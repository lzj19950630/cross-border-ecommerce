# 11 · Runtime HTTP API

> 启动一个最小 FastAPI 服务，把 7 Agent 编排暴露成 HTTP。
> 适用版本：v0.30。

---

## 一、启动

```bash
# 方式 1：内置命令
python -m runtime serve --host 127.0.0.1 --port 8000

# 方式 2：uvicorn factory
uvicorn runtime.api:create_app --factory --host 127.0.0.1 --port 8000

# LangGraph supervisor（interrupt 审批断点，进程内 MemorySaver）
python -m runtime serve --engine supervisor --port 8000

# 审批通过后 POST 到外部执行器（默认 dry-run）
python -m runtime serve --apply-webhook http://127.0.0.1:9000/apply

# LLM 创意层
python -m runtime serve --creative --port 8000
```

- 默认存储：`.runtime/runtime.db`（SQLite）
- 指定 SQLite：`--db ./data/runtime.db`
- 指定数据库 URL：

```bash
# SQLite
RUNTIME_DB_URL=sqlite:///./runtime.db python -m runtime serve

# Postgres（需安装 psycopg）
RUNTIME_DB_URL=postgresql+psycopg://user:pass@localhost:5432/runtime python -m runtime serve
```

- 执行器：

```bash
python -m runtime serve --executor langgraph    # 默认 auto：优先 LangGraph
python -m runtime serve --executor sequential   # 纯顺序
```

---

## 二、Web 控制台

启动后打开 `http://127.0.0.1:8000/`：

- 新建任务（request / inputs JSON / 自动审批）；
- 任务列表与详情；
- 切片状态、审批信封（批准/拒绝）；
- 产物 / 证据 JSON；
- 审计查询；
- **运行评测**按钮（显示 pass/fail 与每条机械判据）；
- Agent 管理：`SKILL.md` / `prompts/` / `references/` / `templates/` 在线查看/编辑（保存需 admin，自动备份）；
- 任务详情：全链路追踪（切片时间轴）、Checkpoint 历史快照。

静态页面在 `cross-border-ecommerce-admin/index.html`，**零构建、同源托管**，无认证/CORS（仅本地原型）。

---

## 三、认证与 CORS

### API Key（可选）

```bash
export RUNTIME_API_KEY=your-strong-key
python -m runtime serve --port 8000
```

- `/api/*`（除 `/api/health`）需要：
  - `Authorization: Bearer <key>` 或
  - `X-API-Key: <key>`；
- `/` 与 `/static` 保持公开；
- Web 控制台右上角输入 Key（存 localStorage）。

### JWT 登录

```bash
export RUNTIME_JWT_SECRET=change-me
export RUNTIME_USERS='{"alice":{"password_bcrypt":"$2b$...","role":"admin"}}'
```

```bash
curl -X POST /api/auth/login -d '{"username":"alice","password":"..."}'
# → {"token":"<jwt>","name":"alice","role":"admin"}
```

后续带 `Authorization: Bearer <jwt>`。Web 控制台也有登录表单。

### 多用户

```bash
export RUNTIME_API_KEYS='{"acme-key":"acme:alice:admin","beta-key":"beta:bob:operator"}'
```

角色：`admin` / `operator` / `viewer`；详见 [16_Multi_User_and_Roles.md](16_Multi_User_and_Roles.md)。

### 限流

```bash
export RUNTIME_RATE_LIMIT=120   # 每分钟请求数
```

- 按 token / API Key / IP 分桶；
- 超限返回 429 + `Retry-After`；
- `/api/health` 不限流；
- 单进程内存实现，多实例请用网关/Redis。

### 幂等

```bash
POST /api/tasks
Idempotency-Key: <唯一键>
```

同一 tenant+owner+key 返回原任务，响应带 `idempotent_replay: true`。

### 代理 SSO（oauth2-proxy / authentik）

```bash
export RUNTIME_PROXY_AUTH_SECRET=proxy-secret
```

