# CHANGELOG

本文件记录本工具箱的结构与内容变更。

---

## [v0.29] — 2026-11-18

### Phase 8b · 目录重构 + 系统管理

#### 目录拆分

- `cross-border-ecommerce-api/`：入口、依赖、Dockerfile、Compose、TLS 样例；
- `cross-border-ecommerce-admin/`：零构建单页后台；
- `runtime/` 保持为共享平台核心包；
- `.gitignore` 增加 `github/`，外部参考项目不再上传。

#### 系统管理

- 租户 CRUD：`/api/tenants`；
- 用户 CRUD / 密码重置：`/api/users`；
- 租户级模型配置：`/api/providers`（保存/测试）；
- Web「系统管理」页面：
  - 创建租户；
  - 创建用户（tenant/username/password/role）；
  - 保存/测试模型配置。
- 动态账号登录：JWT 登录支持数据库用户（bcrypt）。

#### 测试

- **206 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- 租户隔离仍在 API 层；
- 密码重置无邮件通知；
- 平台沙箱、真实 LLM 冒烟、监控看板仍未做。

---

## [v0.28] — 2026-11-18

### Phase 8a · 租户级模型配置 + Key 加密

#### 新增

- `runtime/providers.py`：
  - `ProviderService`：租户级 `base_url/model/api_key`；
  - `RUNTIME_SECRET_KEY` + Fernet 加密保存；
  - `TenantLLMResolver`：按 `context.tenant_id` 选择模型，回退全局 LLM。
- 存储：
  - InMemory / SQLite / Postgres 三套 `provider_configs`。
- API：
  - `GET /api/providers`
  - `PUT /api/providers/{name}`
  - `DELETE /api/providers/{name}`
  - `POST /api/providers/{name}/test`
- 创意层：租户配置存在时优先使用租户模型。
- `runtime/requirements-runtime.txt` 增加 `cryptography`。

#### 测试

- **204 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 加密/脱敏/CRUD/测试连接/租户解析均有覆盖；
- 04 mock 渲染测试继续通过。

#### 边界

- 主密钥丢失会导致已存 Key 无法解密；
- 测试连接会真实调用一次模型；
- 平台沙箱、真实 LLM 冒烟、监控看板仍未做。

---

## [v0.27] — 2026-11-18

### Phase 7b · 交付审核 / 幂等 / 租户

#### 交付审核 + ZIP

- `runtime/delivery.py`：
  - 机器审核：状态/产物/证据/信封/合规；
  - 人工交付决定；
  - 归档 ZIP：task/artifacts/evidence/envelopes/audits/summary/manifest/assets。
- API：
  - `POST /api/tasks/{id}/delivery/review`
  - `POST /api/tasks/{id}/delivery/decision`
  - `GET /api/tasks/{id}/archive`
- Web：机器审核/通过/拒绝/下载 ZIP。
- 文档：`docs/18_Delivery_and_Archive.md`。

#### 幂等 + 执行耗时

- `Idempotency-Key` 请求头 / body 字段；
- 同 owner+tenant+key 返回原任务（`idempotent_replay`）；
- 切片记录 `started_at/finished_at/elapsed_ms/retries`；
- Web 表格展示耗时。
- 文档：`docs/19_Idempotency_and_Tenancy.md`。

#### 租户隔离

- `TaskRecord.tenant_id`；
- API Key 支持 `tenant:name:role`；
- JWT / 代理 SSO 支持 tenant；
- 列表/详情按 tenant + owner 过滤。

#### 测试

- **200 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- 交付审核是确定性检查 + 人工决定，不替代业务判断；
- 幂等是应用层扫描，不是数据库唯一索引；
- 租户隔离在 API 层，数据库仍共享；
- 平台沙箱、真实 LLM 冒烟、密钥加密仍未做。

---

## [v0.26] — 2026-11-18

### Phase 7a · 限流 / 指标看板 / v1 就绪

#### 限流

- `RUNTIME_RATE_LIMIT`：每分钟请求数上限；
- 超限 → 429 + `Retry-After`；
- 按 token / API Key / IP 分桶；
- `/api/health` 不限流。

#### 指标看板

- Web「指标」从 JSON 升级为看板：
  - 任务总数 / 待审批 / 评测次数 / 失败阻塞；
  - 任务状态分布条；
  - 最近 5 条告警。

#### v1 就绪清单

- `docs/17_Runtime_Readiness.md`：
  - 已具备能力矩阵；
  - 已知缺口（平台沙箱、真实 LLM、多租户等）；
  - v1.0 发布标准与步骤。

#### 测试

- **190 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- 限流是单进程内存实现；多实例需 Redis/网关限流；
- 平台沙箱、真实 LLM 冒烟仍未做。

---

## [v0.25] — 2026-11-18

### Phase 6e · 7/7 评测覆盖 + 任务取消

#### 评测覆盖

`Templates/eval_case.yaml` 从 3 个 case 扩到 7 个，覆盖 01–07：

- 新增 02 定价 / 03 Listing / 04 图片 / 05 视频；
- 新机械判据：
  - `skus_nonempty`
  - `title_present`
  - `image_plan_present`
  - `video_timing_ok`
- 7/7 全部通过。

#### 任务取消

- `RuntimeEngine.cancel` + Supervisor 代理；
- `POST /api/tasks/{id}/cancel`；
- Web 任务详情「取消任务」；
- 新增 `cancelled` 状态；
- 取消后清空 pending envelopes。

#### 测试

- **188 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- 取消不撤销已 apply 的外部动作；
- 平台沙箱验证、监控看板、多租户隔离仍未做。

---

## [v0.24] — 2026-11-18

### Phase 6d · JWT 注销 / Token 吊销 / 刷新轮换

#### 新增

- JWT 增加 `jti`；
- `TaskStore.revoke_token` / `is_token_revoked`：
  - InMemory：内存字典；
  - SQLite：`revoked_tokens` 表；
  - Postgres：`runtime_revoked_tokens` 表；
- `POST /api/auth/logout`：吊销当前 JWT；
- `POST /api/auth/refresh`：签发新 JWT 并吊销旧 token（轮换）；
- Middleware 校验 JWT 时检查吊销表；
- Web 退出按钮调用 logout。

#### 测试

- **185 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 新增 logout、refresh 轮换、SQLite 吊销表测试；
- 04 mock 渲染测试继续通过。

#### 边界

- 吊销表按 exp 清理；API Key 不走吊销；
- 平台沙箱验证、监控看板、多租户隔离仍未做。

---

## [v0.23] — 2026-11-18

### Phase 6c · 监控 / 告警 / 代理 SSO

#### 指标

- `GET /api/metrics`：任务总数/状态分布/待审批/评测次数；
- `GET /metrics`：Prometheus 文本格式；
- Web「指标」按钮查看 JSON。

#### 告警

- `GET /api/alerts?stale_minutes=30`：
  - failed / blocked 任务；
  - 等待审批超过 N 分钟的任务；
- Web「告警」按钮查看列表。

#### 代理 SSO

```bash
export RUNTIME_PROXY_AUTH_SECRET=proxy-secret
# 反代（oauth2-proxy/authentik）注入：
# X-Proxy-Auth: proxy-secret
# X-Auth-Request-User: alice
# X-Auth-Request-Role: admin
```

