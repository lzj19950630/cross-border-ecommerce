# 16 · 多用户与角色

> 适用版本：v0.29
> 单租户 API Key 升级为多用户 + 角色 + 任务归属。

---

## 一、配置

### 单密钥（兼容旧用法）

```bash
export RUNTIME_API_KEY=strong-key
```

→ 用户 `api`，角色 `admin`。

### 多用户

```bash
export RUNTIME_API_KEYS='{
  "acme-key": "acme:alice:admin",
  "beta-key": "beta:bob:operator"
}'
```

格式：`tenant:name:role`；两段 `name:role` 兼容（tenant 为空）。

也支持对象格式：

```json
{"op-key": {"name": "bob", "role": "operator"}}
```

Key 只从环境变量读取，不落仓库。

---

## 二、JWT 登录（v0.19）

### 配置

```bash
export RUNTIME_JWT_SECRET=change-me
export RUNTIME_USERS='{
  "alice": {"password_bcrypt": "$2b$...", "role": "admin"},
  "bob":   {"password_bcrypt": "$2b$...", "role": "operator"}
}'
```

生成密码哈希（推荐 bcrypt）：

```bash
python -c "from runtime.auth import hash_password_bcrypt; print(hash_password_bcrypt('your-password'))"
```

旧配置仍支持 `password_sha256`（不推荐用于新用户）。

### 登录

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login   -H 'Content-Type: application/json'   -d '{"username":"alice","password":"your-password"}'
```

返回：

```json
{"token": "<jwt>", "name": "alice", "role": "admin"}
```

后续请求：

```bash
curl -H "Authorization: Bearer <jwt>" http://127.0.0.1:8000/api/tasks
```

- JWT HS256，默认 1 小时过期；
- `POST /api/auth/refresh`（Bearer 未过期 token）→ 新 token，**旧 token 立即吊销**；
- `POST /api/auth/logout` → 吊销当前 token；
- 吊销记录存 InMemory/SQLite/Postgres，按 exp 清理；
- Web 控制台新增用户名/密码登录；
- 无 JWT 配置时仍可用 API Key。

---

## 三、动作级审批权限（v0.19）

```bash
export RUNTIME_ACTION_ROLES='{
  "product.update_price": ["admin"],
  "ad.*": ["admin", "operator"]
}'
```

- 精确 action 或通配前缀（`ad.*`）；
- 未配置的动作默认 `admin` / `operator`；
- 审批前检查信封内**每个** action；角色不足 → 403；
- 审计 `decided_by` 记录审批人。

---

## 四、代理 SSO（v0.23）

```bash
export RUNTIME_PROXY_AUTH_SECRET=proxy-secret
```

反代（oauth2-proxy / authentik / Authelia）注入：

```text
X-Proxy-Auth: proxy-secret
X-Auth-Request-User: alice
X-Auth-Request-Role: admin
```

- 只有 secret 匹配才信任头；
- 反代必须删除客户端传入的同名头；
- 未提供 role 时默认 viewer。

---

## 五、角色

| 角色 | 创建任务 | 审批 | 查看任务 | 评测 |
|---|---|---|---|---|
| `admin` | ✅ | ✅ | 全部 | ✅ |
| `operator` | ✅ | ✅ | 自己的 | ✅ |
| `viewer` | ❌ | ❌ | 自己的 | ❌ |

- 任务创建时写入 `owner` 和 `tenant_id`；
- 有 tenant 的用户只能看到同 tenant 的任务；
- 非 admin 只能看到/访问 `owner == 自己` 的任务；
- 审批审计 `decided_by` 记录用户名；
- 无认证时 `owner=anonymous`，所有接口开放（仅本地）。

---

## 七、API 行为

| 端点 | admin | operator | viewer |
|---|---|---|---|
| `POST /api/tasks` | ✅ | ✅ | 403 |
| `GET /api/tasks` | 全部 | 自己的 | 自己的 |
| `GET /api/tasks/{id}` | ✅ | 自己的 | 自己的 |
| `POST /api/tasks/{id}/resume` | ✅ | 自己的 | 403 |
| `POST /api/tasks/{id}/cancel` | ✅ | 自己的 | 403 |
| `GET /api/audits/{id}` | ✅ | 自己的 | 自己的 |
| `POST /api/evals` | ✅ | ✅ | 403 |
| `GET /api/health` | 公开 | 公开 | 公开 |

---

## 八、Web 控制台

右上角输入 API Key：

- 存 localStorage；
- 每次 API 请求带 `Authorization: Bearer <key>`；
- operator/viewer 只看到自己的任务；
- viewer 没有批准/拒绝按钮（后端也会 403）。

---

## 九、任务归属迁移

旧任务 `owner=""`：

- admin 可见；
- operator/viewer 不可见（不会误暴露历史任务）；
- 如需迁移，给旧任务补 owner 后再交给普通用户。

---

## 十、测试

`runtime/tests/test_api_roles.py` 覆盖：

- viewer 创建 → 403；
- operator 只看到自己的任务；
- operator 读别人的任务 → 403；
- operator 审批自己的任务 → 审计 `decided_by=bob`；
- viewer 审批/评测 → 403；
- health 公开。

---

## 十一、边界

- JWT 已支持；无 SSO / 刷新 token / 密码重置；新用户请用 bcrypt，旧 `password_sha256` 仅兼容。
- API Key 仍是静态密钥；
- 没有按角色细分的动作权限（如只允许 admin 改价）；
- 没有审计导出权限控制；
- Key 轮换需要重启服务（环境变量）。

---

**相关**：[HTTP API](11_HTTP_API.md) · [生产清单](15_Production_Checklist.md) · [运维手册](10_Runtime_Operations.md)