反代注入：

```text
X-Proxy-Auth: proxy-secret
X-Auth-Request-User: alice
X-Auth-Request-Role: admin
```

- 只有 `X-Proxy-Auth` 匹配时才信任用户/角色头；
- 反代必须剥离客户端自带的同名头；
- 角色仍为 admin/operator/viewer。

### CORS

```bash
export RUNTIME_CORS_ORIGINS=https://console.example.com
```

不设置 = 同源访问（推荐）；跨域才需要白名单。

---

## 四、端点

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查 + 版本 + 执行器 |
| POST | `/api/auth/login` | 用户名/密码 → JWT |
| POST | `/api/auth/refresh` | 未过期 token → 新 JWT（旧 token 吊销） |
| POST | `/api/auth/logout` | 吊销当前 JWT |
| POST | `/api/tasks` | 创建并执行任务 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务详情 |
| GET | `/api/tasks/{id}/approvals` | 待审批信封 |
| POST | `/api/tasks/{id}/resume` | 批准/拒绝 |
| GET | `/api/tasks/{id}/trace` | 全链路事件时间轴 |
| GET | `/api/tasks/{id}/checkpoints` | LangGraph checkpoint 历史 |
| GET | `/api/audits/{id}` | 审批审计 |
| GET | `/api/metrics` | JSON 指标 |
| GET | `/metrics` | Prometheus 文本指标 |
| GET | `/api/alerts` | 失败/阻塞 + 审批积压告警 |
| GET | `/api/tenants` | 租户列表（全局管理员） |
| POST | `/api/tenants` | 创建租户 |
| DELETE | `/api/tenants/{id}` | 删除租户 |
| GET | `/api/users` | 用户列表 |
| POST | `/api/users` | 创建用户 |
| DELETE | `/api/users/{username}` | 删除用户 |
| PUT | `/api/users/{username}/password` | 重置密码 |
| GET | `/api/providers` | 租户模型配置（脱敏） |
| PUT | `/api/providers/{name}` | 保存租户模型配置（admin） |
| DELETE | `/api/providers/{name}` | 删除租户模型配置（admin） |
| POST | `/api/providers/{name}/test` | 测试模型连接（真实调用） |
| GET | `/api/agents` | Agent 能力卡 + 文件清单 |
| GET | `/api/agents/{key}` | 单 Agent 详情 |
| GET | `/api/agents/{key}/file` | 读取白名单文件 |
| PUT | `/api/agents/{key}/file` | 编辑文件（admin，自动备份） |
| GET | `/api/agents/edits` | Agent 编辑日志（admin） |
| GET | `/api/tasks/{id}/export` | 导出 task + audits JSON |
| POST | `/api/tasks/{id}/cancel` | 取消任务（清空待审批） |
| POST | `/api/tasks/{id}/delivery/review` | 机器交付审核 |
| POST | `/api/tasks/{id}/delivery/decision` | 人工交付决定 |
| GET | `/api/tasks/{id}/archive` | 下载交付 ZIP（需 passed） |
| GET | `/api/tools` | 工具白名单 |
| GET | `/api/actions` | 动作风险注册表 |
| POST | `/api/evals` | 跑确定性评测（Templates/eval_case.yaml） |
| GET | `/api/evals` | 最近 20 次评测历史 |

---

## 五、示例

### 健康检查

```bash
curl http://127.0.0.1:8000/api/health
```

```json
{"status":"ok","version":"0.30.0","engine":"supervisor","executor":"sequential","creative":false,"auth":true,"proxy_auth":false,"rate_limit":120,"cors":false}
```

### 创建一个 01 市场分析任务

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"request":"帮我看下巴西站滑板车类目的市场容量和价格带"}'
```

### 创建 06 广告任务（会停在审批）

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"request":"广告 ROAS 太低，怎么降预算"}'
```

返回：

```json
{
  "thread_id": "...",
  "status": "interrupted",
  "pending_envelopes": ["ad-..."]
}
```