- 仅在 `X-Proxy-Auth` 匹配时信任用户/角色头；
- 需要反代剥离客户端自带的同名头。

#### CI

- 新增 `docker` job：`docker build` + 容器内 `python -m runtime doctor`；
- 新增 compose config 校验步骤。

#### 测试

- **182 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- 平台沙箱验证、token 吊销、监控看板仍未做；
- 代理 SSO 依赖反代正确配置。

---

## [v0.22] — 2026-11-18

### Phase 6b · 评测趋势 / 任务导出 / TLS 反代

#### 评测趋势

- Web「评测历史」新增 SVG 趋势图（pass rate 随时间的折线）；
- 无第三方图表库；
- 历史仍来自 InMemory / SQLite / Postgres 的 `eval_runs`。

#### 任务导出

- `GET /api/tasks/{id}/export`：task + audits JSON 下载；
- Web 任务详情新增「导出 JSON」按钮。

#### TLS 反代

- `deploy/Caddyfile`（自动 HTTPS）；
- `deploy/nginx.conf`（TLS + 基础限流示例）；
- `docker-compose.prod.yml`（Caddy overlay）；
- `deploy/README.md` 上线检查。

#### 测试

- **178 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- Caddy/Nginx 配置未在本机启动验证；
- 平台沙箱、SSO、token 吊销仍未做。

---

## [v0.21] — 2026-11-18

### Phase 6a · 评测历史 + JWT 刷新 + 导出审计

#### 评测历史

- `TaskStore` 增加 `save_eval_run` / `list_eval_runs`；
- InMemory / SQLite / SQLAlchemy 三实现；
- `POST /api/evals` 保存结果，`GET /api/evals` 返回最近 20 次；
- Web 控制台「评测历史」+ 任务状态筛选。

#### JWT 刷新

- `POST /api/auth/refresh`：未过期 token → 新 token；
- `AuthConfig.issue/refresh`；
- API Key 也可换 JWT（若配置 JWT）。

#### 导出审计

- `export_task(..., audits=...)` 写 `audits.json`；
- CLI `export` 自动带上该任务的审批审计。

#### 测试

- **177 个测试**（2 个 Postgres 集成在无 env 时 skip）；
- 04 mock 渲染测试继续通过。

#### 边界

- 评测历史未做趋势图；
- JWT 无刷新 token 轮换/吊销；
- 平台沙箱仍未验证。

---

## [v0.20] — 2026-11-18

### Phase 5g · 真实 Postgres + bcrypt + CI

#### 真实 Postgres 验证

- Docker 启动 `postgres:16-alpine`；
- `SQLAlchemyStore`：跨 engine 创建/审批/审计通过；
- `langgraph-checkpoint-postgres`：Supervisor 原生 durable 断点跨进程 resume 通过；
- `docker-compose.yml` 改为 Postgres + `--checkpointer postgres`（`docker compose config` 校验通过）；
- 新增 `runtime/tests/test_postgres_integration.py`（无 env 时 skip）。

#### bcrypt

- `hash_password_bcrypt()` + `password_bcrypt` 用户字段；
- 兼容旧 `password_sha256`；
- `runtime/requirements-runtime.txt` 增加 bcrypt。

#### CI

- `.github/workflows/tests.yml`：
  - Python 3.12 + `runtime/requirements-runtime.txt`；
  - Postgres service；
  - `unittest discover -s runtime/tests`；
  - 04 渲染自测 + CLI smoke。

#### 测试

- **175 个测试**：无 Postgres env 时 2 个 skip；有 env 时全部通过。
- 04 mock 渲染测试继续通过。

#### 边界

- Docker 镜像 build 在本机被 Docker Hub 网络阻塞（compose 配置本身有效）；
- 平台沙箱仍未验证；
- Web 仍无 SSO/可视化评测看板。

---

## [v0.19] — 2026-11-18

### Phase 5f · JWT 登录 + 动作级审批权限

#### JWT 登录

- `runtime/auth.py`：stdlib HS256 JWT 编码/解码；
- `RUNTIME_JWT_SECRET` + `RUNTIME_USERS`（`password_sha256` + role）；
- `POST /api/auth/login`：用户名/密码 → token；
- Middleware 同时接受 API Key 与 JWT；
- Web 控制台新增登录/退出；
- 无 JWT 配置时仍可用 API Key。

#### 动作级审批策略

```bash
export RUNTIME_ACTION_ROLES='{"listing.update_title":["admin"]}'
```

- 支持精确 action 与通配 `ad.*`；
- 未配置动作默认 admin/operator；
- 审批前检查信封内每个 action，角色不足 → 403；
- 审计 `decided_by` 仍记录审批人。

#### 测试

- `runtime/tests/test_auth_jwt.py`：登录、过期 token、动作权限；
- 全量 **172 个测试通过**；
- 04 mock 渲染测试继续通过。

#### 边界

- 无 SSO / 刷新 token / 密码重置；
- `password_sha256` 是简单哈希，生产需加盐/慢哈希；
- 平台沙箱验证仍未做。

---

## [v0.18] — 2026-11-18

### Phase 5e · 多用户/角色 + 适配器增强

#### 多用户 / 角色

- `runtime/auth.py`：`RUNTIME_API_KEYS` JSON 多密钥；
- 角色：`admin` / `operator` / `viewer`；
- 任务增加 `owner` 字段；
- API 权限：
  - viewer 不能创建/审批/评测；
  - operator 只能看/审批自己的任务；
  - admin 看全部；
  - 审计 `decided_by` 记录用户名；
- Web 控制台 API Key 输入 + 证据卡片；
- `docs/16_Multi_User_and_Roles.md`。

#### 适配器增强

- `retry.attempts` / `retry.backoff`：5xx/网络/超时重试，4xx 不重试；
- `idempotency_header`：`<envelope_id>:<序号>:<action>`；
- `signing`：HMAC-SHA256 签名（`secret_env` / `header` / `prefix`）；
- mock 测试覆盖重试、幂等头、签名。

#### 测试

- `python -m unittest discover -s runtime/tests` → **169 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- 无 JWT/SSO/密码登录；静态 API Key；
- 无按角色细分的动作权限；
- 平台字段仍需沙箱验证。

---

## [v0.17] — 2026-11-18

### Phase 5d · 生产加固

#### 安全

- 可选 API Key 认证：
  - `RUNTIME_API_KEY` 开启后 `/api/*` 需要 `Authorization: Bearer` 或 `X-API-Key`；
  - `/api/health` 与 `/` 保持公开；
- CORS 白名单：`RUNTIME_CORS_ORIGINS`；
- Web 控制台右上角输入 API Key（存 localStorage）；
- 密钥仍全部走环境变量，不落仓库。

#### 部署

- `Dockerfile`：Python 3.12 + requirements + `python -m runtime serve`；
- `docker-compose.yml`：端口 8000 + `runtime-data` 卷 + 环境变量；
- `.dockerignore`：排除 `.git/.runtime/github/generated-images`；
- `runtime/requirements-runtime.txt` 增加 `psycopg[binary]`；
- `docs/15_Production_Checklist.md`：安全/数据/部署/平台/LLM/可观测性/上线检查。

