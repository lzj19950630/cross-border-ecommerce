"""最小 FastAPI 服务：把运行时暴露成 HTTP API。

启动：
    python -m runtime serve --host 127.0.0.1 --port 8000
或：
    uvicorn runtime.api:app --reload

端点：
    GET  /api/health
    POST /api/tasks
    GET  /api/tasks
    GET  /api/tasks/{thread_id}
    GET  /api/tasks/{thread_id}/approvals
    POST /api/tasks/{thread_id}/resume
    GET  /api/tasks/{thread_id}/trace
    GET  /api/tasks/{thread_id}/checkpoints
    GET  /api/agents
    GET  /api/agents/{key}/file
    PUT  /api/agents/{key}/file
    GET  /api/tools
    GET  /api/actions
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .actions import DEFAULT_ACTION_REGISTRY
from .agent_files import AgentFileError, AgentFileService
from .alerts import collect_alerts
from .delivery import archive_bytes, machine_review
from .metrics import collect_metrics, prometheus_text
from .providers import ProviderError, ProviderService, TenantLLMResolver
from .auth import ROLES, ActionPolicy, AuthConfig, Principal, hash_password_bcrypt
from .engine import RuntimeEngine
from .executors import make_executor
from .factory import make_store
from .llm import load_llm_from_env
from .storage import TaskStore
from .tools import DEFAULT_TOOL_REGISTRY
from .trace import build_trace, list_checkpoints


class TaskCreateRequest(BaseModel):
    request: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None
    decision: Literal["none", "approve", "reject"] = "none"
    comment: str | None = None
    idempotency_key: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TenantCreateRequest(BaseModel):
    id: str
    name: str


class UserCreateRequest(BaseModel):
    tenant_id: str
    username: str
    password: str
    role: Literal["admin", "operator", "viewer"]


class PasswordResetRequest(BaseModel):
    password: str


class ProviderConfigRequest(BaseModel):
    base_url: str
    model: str
    api_key: str


class AgentFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str


class DeliveryDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


class ResumeRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None
    decided_by: str = "api"


def _principal(request: Request) -> Principal | None:
    return getattr(request.state, "principal", None)


def _require(request: Request, roles: set[str]) -> Principal | None:
    principal = _principal(request)
    if principal is None:
        return None
    if principal.role not in roles:
        raise HTTPException(status_code=403, detail="forbidden")
    return principal


def _require_tenant(request: Request) -> Principal:
    principal = _principal(request)
    if principal is None or not principal.tenant:
        raise HTTPException(status_code=400, detail="该操作需要租户身份")
    return principal


def _require_global_admin(request: Request) -> Principal | None:
    principal = _principal(request)
    if principal is None:
        return None
    if principal.role != "admin" or principal.tenant:
        raise HTTPException(status_code=403, detail="需要全局管理员")
    return principal


def _require_tenant_admin(request: Request, tenant_id: str) -> Principal | None:
    principal = _principal(request)
    if principal is None:
        return None
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    if principal.tenant and principal.tenant != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return principal


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password_bcrypt"}


def _check_task(task, request: Request) -> None:
    principal = _principal(request)
    if principal is None:
        return
    if principal.tenant and task.tenant_id != principal.tenant:
        raise HTTPException(status_code=403, detail="forbidden")
    if principal.role != "admin" and task.owner != principal.name:
        raise HTTPException(status_code=403, detail="forbidden")


def create_app(
    store: TaskStore | None = None,
    *,
    executor: str = "auto",
    engine_type: str = "simple",
    apply_webhook: str | None = None,
    checkpointer: str = "auto",
    checkpoint_db: str = ".runtime/checkpoints.db",
    agent_service: AgentFileService | None = None,
    creative: bool = False,
    apply_adapter: str | None = None,
    api_key: str | None = None,
    cors_origins: list[str] | None = None,
    api_keys: dict[str, object] | None = None,
    jwt_secret: str | None = None,
    users: dict[str, object] | None = None,
    action_roles: dict[str, object] | None = None,
    proxy_auth_secret: str | None = None,
    rate_limit: int | None = None,
    secret_key: str | None = None,
) -> FastAPI:
    from .apply import make_apply_fn

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        close = getattr(app.state.engine, "close", None)
        if callable(close):
            close()

    app = FastAPI(
        title="AI Cross-Border Ecommerce Agent Runtime",
        version=__version__,
        lifespan=lifespan,
    )
    apply_fn = make_apply_fn(apply_webhook, adapter_path=apply_adapter)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    task_store = store or make_store()
    auth = AuthConfig(
        api_key=api_key,
        api_keys=api_keys,
        jwt_secret=jwt_secret,
        users=users,
        account_store=task_store,
    )
    action_policy = ActionPolicy(action_roles)
    auth_enabled = auth.enabled or bool(proxy_auth_secret)
    if auth_enabled or rate_limit:
        buckets: dict[str, tuple[float, int]] = {}

        @app.middleware("http")
        async def _guard(request: Request, call_next):
            path = request.url.path
            principal = None
            if auth_enabled:
                if proxy_auth_secret and request.headers.get("x-proxy-auth") == proxy_auth_secret:
                    user = request.headers.get("x-auth-request-user") or request.headers.get("x-forwarded-user")
                    role = request.headers.get("x-auth-request-role") or "viewer"
                    tenant = request.headers.get("x-auth-request-tenant") or ""
                    if user and role in ROLES:
                        principal = Principal(name=user, role=role, tenant=tenant)
                if path.startswith("/api/") and path not in {"/api/health", "/api/auth/login", "/api/auth/refresh", "/api/auth/logout"}:
                    if principal is None:
                        token = request.headers.get("authorization", "")
                        token = token.removeprefix("Bearer ").strip() or request.headers.get("x-api-key", "")
                        engine = getattr(request.app.state, "engine", None)
                        is_revoked = engine.store.is_token_revoked if engine is not None else None
                        principal = auth.authenticate(token, is_revoked=is_revoked)
                    if principal is None:
                        return JSONResponse({"detail": "unauthorized"}, status_code=401)

            if rate_limit and path.startswith("/api/") and path != "/api/health":
                key = (
                    request.headers.get("authorization")
                    or request.headers.get("x-api-key")
                    or (request.client.host if request.client else "anonymous")
                )
                now = time.monotonic()
                window, count = buckets.get(key, (now, 0))
                if now - window >= 60:
                    window, count = now, 0
                count += 1
                buckets[key] = (window, count)
                if count > rate_limit:
                    retry_after = max(1, int(60 - (now - window)))
                    return JSONResponse(
                        {"detail": "rate limit exceeded"},
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )

            request.state.principal = principal
            return await call_next(request)
    providers = ProviderService(task_store, secret_key=secret_key)
    agent_files = agent_service or AgentFileService()
    runners = None
    if creative:
        from .creative import build_creative_registry
        fallback = load_llm_from_env()
        runners = build_creative_registry(TenantLLMResolver(providers, fallback))
    runtime_kwargs = {"runners": runners} if runners else {}
    if engine_type == "supervisor":
        from .supervisor import LangGraphSupervisor
        runtime = LangGraphSupervisor(
            store=task_store,
            executor=make_executor(executor),
            apply_fn=apply_fn,
            checkpointer=checkpointer,
            checkpoint_db=checkpoint_db,
            **runtime_kwargs,
        )
        executor_name = runtime.engine.executor.name
    else:
        runtime = RuntimeEngine(
            store=task_store,
            executor=make_executor(executor),
            apply_fn=apply_fn,
            **runtime_kwargs,
        )
        executor_name = runtime.executor.name
    app.state.engine = runtime
    app.state.engine_type = engine_type
    app.state.executor_name = executor_name
    app.state.creative = creative
    app.state.auth_enabled = auth_enabled
    app.state.rate_limit = rate_limit
    app.state.action_policy = action_policy
    app.state.providers = providers
    app.state.agent_files = agent_files
    app.state.checkpoint_db = checkpoint_db
    app.state.cors_origins = cors_origins or []

    def _task_or_404(thread_id: str):
        try:
            return runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    web_dir = Path(__file__).resolve().parent.parent / "cross-border-ecommerce-admin"
    if web_dir.is_dir():
        app.mount("/static", StaticFiles(directory=web_dir), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "engine": engine_type,
            "executor": executor_name,
            "creative": creative,
            "auth": auth_enabled,
            "proxy_auth": bool(proxy_auth_secret),
            "rate_limit": rate_limit,
            "cors": bool(cors_origins),
        }

    @app.post("/api/auth/login")
    def login(body: LoginRequest) -> dict[str, Any]:
        result = auth.login(body.username, body.password)
        if result is None:
            raise HTTPException(status_code=401, detail="用户名或密码错误（或未配置 JWT）")
        token, principal = result
        return {
            "token": token,
            "name": principal.name,
            "role": principal.role,
            "tenant": principal.tenant,
        }

    @app.post("/api/auth/refresh")
    def refresh_token(request: Request) -> dict[str, Any]:
        token = request.headers.get("authorization", "")
        token = token.removeprefix("Bearer ").strip() or request.headers.get("x-api-key", "")
        result = auth.refresh(token, is_revoked=runtime.store.is_token_revoked)
        if result is None:
            raise HTTPException(status_code=401, detail="token 无效、已过期或已注销")
        old_payload = auth.payload(token)
        if old_payload and old_payload.get("jti"):
            runtime.store.revoke_token(
                str(old_payload["jti"]), float(old_payload.get("exp", 0))
            )
        new_token, principal = result
        return {
            "token": new_token,
            "name": principal.name,
            "role": principal.role,
            "tenant": principal.tenant,
        }

    @app.post("/api/auth/logout")
    def logout(request: Request) -> dict[str, Any]:
        token = request.headers.get("authorization", "")
        token = token.removeprefix("Bearer ").strip() or request.headers.get("x-api-key", "")
        payload = auth.payload(token)
        if payload is None or not payload.get("jti"):
            raise HTTPException(status_code=401, detail="不是有效的 JWT")
        runtime.store.revoke_token(str(payload["jti"]), float(payload.get("exp", 0)))
        return {"status": "logged_out"}

    @app.post("/api/tasks")
    def create_task(body: TaskCreateRequest, request: Request) -> dict[str, Any]:
        principal = _require(request, {"admin", "operator"})
        owner = principal.name if principal else "anonymous"
        tenant_id = principal.tenant if principal else ""
        idempotency_key = request.headers.get("idempotency-key") or body.idempotency_key or ""
        if idempotency_key:
            for existing in runtime.list_tasks():
                if (
                    existing.owner == owner
                    and existing.tenant_id == tenant_id
                    and existing.idempotency_key == idempotency_key
                ):
                    data = existing.to_dict()
                    data["idempotent_replay"] = True
                    return data
        task = runtime.run(
            body.request,
            inputs=body.inputs,
            thread_id=body.thread_id,
            owner=owner,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
        )
        if body.decision != "none" and task.status == "interrupted":
            task = runtime.resume(task.thread_id, decision=body.decision, comment=body.comment)
        return task.to_dict()

    @app.get("/api/tasks")
    def list_tasks(request: Request) -> dict[str, Any]:
        principal = _principal(request)
        tasks = runtime.list_tasks()
        if principal is not None and principal.tenant:
            tasks = [task for task in tasks if task.tenant_id == principal.tenant]
        if principal is not None and principal.role != "admin":
            tasks = [task for task in tasks if task.owner == principal.name]
        return {
            "tasks": [
                {
                    "thread_id": task.thread_id,
                    "request": task.request,
                    "owner": task.owner,
                    "tenant_id": task.tenant_id,
                    "status": task.status,
                    "updated_at": task.updated_at,
                }
                for task in tasks
            ]
        }

    @app.get("/api/tasks/{thread_id}")
    def get_task(thread_id: str, request: Request) -> dict[str, Any]:
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        return task.to_dict()

    @app.post("/api/tasks/{thread_id}/delivery/review")
    def delivery_review(thread_id: str, request: Request) -> dict[str, Any]:
        _require(request, {"admin", "operator"})
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        review = machine_review(task)
        task.delivery_review = dict(task.delivery_review or {})
        task.delivery_review["machine"] = review
        task.delivery_status = "pending" if review["passed"] else "failed"
        runtime.store.save_task(task)
        return task.to_dict()

    @app.post("/api/tasks/{thread_id}/delivery/decision")
    def delivery_decision(
        thread_id: str, body: DeliveryDecisionRequest, request: Request
    ) -> dict[str, Any]:
        principal = _require(request, {"admin", "operator"})
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        machine = (task.delivery_review or {}).get("machine") or {}
        if not machine.get("passed"):
            raise HTTPException(status_code=409, detail="机器审核未通过，不能做交付决定")
        task.delivery_review = dict(task.delivery_review or {})
        task.delivery_review["human"] = {
            "decision": "approved" if body.decision == "approve" else "rejected",
            "note": body.note,
            "reviewer": principal.name if principal else "anonymous",
            "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        task.delivery_status = "passed" if body.decision == "approve" else "rejected"
        runtime.store.save_task(task)
        return task.to_dict()

    @app.get("/api/tasks/{thread_id}/archive")
    def download_archive(thread_id: str, request: Request) -> Response:
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        try:
            data = archive_bytes(task, audits=runtime.store.list_audits(thread_id))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="task-{thread_id}.zip"',
            },
        )

    @app.post("/api/tasks/{thread_id}/cancel")
    def cancel_task(thread_id: str, request: Request) -> dict[str, Any]:
        _require(request, {"admin", "operator"})
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        try:
            task = runtime.cancel(thread_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return task.to_dict()

    @app.get("/api/tasks/{thread_id}/export")
    def export_task_json(thread_id: str, request: Request) -> JSONResponse:
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        payload = {
            "task": task.to_dict(),
            "audits": runtime.store.list_audits(thread_id),
        }
        return JSONResponse(
            payload,
            headers={
                "Content-Disposition": f'attachment; filename="task-{thread_id}.json"',
            },
        )

    @app.get("/api/tasks/{thread_id}/approvals")
    def get_approvals(thread_id: str, request: Request) -> dict[str, Any]:
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        pending = [
            task.envelopes[env_id]
            for env_id in task.pending_envelopes
            if env_id in task.envelopes
        ]
        return {"thread_id": thread_id, "pending": pending}

    @app.post("/api/tasks/{thread_id}/resume")
    def resume(thread_id: str, body: ResumeRequest, request: Request) -> dict[str, Any]:
        principal = _require(request, {"admin", "operator"})
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        if principal is not None:
            denied: list[str] = []
            for envelope_id in task.pending_envelopes:
                envelope = runtime.store.get_envelope(envelope_id)
                denied.extend(
                    action.action for action in envelope.actions
                    if not action_policy.allowed(principal, action.action)
                )
            if denied:
                raise HTTPException(
                    status_code=403,
                    detail=f"当前角色不能批准动作：{sorted(set(denied))}",
                )
        try:
            task = runtime.resume(
                thread_id,
                decision=body.decision,
                comment=body.comment,
                decided_by=principal.name if principal else body.decided_by,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return task.to_dict()

    @app.get("/api/tasks/{thread_id}/trace")
    def task_trace(thread_id: str, request: Request) -> dict[str, Any]:
        task = _task_or_404(thread_id)
        _check_task(task, request)
        return build_trace(task, runtime.store.list_audits(thread_id))

    @app.get("/api/tasks/{thread_id}/checkpoints")
    def task_checkpoints(thread_id: str, request: Request) -> dict[str, Any]:
        task = _task_or_404(thread_id)
        _check_task(task, request)
        data = list_checkpoints(checkpoint_db, thread_id)
        data["task_checkpoint"] = task.checkpoint
        data["task_status"] = task.status
        return data

    @app.post("/api/evals")
    def run_evals(request: Request) -> dict[str, Any]:
        _require(request, {"admin", "operator"})
        from .evals import load_cases, run_cases
        root = Path(__file__).resolve().parent.parent
        cases = load_cases(root / "Templates" / "eval_case.yaml")
        report = run_cases(cases)
        report["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        runtime.store.save_eval_run(report)
        return report

    @app.get("/api/evals")
    def eval_history() -> dict[str, Any]:
        return {"runs": runtime.store.list_eval_runs(limit=20)}

    @app.get("/api/tenants")
    def list_tenants(request: Request) -> dict[str, Any]:
        _require_global_admin(request)
        users = runtime.store.list_users()
        return {
            "tenants": [
                {
                    **tenant,
                    "user_count": sum(1 for user in users if user.get("tenant_id") == tenant["id"]),
                }
                for tenant in runtime.store.list_tenants()
            ]
        }

    @app.post("/api/tenants")
    def create_tenant(body: TenantCreateRequest, request: Request) -> dict[str, Any]:
        _require_global_admin(request)
        tenant_id = body.id.strip()
        if not tenant_id or not body.name.strip():
            raise HTTPException(status_code=422, detail="tenant id/name 不能为空")
        if runtime.store.get_tenant(tenant_id) is not None:
            raise HTTPException(status_code=409, detail="租户已存在")
        tenant = {
            "id": tenant_id,
            "name": body.name.strip(),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        runtime.store.save_tenant(tenant)
        return tenant

    @app.delete("/api/tenants/{tenant_id}")
    def delete_tenant(tenant_id: str, request: Request) -> dict[str, Any]:
        _require_global_admin(request)
        if runtime.store.list_users(tenant_id):
            raise HTTPException(status_code=409, detail="租户下仍有用户，不能删除")
        runtime.store.delete_tenant(tenant_id)
        return {"status": "deleted", "id": tenant_id}

    @app.get("/api/users")
    def list_users(request: Request, tenant_id: str | None = None) -> dict[str, Any]:
        principal = _principal(request)
        if principal is None:
            target = tenant_id
        else:
            if principal.role != "admin":
                raise HTTPException(status_code=403, detail="forbidden")
            target = principal.tenant or tenant_id
        return {"users": [_public_user(user) for user in runtime.store.list_users(target)]}

    @app.post("/api/users")
    def create_user(body: UserCreateRequest, request: Request) -> dict[str, Any]:
        _require_tenant_admin(request, body.tenant_id)
        if runtime.store.get_tenant(body.tenant_id) is None:
            raise HTTPException(status_code=404, detail="租户不存在")
        username = body.username.strip()
        if not username or not body.password:
            raise HTTPException(status_code=422, detail="用户名/密码不能为空")
        if runtime.store.get_user(username) is not None:
            raise HTTPException(status_code=409, detail="用户名已存在")
        user = {
            "tenant_id": body.tenant_id,
            "username": username,
            "role": body.role,
            "password_bcrypt": hash_password_bcrypt(body.password),
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        runtime.store.save_user(user)
        return _public_user(user)

    @app.delete("/api/users/{username}")
    def delete_user(username: str, request: Request) -> dict[str, Any]:
        user = runtime.store.get_user(username)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        principal = _require_tenant_admin(request, user["tenant_id"])
        if principal is not None and principal.name == username:
            raise HTTPException(status_code=409, detail="不能删除当前登录用户")
        runtime.store.delete_user(username)
        return {"status": "deleted", "username": username}

    @app.put("/api/users/{username}/password")
    def reset_password(
        username: str, body: PasswordResetRequest, request: Request
    ) -> dict[str, Any]:
        user = runtime.store.get_user(username)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        _require_tenant_admin(request, user["tenant_id"])
        if not body.password:
            raise HTTPException(status_code=422, detail="密码不能为空")
        user["password_bcrypt"] = hash_password_bcrypt(body.password)
        runtime.store.save_user(user)
        return {"status": "password_updated", "username": username}

    @app.get("/api/providers")
    def list_providers(request: Request) -> dict[str, Any]:
        principal = _require_tenant(request)
        return {"providers": providers.list(principal.tenant)}

    @app.put("/api/providers/{name}")
    def save_provider(
        name: str, body: ProviderConfigRequest, request: Request
    ) -> dict[str, Any]:
        principal = _require(request, {"admin"})
        principal = _require_tenant(request)
        try:
            config = providers.save(
                tenant_id=principal.tenant,
                name=name,
                base_url=body.base_url,
                model=body.model,
                api_key=body.api_key,
                updated_by=principal.name,
            )
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return config

    @app.delete("/api/providers/{name}")
    def delete_provider(name: str, request: Request) -> dict[str, Any]:
        principal = _require(request, {"admin"})
        principal = _require_tenant(request)
        providers.delete(principal.tenant, name)
        return {"status": "deleted", "name": name}

    @app.post("/api/providers/{name}/test")
    def test_provider(name: str, request: Request) -> dict[str, Any]:
        principal = _require(request, {"admin", "operator"})
        principal = _require_tenant(request)
        try:
            return providers.test(principal.tenant, name)
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/agents")
    def list_agents(request: Request) -> dict[str, Any]:
        _require(request, {"admin", "operator", "viewer"})
        return {"agents": agent_files.list_agents()}

    @app.get("/api/agents/edits")
    def agent_edit_log(request: Request, limit: int = 50) -> dict[str, Any]:
        _require(request, {"admin"})
        return {"edits": agent_files.edits(limit=limit)}

    @app.get("/api/agents/{key}")
    def get_agent(key: str, request: Request) -> dict[str, Any]:
        _require(request, {"admin", "operator", "viewer"})
        try:
            return agent_files.get_agent(key)
        except AgentFileError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/agents/{key}/file")
    def read_agent_file(key: str, request: Request, path: str) -> dict[str, Any]:
        _require(request, {"admin", "operator", "viewer"})
        try:
            return agent_files.read(key, path)
        except AgentFileError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.put("/api/agents/{key}/file")
    def write_agent_file(
        key: str, body: AgentFileWriteRequest, request: Request
    ) -> dict[str, Any]:
        principal = _require(request, {"admin"})
        try:
            result = agent_files.write(
                key,
                body.path,
                body.content,
                user=principal.name if principal else "anonymous",
            )
        except AgentFileError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        result["saved_by"] = principal.name if principal else "anonymous"
        return result

    @app.get("/api/metrics")
    def metrics_json() -> dict[str, Any]:
        return collect_metrics(runtime.store)

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics_prometheus() -> str:
        return prometheus_text(collect_metrics(runtime.store))

    @app.get("/api/alerts")
    def alerts(stale_minutes: int = 30) -> dict[str, Any]:
        return {"alerts": collect_alerts(runtime.store, stale_minutes=stale_minutes)}

    @app.get("/api/tools")
    def tools() -> dict[str, Any]:
        return {"tools": [tool.to_dict() for tool in DEFAULT_TOOL_REGISTRY.all()]}

    @app.get("/api/actions")
    def actions() -> dict[str, Any]:
        return {"actions": DEFAULT_ACTION_REGISTRY.metadata()}

    @app.get("/api/audits/{thread_id}")
    def audits(thread_id: str, request: Request) -> dict[str, Any]:
        try:
            task = runtime.get_task(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _check_task(task, request)
        return {"thread_id": thread_id, "audits": runtime.store.list_audits(thread_id)}

    return app


# 用 uvicorn 启动：uvicorn runtime.api:create_app --factory