### 查看待审批

```bash
curl http://127.0.0.1:8000/api/tasks/<thread_id>/approvals
```

### 批准并续跑

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/<thread_id>/resume \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approve","comment":"同意降出价"}'
```

### 一步完成

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"request":"广告 ROAS 太低，怎么降预算","decision":"approve"}'
```

### 输入覆盖

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "request":"广告 ROAS 太低，怎么降预算",
    "inputs":{"price":99.9,"product_cost":48,"commission":14,"tax":8}
  }'
```

---

## 六、请求/响应约定

### POST /api/tasks

```json
{
  "request": "string（必填）",
  "inputs": {},
  "thread_id": "可选，指定任务 ID",
  "decision": "none | approve | reject",
  "comment": "可选"
}
```

`decision` 不为 `none` 且任务停在审批时，服务端会立即 `resume`。

### POST /api/tasks/{id}/resume

```json
{
  "decision": "approve | reject",
  "comment": "可选",
  "decided_by": "api"
}
```

---

## 七、Agent 管理与追踪

### Agent / Skill / Prompt

```bash
# 列出 7 个 Agent（能力卡 + 文件清单）
curl http://127.0.0.1:8000/api/agents

# 读取
curl 'http://127.0.0.1:8000/api/agents/product_image/file?path=prompts/00_system.md'

# 保存（admin；自动备份到 .runtime/agent_backups/）
curl -X PUT http://127.0.0.1:8000/api/agents/product_image/file \
  -H 'Content-Type: application/json' \
  -d '{"path":"prompts/00_system.md","content":"..."}'

# 编辑日志
curl http://127.0.0.1:8000/api/agents/edits
```

- 可访问：`SKILL.md` / `README.md`，以及 `prompts/`、`references/`、`templates/` 下的 `.md/.yaml/.yml/.json/.txt`；
- 仅允许覆盖已存在文件；读 512KB / 写 256KB；路径白名单 + 防穿越；
- 写接口仅 `admin`；未启用认证时视为本地管理员。

### 全链路追踪

```bash
curl http://127.0.0.1:8000/api/tasks/<thread_id>/trace
```

返回 `events`（route / plan / slice / audit 按时间排序）+ `slices`、`messages`、`audits` 原始结构。

### Checkpoint 历史

```bash
curl http://127.0.0.1:8000/api/tasks/<thread_id>/checkpoints
```

- 只读 `.runtime/checkpoints.db`（`SqliteSaver.list()`）；
- 每个快照含 `checkpoint_id / step / source / ts / state / has_interrupt`；
- `available=false` 表示未启用 sqlite checkpointer 或 DB 不存在；
- 历史快照当前仅查看，不支持回滚；续跑走审批 / `resume`。

---

## 八、边界

- **认证**：支持 API Key 与 JWT（admin/operator/viewer）；无 SSO/刷新 token/密码重置；
- **无 CORS 配置**：浏览器跨域需自行加 middleware；
- **apply 是 dry-run**：HTTP 审批不会改平台后台；
- **SQLite 单机**：多实例请用 `RUNTIME_DB_URL` 切 Postgres；
- **Supervisor 同进程用 MemorySaver**；跨进程 API 进程重启后会自动回退任务 checkpoint 续跑（v0.13）。
- **Webhook apply**：`--apply-webhook` 可让审批通过后真的 POST 到执行器；默认 dry-run。
- **simple 引擎**支持跨进程 resume；supervisor 引擎适合单进程 API/长驻服务。
- **Checkpoint 历史**：`/api/tasks/{id}/checkpoints` 仅查看，不支持回滚；回滚需同时回滚外部 TaskRecord，暂未实现。
- **Agent 在线编辑**：只覆盖已有文件；注册表（keywords/tools/schema）仍为代码内只读。

---

**相关**：[运行时 README](../runtime/README.md) · [运维手册](10_Runtime_Operations.md) · [集成方案](06_Agent_Runtime_Integration.md)