#### Web

- 任务详情证据从 raw JSON 升级为**证据卡片**（claim/source/locator/type）+ 原始 JSON 折叠。

#### 测试

- `python -m unittest discover -s runtime/tests` → **160 个测试通过**
- 新增认证/CORS 测试；04 mock 渲染测试继续通过。

#### 边界

- 仍是单租户 API Key，没有多用户/角色；
- 平台适配器需沙箱验证；
- Dockerfile 未在本机实际 build（可用 `docker compose up -d --build` 验证）。

---

## [v0.16] — 2026-11-18

### Phase 5c · 平台动作适配器 + 评测 API/Web

#### 平台动作适配器

- `runtime/platforms.py`：`MappingAdapter`，YAML/JSON 配置动作映射；
- 支持 `{target}` / `{before.x}` / `{after.x}` / `{reason}` 等模板变量；
- `bearer` / `header` / `none` 鉴权，token 只从环境变量读取；
- 缺映射/缺 token/非 2xx → `PlatformAdapterError`；
- CLI `--apply-adapter`，API `create_app(apply_adapter=...)`；
- 示例：`Templates/platform_adapter.example.yaml`。

#### 评测 API / Web

- `POST /api/evals`：跑 `Templates/eval_case.yaml` 确定性评测；
- Web 控制台新增「运行评测」按钮与结果展示；
- 平台适配器 mock 测试覆盖路径编码/body/token/错误。

#### 测试

- `python -m unittest discover -s runtime/tests` → **158 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- 适配器字段是占位示例，必须按平台官方 API 文档替换；
- 不做平台请求签名/重试/分布式事务；
- Web 仍无认证/CORS。

---

## [v0.15] — 2026-11-18

### Phase 5b · Web 控制台 + LLM judge + 依赖对齐

#### Web 控制台

- `runtime/web/index.html`：零构建静态页面；
- FastAPI 同源托管 `GET /` 与 `/static`；
- 功能：任务列表、创建任务（含 inputs/自动审批）、任务详情、切片、审批信封批准/拒绝、产物/证据 JSON、审计。

#### LLM judge

- `runtime/evals.py` 增加 `judge` 参数；
- 每条 rubric 0/1 + 理由，必须在最后报告里覆盖全部 rubric；
- 判据数量不符/非布尔 → `judge_error`，case 失败；
- CLI `python -m runtime eval Templates/eval_case.yaml --judge`；
- 测试全部 `FakeLLM`，不真实调用。

#### 依赖对齐

- `runtime/requirements-runtime.txt`：langgraph / checkpoint / SQLAlchemy / FastAPI / uvicorn / PyYAML / Pillow；
- 建议干净 venv 安装（当前旧环境有版本声明冲突）。

#### 测试

- `python -m unittest discover -s runtime/tests` → **153 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- Web 控制台无认证/CORS，仅本地原型；
- 真实平台适配器仍未接；
- LLM judge 未做可视化看板。

---

## [v0.14] — 2026-11-18

### Phase 5a · LLM 创意层 + 原生 SQLite checkpointer

#### LLM 创意层

- `runtime/llm.py`：OpenAI 兼容 Chat Completions 客户端 + `FakeLLM`；
- `runtime/creative.py`：
  - 03：PT-BR 标题/详情/次级卖点 → 过 `title_lint` + `spec_consistency`；
  - 04：9 图规划 + 逐图英文 Prompt；
  - 05：PT-BR 台词/分镜/字幕 → 过 `video_timing`；
  - 07：PT-BR 修补建议 + 卖点排行；
- LLM 失败 → 回退确定性结果并记录消息；
- 默认关闭，`--creative` 显式启用；
- 测试全部使用 `FakeLLM`，不访问网络、不烧 token。

#### 原生 durable checkpointer

- 安装并接入 `langgraph-checkpoint-sqlite`；
- `LangGraphSupervisor(checkpointer="sqlite", checkpoint_db=...)`；
- CLI `--checkpointer auto|memory|sqlite`；
- 跨进程 `Command(resume=...)` 直接恢复 LangGraph 断点（不再依赖任务 checkpoint 回退）；
- 未安装时自动回退 MemorySaver + 任务 checkpoint。

#### 测试

- `python -m unittest discover -s runtime/tests` → **148 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- 真实平台 API 仍未接；Webhook 是通用执行口；
- 04 Prompt 未做像素校验（需实际出图后校验）；
- 仍无前端 / LLM judge。

---

## [v0.13] — 2026-11-18

### Phase 4b · 跨进程续跑 + Webhook apply + 确定性评测

#### 跨进程 Supervisor 续跑

- `TaskRecord.checkpoint`：保存 `current_layer` / `status`；
- 同进程：MemorySaver 有状态 → `Command(resume=...)`；
- 新进程：MemorySaver 无状态 → `engine.decide_pending` + `continue_plan` 回退；
- CLI `resume --engine supervisor` 现在可跨进程完成。

#### Webhook apply

- `runtime/apply.py`：`DryRunExecutor` / `WebhookExecutor`；
- 审批通过后把 `ApprovalEnvelope` POST 到外部执行器；
- `RUNTIME_APPLY_TOKEN` 环境变量传 Bearer token；
- CLI `run/resume/serve --apply-webhook <url>`；
- 默认仍为 dry-run。

#### 确定性评测

- `runtime/evals.py`：读取 `Templates/eval_case.yaml`，跑固定输入 + 机械判据；
- 判据：`number_traceable` / `required_sections` / `action_envelope_valid` /
  `no_forbidden_action` / `attribution_sum`；
- CLI `python -m runtime eval Templates/eval_case.yaml`；
- 3 个模板场景全部通过。

#### 测试

- `python -m unittest discover -s runtime/tests` → **140 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- 跨进程续跑依赖任务 checkpoint，不是 LangGraph 原生 durable checkpointer；
- Webhook 是通用执行接口，真实平台适配仍需 P5；
- 仍无 LLM 创意层 / 前端。

---

## [v0.12] — 2026-11-18

### Phase 4a · LangGraph Supervisor + interrupt/resume

用 LangGraph 原生 `StateGraph` + `MemorySaver` + `interrupt` 表达审批断点，
与 `RuntimeEngine` 共享 Runner、证据校验、审批信封、存储。

#### 新增

| 文件 | 内容 |
|---|---|
| `runtime/supervisor.py` | `LangGraphSupervisor`：plan → execute_layer → approval → resume |
| `runtime/tests/test_supervisor.py` | 06 中断/批准/拒绝、全链路 06 断点 → 07、clarify、无待审批 |
| `runtime/tests/test_executors.py` | 顺序 / LangGraph 层执行器 |
| `runtime/tests/test_sqlalchemy_store.py` | SQLAlchemy（SQLite URL）跨 engine |
| `runtime/tests/test_api.py` | FastAPI 端点 + supervisor 模式 |

#### 引擎与接入

- `RuntimeEngine` 暴露 `execute_slice` / `record_result` / `decide_pending`，供 Supervisor 复用；
- 新增 `running` 任务状态；
- CLI：`run/resume/serve --engine simple|supervisor`；
- FastAPI：`create_app(engine_type="supervisor")`，`python -m runtime serve --engine supervisor`；
- SQLAlchemyStore：SQLite 可直接跑，Postgres 换 `RUNTIME_DB_URL` + psycopg；
- `runtime/executors.py`：默认优先 LangGraph 层执行器，失败回退 sequential。

#### 测试

- `python -m unittest discover -s runtime/tests` → **130 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- Supervisor 使用 `MemorySaver`：断点状态在进程内，跨重启需 durable checkpointer；
- apply 仍为 dry-run；
- 尚未接真实平台 API / LLM 创意层 / 前端。

---

## [v0.11] — 2026-11-18

### Phase 3d · LangGraph 层执行器 + SQLAlchemy + FastAPI

- `runtime/executors.py`：顺序执行器 + LangGraph 层扇出执行器（默认 auto）
- `runtime/integrations/sqlalchemy_store.py`：SQLite/Postgres 通用 `TaskStore`
- `runtime/api.py`：FastAPI 端点（health/tasks/approvals/resume/audits/tools/actions）
- `runtime/factory.py`：存储工厂（SQLite / `RUNTIME_DB_URL`）
- `runtime/tests/test_executors.py` / `test_sqlalchemy_store.py` / `test_api.py`
- CLI：`run --executor`，`serve` 命令
- **122 个测试通过**

---

## [v0.10] — 2026-11-18

### Phase 3c · 运维加固

让运行时能自检、能审计、能导出，并且不会把"没有证据/信封非法"的产出当成成功。

#### 新增

| 文件/命令 | 内容 |
|---|---|
| `runtime/doctor.py` / `python -m runtime doctor` | Python/脚本/样本/SQLite/可选依赖自检（29 项） |
| `runtime/export.py` / `python -m runtime export` | 导出 `task.json` + `summary.md` + 产物/证据/信封 |
| `python -m runtime audits` | 审批审计查询 |
| `runtime/tests/test_doctor.py` | 自检通过/缺脚本失败 |
| `runtime/tests/test_export.py` | 中断/完成任务导出 |
| `runtime/tests/test_engine_invariants.py` | 无证据/非法信封必须失败 |

#### 加固

- `_execute` 增加不变量：`ok` 产出必须有证据；证据块必须通过校验；审批信封必须通过校验；Runner 返回的 Agent 必须一致。
- `TaskRecord.set_status` + `VALID_TASK_STATUSES`：非法状态直接拒绝。
- SQLite 连接在 CLI 命令结束时关闭；`.gitignore` 增加 `*.db-wal` / `*.db-shm`。
- `doctor` 自动检查 11 个脚本、7 个 Agent 工具、7 个样本文件、SQLite schema。

#### 测试

- `python -m unittest discover -s runtime/tests` → **110 个测试通过**
- 04 mock 渲染测试继续通过。

#### 边界

- 单机 SQLite；多实例仍待 Postgres；
- apply 仍为 dry-run；
- LangGraph 尚未接入。

---

## [v0.9] — 2026-11-18

### Phase 3b · SQLite 持久化 + 跨进程审批

把 Phase 3a 的内存编排落盘到 SQLite（stdlib `sqlite3`），让 `run` 与 `resume`
可以在不同进程/不同命令之间完成。

#### 新增/修改

| 文件 | 内容 |
|---|---|
| `runtime/storage.py` | `TaskStore` 协议；`TaskRecord.from_dict`；`InMemoryStore`；`SQLiteStore` |
| `runtime/engine.py` | 适配 `TaskStore`；任务聚合状态统一 `save_task`；审批后继续剩余切片 |
| `runtime/cli.py` | `run --db`、`resume`、`task`、`tasks`；默认 `.runtime/runtime.db` |
| `runtime/tests/test_sqlite_store.py` | 跨 engine 持久化、全链路 7 产物、任务列表 |
| `runtime/tests/test_cli.py` | 跨命令 run → resume → task |
| `.gitignore` | 忽略 `.runtime/` 与 `*.db` |

#### SQLite 表

- `tasks(thread_id, payload)`：完整 `TaskRecord` JSON
- `envelopes(envelope_id, thread_id, payload)`：审批信封
- `audits(id, thread_id, payload)`：审批审计

#### CLI

```bash
python -m runtime run "广告 ROAS 太低，怎么降预算"        # exit 2，interrupted
python -m runtime resume <thread_id> --decision approve    # exit 0，completed
python -m runtime task <thread_id>                         # 查看任务
python -m runtime tasks                                    # 列出任务
```

#### 测试

- `python -m unittest discover -s runtime/tests` → **100 个测试通过**
- 全链路跨进程：run（6 个产物，06 审批）→ resume（07 执行）→ completed

#### 边界

- SQLite 是单机持久化；多实例/并发仍待 Postgres；
- apply 仍为 dry-run；
- LangGraph supervisor 尚未接入。

---

## [v0.8] — 2026-11-18

### Phase 3a · 7 Agent 内存全链路 + 审批后续跑

补齐 03/04/05/07 四个 Runner，并让 `resume(approve)` 在审批后**继续执行剩余切片**。

#### 新增 Runner

| Agent | 调用 | 产物 | 审批 |
|---|---|---|---|
| 03 Listing | `title_lint` + `spec_consistency` | 标题校验/参数溯源 | 可选换标题信封 |
| 04 商品图 | `check_main_image` | 像素报告 + 9 图骨架 | 可选换主图信封 |
| 05 视频 | `video_timing` | 时长/字幕校验 | 无 |
| 07 评论 | `review_stats` | 归因/可修复率 | 可选修补 Listing 信封 |

#### 编排增强

- `TaskRecord` 增加 `inputs`，支持 resume 后继续；
- `RuntimeEngine._execute_plan`：跳过已执行切片，审批通过后继续剩余层；
- 全链路：01→02→03→04/05→06（审批中断）→ 07；
- 06 批准后自动继续 07，任务最终 `completed`。

#### 测试

- `python -m unittest discover -s runtime/tests` → **95 个测试通过**
- 新增 Runner 测试：03/04/05/07；
- 新增全链路中断→批准→07 完成测试；
- 04 mock 渲染测试继续通过。

#### 边界

- 仍是内存存储、单进程；Postgres 持久化与 LangGraph 替换在 P3b；
- 03/04/05/07 目前是"确定性校验 + 骨架"，不是完整 LLM 创意生成；
- apply 仍为 dry-run。

---

## [v0.7] — 2026-11-18

### Phase 2 · 内存编排 + 审批闭环

在 `runtime/` 平台核心上增加了可执行的内存编排引擎，先跑通 **01 / 02 / 06** 三条链路，
不接数据库、不接 LangGraph、不调 LLM。

#### 新增

| 文件 | 内容 |
|---|---|
| `runtime/storage.py` | `TaskRecord` + `InMemoryStore`：任务/产物/证据/审批/审计 |
| `runtime/agent_runners.py` | 01 市场分析、02 产品策略、06 广告 Runner；03/04/05/07 明确 `blocked` Stub |
| `runtime/engine.py` | `RuntimeEngine`：IntentRouter → ManagerPlanner → 逐层执行 → 审批中断 → resume |
| `runtime/tests/test_agent_runners.py` | Runner 产物/证据/审批信封测试 |
| `runtime/tests/test_engine.py` | 01 完成、01→02 顺序、06 中断/批准/拒绝/漂移、Stub、clarify |
| `runtime/tests/test_cli.py` | 扩展 `run` 命令测试 |

#### 能力

- 01：读取 `market_metrics` 指标 JSON → 容量/集中度/价格带产物 + 3 条证据；
- 02：调用 `sku_pricing.py matrix` → SKU 净利率/价格阶梯 + 证据；
- 06：调用 `ad_metrics.py diagnose` → 盈亏线/P0 分级 + 证据 + `ad.set_bid` 审批信封；
- 06 生成信封后任务停在 `interrupted`；`resume(approve/reject)` 记录审计；
- 快照漂移可拒绝整批（`check_drift`）；
- Phase 2 的 apply 为 **dry-run**，不改平台后台。

#### CLI

```bash
python -m runtime run "帮我看下巴西站滑板车类目的市场容量和价格带"
python -m runtime run "广告 ROAS 太低，怎么降预算"                  # exit 2，停在审批
python -m runtime run "广告 ROAS 太低，怎么降预算" --decision approve  # exit 0，completed
```

#### 测试

- `python -m unittest discover -s runtime/tests` → **90 个测试通过**
- 现有 04 mock 渲染测试继续通过

#### 边界

1. 内存存储、单进程；Phase 3 换 Postgres；
2. 03/04/05/07 暂为 `blocked`，不假装成功；
3. 审批通过后只做 dry-run，真实执行由底座事务 apply 接管；
4. 不改变工具箱独立使用的用法。

---

## [v0.6] — 2026-11-18

### Agent Runtime 平台核心（可选层）

参考 `Multi-Agent-E-commerce-System` 的编排/审批/引用/评测架构，抽出**不依赖第三方库**的平台核心，
为后续"多智能体 + 意图识别 + 路由分发"做准备。**没有把它的 9 服务底座搬进本仓库**。

#### 新增 `runtime/`

| 文件 | 内容 |
|---|---|
| `contracts.py` | `AgentSpec` / `RouteDecision` / `Slice` / `SlicePlan` / `EvalCase` |
| `agent_registry.py` | 7 个 Agent 的能力卡（关键词/工具/输入输出/审批策略）+ 工作流顺序 + 上游关系 |
| `intent_router.py` | 规则优先的意图路由；复合任务识别；LLM 兜底可注入；低置信 → CLARIFY |
| `planner.py` | Manager 切片：≤7 片、依赖声明、执行分层、写动作必须有审批点 |
| `actions.py` | 三层风险 `auto/approval/forbidden` + 动作注册表 + 审批信封 + 快照漂移 |
| `evidence.py` | 证据块 + 正文 `[n]` 引用机械校验 + claim 溯源 |
| `tools.py` | 11 个现有确定性脚本 → 白名单工具（参数列表传递，不执行任意 shell） |
| `cli.py` / `__main__.py` | `python -m runtime route/plan/tools/actions/check-envelope/check-evidence` |
| `tests/` | 40+ 个单元测试（路由/切片/审批/证据/工具），无需 API Key |

#### 新增契约模板

- `Templates/action_approval_envelope.yaml`
- `Templates/evidence_block.yaml`
- `Templates/workflow_plan.yaml`
- `Templates/eval_case.yaml`

#### 新增文档

- `docs/06_Agent_Runtime_Integration.md`：底座选型、保留/替换/剥离清单、7 Agent 接入方式、分阶段路线
- `docs/07_Action_Risk_and_Approval.md`：三层风险、动作注册表、审批信封、漂移与审计
- `docs/08_Evidence_and_Citation_Spec.md`：证据类型、引用规则、失败语义
- `docs/09_Eval_Golden_Scenarios.md`：金标场景、run/score 解耦、机械判据 + LLM judge

#### 边界

1. **工具箱仍可独立使用**：不装运行时也能继续"三个文件跑通"；
2. **不依赖第三方库**：runtime 纯标准库，不发 LLM 请求、不连数据库；
3. **不整包融合**：真正跑任务时，把 runtime 嵌入 fork 的 LangGraph 底座；
4. **执行仍走审批**：对外动作只产出审批信封，绝不直接执行。

---

## [v0.5] — 2026-11-18

### 04 Product Image Agent · 生图执行层 + 多图一致性

借鉴社区 Skill 的可执行出图能力（见 [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md)），
按本仓库的平台/合规/语言规则重写，**没有整包引入外部 Skill**。

#### 新增脚本

| 文件 | 内容 |
|---|---|
| `scripts/render_openai.py` | 单张渲染：OpenAI 兼容 `/images/generations` 与 `/images/edits`；纯标准库；支持 `.env`、`IMAGE_*`/`IMG_*`/`OPENAI_*` 别名、`auto/prompt/image` 三模式、参考图、negative 合并、`job-dir/asset-type` 归类 |
| `scripts/render_prompt_pack.py` | 批量渲染：读 04 的 `output_image_prompt_pack.yaml/.json`；**强制跳过 `layout` / `photo_required`**；`overlay_copy` 不送进模型；参考图缺失时 `[INPUT_MISSING]` 阻塞；出图后默认校验 slot 1，支持 `--check-all` / `--fix`；输出 `render_manifest.json` |
| `scripts/README.md` | 三个脚本的依赖、用法、输出结构、边界与自测命令 |

#### 新增规则卡

| 文件 | 内容 |
|---|---|
| `references/style-lock.md` | **Campaign Style Lock**：10 项字段、Shopee/ML/Amazon 三套默认锁、多图 Prompt 复用规则、自检 |
| `references/product-angle-sheet.md` | **Product Angle Sheet**：何时用、8 角度模板、一致性 Gate、正式图固定引用句、命令 |

#### 模板与 Prompt 更新

- `templates/output_image_prompt_pack.yaml`：新增 `campaign_style_lock`、`angle_sheet`、`render` 区块与 `prompts[].asset_type`；
  Prompt 版本升到 `04-Product-Image v0.5`。
- `templates/input_image_brief.md`：新增可选渲染配置与 Angle Sheet 开关。
- `prompts/00_system.md`：新增 MULTI-IMAGE CONSISTENCY 段。
- `prompts/02_image_prompt_generator.md`：Prompt 公式加入风格锁与 Angle Sheet 引用；自检加入多图一致性项。
- `SKILL.md`：工作流、出图通道 B（可执行脚本）、批量渲染四条硬规则、已知限制。

#### 测试与工程

- `tests/sample_prompt_pack.yaml`：5 个图位的批量渲染夹具（含 layout / photo_required 跳过用例）。
- `tests/test_render.py`：本地 mock 图片 API 一键自测（generations / edits / 图位跳过 / manifest / overlay_copy 不进出图 Prompt）。
- `tests/README.md`：新增渲染脚本测试命令与预期结果（**不需要 API Key**）。
- `.env.example`：可选的图片 API 配置样例。
- `.gitignore`：忽略 `generated-images/`。
- `THIRD_PARTY_NOTICES.md`：登记参考来源与未采用项。

#### 明确保留的边界

1. **图内文字仍后期叠字** —— 渲染器不把 `overlay_copy` 送进图像模型（PT-BR 变音符号易错）；
2. **包装清单图仍必须实拍** —— 批量适配器遇到 `photo_required` 直接跳过；
3. **合规默认开启** —— 未采用外部的"合规默认关闭 + 模拟好评"路线；
4. **不配 API 也能完整使用** —— `auto` 模式自动降级为只输出 Prompt。

---

## [v0.3] — 2026-10-13

补齐 **分析簇（前置链路）**：01 市场分析、02 产品策略。**7 个 Agent 模块全部完成。**

本次还落地了三项此前标记为"待确认"的决策，并新增差异登记文档。

### 决策确认

| # | 事项 | 结论 |
|---|---|---|
| 1 | **Agent 编号重排** | ✅ **接受**。按工作簇：`01-02` 分析簇 → `03-04-05` 创意簇 → `06-07` 运营簇 |
| 2 | **SOP 的「9 图生成逻辑」原始清单** | ✅ **采用本仓库推导的 9 图框架**，不再等待原文。推导逻辑（三步）已写入 [`04 README`](./Agents/04_Product_Image_Agent/README.md) 第二节 |
| 3 | **SOP 灰产部分是否留附录** | ✅ **留，但做成"登记表"而非"操作指南"**。见下方新增文档 |

### 新增文档

#### `docs/05_SOP_Gap_Register.md` — SOP 差异登记表

登记原始 SOP 中未实现的内容：**原始提及了什么 → 为什么未实现 → 是否有合规替代 → 替代落在哪**。

- 覆盖 10 项，分三类：数据与评价类 / 内容与参数类 / 运营节奏类
- 另列出本仓库做的 **7 处"加法"**（SOP 没有、我们补的）
- 同时给出使用者的自查方法（三个问题判断某个动作是否该做）

> ⚠️ **安全设计决策**：本文档只登记到"**结论层级**"，**不复述操作细节**。
> 原因：开源仓库含违规操作指引会被平台风控识别，也会让使用者连带受损。**登记的目的是透明，不是传播。**

### 新增模块

#### `Agents/01_Market_Research_Agent`

⚠️ **这个模块和前面五个不一样：它带脚本。**

之前的判断是"01 的瓶颈在数据获取，不在 Prompt"。既然认了这个判断，就把脚本一起做了——否则只是把坑留给了使用者。

| 文件 | 内容 |
|---|---|
| `scripts/shaduola_parser.py` | 格式标准化：货币符号 / 千分位 / 欧式小数 / 中文数量单位 / 空值标记 / 日期 → 统一 JSON；列名模糊匹配 + `--mapping` 手动指定；`--profile` 只看识别结果 |
| `scripts/market_metrics.py` | 指标计算：市场容量 / 品牌与卖家集中度（CR3·CR10·HHI）/ 价格分箱 + **波谷检测** / 配置交叉表（四维判断） |
| `scripts/make_sample.py` | 生成带脏数据的样本，让使用者一 clone 就能跑通 |
| `scripts/README.md` | 用法 + 算法说明（含为什么不做平滑） |
| `samples/` | 样本 CSV + 标准化 JSON + 指标报告（含**预期结果表**，用于验证环境） |
| `prompts/00_system.md` | 角色 + SOP 判断阈值 + M1–M5 合规守卫 |
| `prompts/01_category_precheck.md` | SOP 1.1 前置判断（含高风险类目的**利润承载力检验**） |
| `prompts/02_market_analysis.md` | SOP 1.2–1.6（容量 / 集中度 / 价格带 / 配置 / 竞品） |
| `templates/` | input_category_research · output_market_analysis |
| `examples/patinete_eletrico_market.md` | 可复现案例（三条命令核对每个数字） |

**四个核心设计**：

1. **能算的别让模型猜** —— 集中度/分箱/交叉表是确定性计算，交脚本；Agent 只解读"这些数字意味着什么"
2. **波谷检测不平滑** —— 3 点滑动平均会抹掉陡峭波谷（样本里 `799→618→1120` 的波谷被平均成 `639→846→912`，波谷消失）
3. **前置判断能叫停** —— SOP 1.1 说"没有供应链/售后能力/价格优势，即使市场好也不一定适合做"，所以判定不通过时**停止，不做下游分析**
4. **CR-n 的陷阱自动提示** —— 主体数 ≤ n 时 CR-n 恒为 100%，脚本自动提示改用 CR3 与 HHI

#### `Agents/02_Product_Strategy_Agent`

| 文件 | 内容 |
|---|---|
| `prompts/00_system.md` | 角色 + 定价与 SKU 规则 + S1–S5 合规守卫 |
| `prompts/01_product_decision.md` | SOP 1.7 + 3.1：定位 / 配置 / **主推卖点收敛（唯一）** / 风险规避 / 上架前 8 问 |
| `prompts/02_pricing_and_sku.md` | SOP 1.9 + 3.2：定价公式 + 逐 SKU 验算 + SKU 四角色 + 优惠券设计 + 盈亏线 |
| `templates/` | input_strategy_brief · output_product_requirement |
| `examples/patinete_eletrico_strategy.md` | 完整案例（接 01 的输出） |

**三个核心设计**：

1. **`decision_approved` 阻塞机制** —— 本模块**不做选品决策**，只做"把已决策的产品规格化"。未由人确认就往下跑 = 让 Agent 替你做商业决策
2. **主卖点必须唯一** —— 两个并列等于零个。主卖点决定主图打什么字、视频开头放什么镜头
3. **SKU 四角色 + 价格阶梯双向检查** —— 价差过大买家不升级、过小引流款失去意义

### 案例中的两个"自洽巧合"

在做 01、02 的案例时，出现了两处**独立推导指向同一结果**的验证点，都保留在案例里：

| 发现的巧合 | 意义 |
|---|---|
| 波谷检测出的价格带下界 **R$ 1.989,13** vs 定价公式反算的成本可行价 **R$ 1.989,36**，相差 **R$ 0,23** | 一条是纯数学（销量曲线），一条是纯财务（成本结构）→ 该价位同时满足市场结构与成本可行 |
| 主推款毛利余量 **R$ 98,95** vs 拟发券面额 **R$ 100**，相差 **R$ 1,05** | 市场给的价格（2.199）与成本要求（1.989）之间的空间，刚好够发一张"缩小价格差距"的券 |

> 这两个数字不是凑的，是"市场愿意给多少 + 成本需要多少"共同决定的结果。**它们出现，说明这套方法论内部是自洽的。**

### 新增认知

| # | 认知 | 证据 |
|---|---|---|
| 1 | **CR 高 ≠ 垄断** | 案例中品牌 CR3 = 74,1% 看似很高，但**前三名全是白牌** → 买家不认品牌，新店仍有空间 |
| 2 | **要看份额与商品数的比值** | 某卖家销售额占比 8,5% 但商品数占 12% → **占位型而非效率型**，是可超越对象 |
| 3 | **"高配"未必高毛利** | 800W 成本涨 34,8% 但售价只涨 22,7% → 高配净利率 32,3% **低于主推 36,5%** |
| 4 | **"前期降毛利养权重"的自由度取决于余量** | 案例中 R$ 1.999 的净利率仍有 32,2%，其实没真降——因为定价本身有充足余量 |
| 5 | **引流款低于目标毛利 ≠ 战略亏损** | 27,5% 低于 32% 目标但仍在盈亏线（临界价 R$ 1.113）之上 → 无需标注亏损与退出条件 |

### 文档更新

- `README.md`：Agent 全景表（7/7 完成）· 目录树（含 `scripts/`、`samples/`）· 闭环 mermaid 图（含 01/02）· 路线图 · badge → v0.3 · 合规声明增加差异登记表入口
- `Agents/README.md`：v0.3 完成清单 + **正向契约表**（谁必须给谁什么、缺失时报什么错）
- `docs/00`：新增分析簇模块边界 + 各模块"做什么/不做什么"
- `docs/03`：顶部增加与 `05` 的分工说明（本文给"怎么换"，05 给"为什么不做"）
- `docs/04` / `Templates/output_qa_checklist.md`：补 01/02 的自检段（待补）
- `ROADMAP.md`：v0.3 标记完成，关闭技术债 #1、#4，新增 #7–#9
- `Examples/README.md`：案例索引更新

---

## [v0.2] — 2026-10-13

完成 **Phase 2 运营簇**：新增 06 广告优化、07 评论分析两个模块，并把整套流程闭合成环。

### 新增模块

#### `Agents/06_Advertising_Optimization_Agent`

| 文件 | 内容 |
|---|---|
| `README.md` | 四类漏斗诊断表 · 健康基准线 · **盈亏线 ROAS 算法** · SOP 两条实战技巧（不暂停广告 / 改主图解 bug） |
| `prompts/00_system.md` | 角色 + 基准线 + 漏斗判定顺序（硬规则：前段达标前禁止调出价）+ G1–G5 合规守卫 |
| `prompts/01_funnel_diagnosis.md` | 逐广告组四步判定 → 动作清单（**强制输出"本轮明确不动的部分"**）+ 解 bug 流程 + 复测方案 |
| `prompts/02_budget_roi_model.md` | 盈亏线核算 + ROAS 敏感性表 + 达标线差距分析 + 预算×ROI 双变量模型 + 分时段节律 |
| `templates/input_ad_data.md` | 广告数据 + 成本结构（含数据质量门槛） |
| `templates/output_ad_action_plan.md` | 动作清单（下游：03/04/07） |
| `examples/powerbank_20000mah_ads.md` | 真实案例：4 个广告组覆盖全部四类症状，整体 ROAS 1,84 亏损 |

**三个核心设计**：

1. **漏斗判定顺序不可跳**：CTR → 加购率 → 转化率 → ROAS。**只有前段全部达标，才允许建议调整出价。**
2. **盈亏线优先于基准线**：基准线判断"哪一环不健康"，盈亏线判断"赚不赚钱"。两者都要看——因为**漏斗全达标也可能亏钱**。
3. **数据质量门槛**：曝光 < 1,000 拒绝分析；成本结构缺失则拒绝输出任何 ROI 结论。

#### `Agents/07_Review_Analysis_Agent`

| 文件 | 内容 |
|---|---|
| `README.md` | 八类差评归因 · **误解型为何单独拎出来** · 三类回流（详情页修补 / 参数红线 / 卖点排序）· 合规边界 |
| `prompts/00_system.md` | 角色 + 八类归因定义 + 误解型判定标准（"描述无误仍不满 = 描述的问题"）+ C1–C5 合规守卫 |
| `prompts/01_classify_and_attribute.md` | 好评 5 维度 + 差评八类归因 + 卖点频次×情感强度排序 + 竞品对比 + SOP 七问 |
| `prompts/02_misunderstanding_detector.md` | **误解型判定三分类**（缺失说明 / 说明不醒目 / 买家未阅读）+ 详情页修补文案 + 参数红线 |
| `templates/input_review_batch.md` | 评论批量导入（含样本量门槛 ≥ 20） |
| `templates/output_review_insights.md` | 评论洞察报告（下游：03/04） |
| `examples/electric_scooter_reviews.md` | 真实案例：128 条评论，**可修复差评 84,6%**，误解型占 38,5% |

**三个核心设计**：

1. **误解型差评单独拎出来**：它是唯一一类"改一句话就能消除"的差评——成本接近零、改完立即生效，ROI 最高。
2. **判定三分类**：缺失说明 → 新增条目；说明不醒目 → 前置；买家未阅读 → **换成图**（文字会被跳过，图不会）。
3. **配件类误解必须用图**：2 条配件差评都因买家未读参数表——补发配件是错的，正确动作是包装清单图标注"不含什么"。

### 新增闭环案例

#### `Examples/03_Closed_Loop/`

演示 SOP 第三章"数据复盘 → 反过来优化前面四个环节"的完整机制：

- **广告侧回流**（Power Bank）：06 诊断 → 定位瓶颈是转化率而非点击率 → 干预 → 7 天复测 → **净贡献 −R$ 235,56 → +R$ 83,90**
- **评论侧回流**（Electric Scooter）：07 诊断 → 84,6% 差评可修 → 回流 03/04 → 14–30 天复测
- **反直觉的坑**：修 CTR 最差的组 → 亏损扩大到 −R$ 335,26；放大曝光 → 同比例放大亏损
- **复测指标选择原则**：要选"改动能控制"的指标（广告看 ROAS，文案看误解型占比，都不看总销量）

### 新增设计机制

| 机制 | 说明 |
|---|---|
| **盈亏线 ROAS** | 分母减去佣金/广告/退货/毛利四项百分比；`ROAS < 盈亏线` 即每单亏钱 |
| **达标线 vs 盈亏线** | 显式指出"定价预留广告成本 7.5% 对应 ROAS 13,33，而实际投放常见 3–8"的差距 |
| **漏斗判定顺序为硬规则** | 前段未达标就调出价 = 违规建议，Prompt 必须拒绝 |
| **"本轮明确不动的部分"** | 06 强制输出项——防止修 A 环节时顺手改坏 B 环节 |
| **误解型三分类** | 把"想消除差评"的诉求，转换成"补说明 / 前置 / 换成图"三个可执行动作 |
| **复测指标可归因** | 选改动能控制的指标：广告看 ROAS，文案看误解型占比 |

### 文档更新

- `README.md`：Agent 全景表更新（5 个已完成）· 目录树 · 闭环 mermaid 图 · 路线图
- `Agents/README.md`：拆分 v0.1/v0.2 已完成清单 + 新增**回流契约**表
- `docs/04_Result_Checklist.md`：新增 F（06）/ G（07）/ H（闭环）三段自检
- `Templates/output_qa_checklist.md`：同步新增 F/G/H 段
- `Examples/README.md`：新增闭环案例索引 + 五款产品覆盖表（现每款被至少两个模块分析过）
- `ROADMAP.md`：v0.1/v0.2 标记完成，新增技术债第 5、6 项

### 合规处理（延续 v0.1 原则）

07 模块涉及 SOP 3.7 的差评处理流程，其中以下动作**未搬运**：

| SOP 原始表述 | 处理 |
|---|---|
| 联系客户删差评，说删了会很快退款并给补偿 | ❌ 移除（以利益诱导删评） |
| 产品有虚标的话可以说是说明书打包错了 | ❌ 移除（以不实理由解释参数不符） |
| 先给差评点举报，有机会消除差评 | ⚠️ 保留"单条明显违规评论可正常申诉"，移除"组织性举报" |
| **反向优化详情页、客服话术或产品** | ✅ **保留并强化为 07 的核心输出** |

详见 [`docs/03_Compliance_Guard.md`](./docs/03_Compliance_Guard.md)。

### 已知问题

| # | 问题 | 状态 |
|---|---|---|
| 7 | 06/07 的输入依赖手工填表（广告数据 / 评论数据需人工导出） | V2 接入 API 后消除 |
| 8 | 复盘数据无法自动回流，`iterate` 需人工粘贴 | v1.0 串联后消除 |

---

## [v0.1] — 2026-10-13

首个版本。完成 **Phase 1** 三个创意簇 Agent。

### 新增

**核心模块（Phase 1）**

| 模块 | 内容 |
|---|---|
| `Agents/03_Listing_Creative_Agent` | 关键词七类分词 · 标题五段公式 · 详情页 7 段 · 卖点分层 · 参数一致性校验 |
| `Agents/04_Product_Image_Agent` | 9 图内容规划 · 逐图出图 Prompt · 负面 Prompt 库 · 图片合规守卫 |
| `Agents/05_Product_Video_Agent` | 15s/30s 双版本脚本 · 分镜表 · AI 视频 Prompt · 配音稿 · 字幕 · 静音可读性检查 |

**模块占位说明（Phase 2）**

`01 Market Research` · `02 Product Strategy` · `06 Advertising Optimization` · `07 Review Analysis`

**方法论文档**

| 文件 | 内容 |
|---|---|
| `docs/00_Architecture_SOP_to_Agent.md` | SOP 38 页 → 7 个 Agent 的完整拆解表（含三级分级法） |
| `docs/01_Prompt_Design_Guide.md` | Prompt 五要素规范 + 四条硬规则 + 输出语言策略 |
| `docs/02_Platform_Output_Spec.md` | Shopee / ML / Amazon / TikTok Shop / Shopify 字段硬指标 |
| `docs/03_Compliance_Guard.md` | 合规红线 + 灰产动作改写对照表 + 卖点真实化映射表 |
| `docs/04_Result_Checklist.md` | 六段式交付自检清单 |

**模板库**（顶层 `Templates/`）

`product_brief_template.md`（模块间通信契约）· `keyword_analysis_template.md` · `cost_pricing_template.md`（含可验算的定价公式）· `output_qa_checklist.md`（可打印版）

**案例库**

| 案例 | 覆盖模块 | 重点 |
|---|---|---|
| `Examples/01_Patinete_Eletrico_500W` | 03 → 04 → 05 | 端到端串联 · 跨平台 120→60 字符压缩 · 跨模块一致性校验 |
| `Examples/02_Thermal_Bag` | 03（iterate） | 广告数据诊断 → 最小改动回改闭环 |
| `Agents/03.../examples/powerbank_20000mah.md` | 03 | 评论反向修复 Listing |
| `Agents/04.../examples/pet_carrier.md` | 04 | ML 与 Shopee 主图规范冲突处理 |
| `Agents/05.../examples/air_fryer.md` | 05 | 钩子从差评来 · 静音可读性 |

### 结构变更

**Agent 编号重排。** 原始规划（来自制作说明）为：

```
01 Market Research → 02 Product Strategy → 03 Listing Creative
→ 04 Advertising → 05 Review → 06 Product Video
```

v0.1 改为按**工作簇**编号：

```
03 Listing Creative ─┐
04 Product Image     ├─ 创意簇（文案 → 图 → 视频，天然串联）
05 Product Video     ┘

06 Advertising ─┐
07 Review      ─┴─ 运营簇（广告 → 评论）
```

**调整理由**：让天然串联的模块编号连续，便于引用；创意簇与运营簇在依赖关系上互不交叉。
**影响**：`Product Video` 从 `06` 变为 `05`；`Advertising` 从 `04` 变为 `06`；`Review` 从 `05` 变为 `07`；新增 `04 Product Image`（原规划中未独立编号）。

### 新增设计机制

| 机制 | 说明 |
|---|---|
| **模块间通信契约** | 03 → 04/05 通过 `product_brief` 传递结构化字段，防止信息损耗 |
| **阻塞字段** | `core_selling_point` / `forbidden_words` 等为空时，下游模块必须报错，不得推测 |
| **中文/母语分离** | 买家可见文本用目标市场母语，内部备注用中文，Prompt 强制区分 |
| **参数唯一来源** | 所有输出中的数值必须溯源到 `spec_table`，否则删除并记录 `[PARAM_DROPPED]` |
| **强制输出合规扫描区块** | 无命中时也必须写"无命中"，以确认扫描确实执行 |
| **负面 Prompt 作为合规工具** | 不防水产品的场景图负面词必含 `rain, water, swimming pool` |

### 合规处理

原始 SOP 中以下内容**未搬运、未实现**，并给出合规替代：

| SOP 原始表述 | 处理 |
|---|---|
| 刷单 / 测评 / 建虚假 SKU 规避风控 | ❌ 移除 → 真实低价促销 + 非公开优惠券 + 官方邀评 |
| 组织给竞品上差评 | ❌ 移除 → 竞品差评归因 → 己方防御性说明 |
| "可控范围内虚假宣传" | ❌ 移除 → 卖点真实化映射表 |
| 优惠券诱导评价 / 改图片 MD5 | ❌ 移除 → 官方邀评通道 |
| 参数虚标后解释为"说明书打包错了" | ❌ 移除 → 参数三处一致性校验 |

详见 [`docs/03_Compliance_Guard.md`](./docs/03_Compliance_Guard.md)。

### 已知问题

| # | 问题 | 状态 |
|---|---|---|
| 1 | SOP 的「9 张电商图片生成逻辑」具体清单在 PDF 中为图片形式，文本提取未能还原；当前 9 图框架为基于详情页结构的**推导版** | 待 SOP 作者补充后校准 |
| 2 | SOP 原文写详情页"8 个部分"但只列出 7 项 | 本仓库按 7 段执行，待确认 |
| 3 | 平台字数 / 字段规则为编写时公开规则，可能滞后 | 已在多处标注"发布前复核" |
| 4 | `Examples/02_Thermal_Bag` 中同时改动了主图与标题，无法归因 | 已在案例内明确标注为方法论瑕疵并给出分步方案 |

---

## 待发布

### v0.2（计划）

- `06 Advertising Optimization Agent`：四类漏斗诊断 + 基准线校验 + 预算节律
- `07 Review Analysis Agent`：评论归因 + 误解型差评识别 → 详情页修补建议

### v0.3（计划）

- `01 Market Research Agent`：需先解决数据获取（解析脚本 + 指标计算）
- `02 Product Strategy Agent`：依赖 01

详见 [`ROADMAP.md`](./ROADMAP.md)。
