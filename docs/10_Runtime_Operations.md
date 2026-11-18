# 10 · Runtime 运维手册

> 适用版本：v0.26 · 运行时：`runtime/`（SQLite/SQLAlchemy + simple/supervisor + LLM 创意层 + Web 控制台 + 平台适配器 + 多用户）
> 目标：让人能跑、能看、能审批、能导出、能排错。

---

## 一、命令总览

| 命令 | 作用 |
|---|---|
| `python -m runtime doctor` | 环境/脚本/样本/SQLite/可选依赖自检 |
| `python -m runtime route "..."` | 只做意图识别 |
| `python -m runtime plan "..."` | 意图 + 切片计划 |
| `python -m runtime run "..."` | 执行任务（默认 simple 引擎；可 `--engine supervisor`） |
| `python -m runtime resume <id> --decision approve/reject` | 审批并发起续跑 |
| `python -m runtime task <id>` | 查看单个任务 |
| `python -m runtime serve --engine supervisor` | 启动 LangGraph supervisor API |
| `--apply-webhook <url>` | 审批通过后 POST 到外部执行器（默认 dry-run） |
| `--apply-adapter <yaml>` | 按平台动作映射发 HTTP（优先于 webhook） |
| `--creative` | 启用 LLM 创意层（03/04/05/07；需 LLM 配置） |
| `--checkpointer sqlite` | Supervisor 原生 durable 断点（默认 auto） |
| `python -m runtime tasks` | 列出任务 |
| `python -m runtime audits [id]` | 查看审批审计 |
| `python -m runtime export <id> --out <dir>` | 导出产物/证据/信封 + Markdown 摘要 |
| `python -m runtime eval <cases> [--judge]` | 确定性金标评测跑批 + 可选 LLM judge |
| `POST /api/tasks/{id}/cancel` | 取消任务 |
| `python -m runtime serve` → `http://127.0.0.1:8000/` | Web 控制台（任务/审批/证据/审计/评测/告警） |
| `GET /api/metrics` / `GET /metrics` | JSON / Prometheus 指标 |
| `GET /api/alerts` | 失败/阻塞 + 审批积压告警 |
| `python -m runtime tools` | 工具白名单 |
| `python -m runtime actions` | 动作风险注册表 |
| `python -m runtime check-envelope <file>` | 校验审批信封 |
| `python -m runtime check-evidence --text <t> --evidence <f>` | 校验引用与证据 |

所有涉及数据库的命令都支持 `--db <path>`，默认 `.runtime/runtime.db`。

### 认证 / CORS

```bash
export RUNTIME_API_KEY=your-strong-key
# 或多用户：
# export RUNTIME_API_KEYS='{"admin-key":"alice:admin","op-key":"bob:operator"}'
# JWT 登录：
# export RUNTIME_JWT_SECRET=change-me
# export RUNTIME_USERS='{"alice":{"password_sha256":"<hex>","role":"admin"}}'
# 动作级权限：
# export RUNTIME_ACTION_ROLES='{"product.update_price":["admin"]}'
# 限流（每分钟）：
# export RUNTIME_RATE_LIMIT=120
export RUNTIME_CORS_ORIGINS=https://console.example.com
```

- `/api/*`（除 health）需要 Bearer / X-API-Key；
- Web 控制台右上角输入 Key；
- 不设置 API Key = 无认证（仅本地）。

### 可选依赖安装

核心 runtime 只用标准库；需要 LangGraph supervisor / FastAPI / SQLAlchemy 时：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r cross-border-ecommerce-api/requirements.txt
```

> 本机旧环境已有 `langgraph 0.2.x`，与 `langgraph-checkpoint-sqlite 3.x` 存在声明冲突；
> 生产请用干净 venv 按 requirements 安装。

---

## 二、典型流程

### 1. 自检

```bash
python -m runtime doctor
```

输出 `ok: true` 表示（32 项检查）：
- Python >= 3.10；
- 11 个脚本都存在；
- 7 个 Agent 的工具都注册了；
- 7 个样本文件存在；
- SQLite 可建表；
- PyYAML / Pillow 是否安装（可选）。

### 2. 单 Agent

```bash
python -m runtime run "帮我看下巴西站滑板车类目的市场容量和价格带"
```

### 3. 审批闭环

```bash
# run 06：生成 ad.set_bid 信封，任务 interrupted
python -m runtime run "广告 ROAS 太低，怎么降预算"

# 新进程批准
python -m runtime resume <thread_id> --decision approve --comment "同意降出价"

# 查看审计
python -m runtime audits <thread_id>

# 导出
python -m runtime export <thread_id> --out ./exports/ad-001
```

### 4. 全链路

```bash
python -m runtime run "走一遍完整链路" --decision approve
```

顺序：01→02→03→04/05→06（审批中断）→07。
`--decision approve` 表示同进程内批准；不加则停在审批，稍后 `resume`。

---

## 三、任务状态

| 状态 | 含义 | 下一步 |
|---|---|---|
| `created` | 刚创建 | — |
| `running` | 执行中/审批后续跑 | 等待完成或下一次中断 |
| `clarify` | 意图不明确 | 补充关键词或指定 Agent |
| `planning_error` | 切片计划失败 | 查看 error，调整请求 |
| `interrupted` | 等待审批 | `resume approve/reject` |
| `completed` | 全部切片完成 | `export` / `task` |
| `blocked` | 缺输入/校验不过/未接入 | 查看 error |
| `failed` | 执行或证据/信封校验失败 | 查看 error |
| `rejected` | 审批被拒绝 | 修改方案后重跑 |
| `cancelled` | 人工取消 | — |

---

## 四、SQLite 表

```text
tasks(
  thread_id TEXT PRIMARY KEY,
  payload   TEXT  -- TaskRecord JSON
)
envelopes(
  envelope_id TEXT PRIMARY KEY,
  thread_id   TEXT,
  payload     TEXT  -- ApprovalEnvelope JSON
)
audits(
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT,
  payload   TEXT  -- 审批决定 + apply 结果
)
```

默认路径：`.runtime/runtime.db`（WAL 模式，会生成 `-wal` / `-shm`）。

也可以使用 SQLAlchemy 存储：

```bash
# SQLite
RUNTIME_DB_URL=sqlite:///./runtime.db python -m runtime run "..."

# Postgres（需 psycopg）
RUNTIME_DB_URL=postgresql+psycopg://user:pass@host:5432/runtime python -m runtime run "..."
```

### 备份 / 恢复

```bash
# 停掉正在跑的命令后
cp .runtime/runtime.db backups/runtime-$(date +%Y%m%d).db
```

恢复 = 把备份文件放回 `.runtime/runtime.db`。

### 清理

```bash
rm -rf .runtime/
```

---

## 五、导出目录

```text
<out>/
├── task.json                 # 完整 TaskRecord
├── summary.md                # 人读摘要（状态/切片/信封/证据）
├── artifacts/<agent>.json    # 各 Agent 产物
├── evidence/<agent>.json     # 各 Agent 证据块
└── envelopes/<id>.json       # 审批信封
```

---

## 六、常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `status=clarify` | 没有命中关键词 | 换更具体的说法，或 `route` 看候选 |
| `status=blocked` | 缺输入/图片校验不过/Stub | 看 `error` 和 `task.slices` |
| `status=failed` | Runner 失败或证据/信封校验失败 | 看 `error`；证据不完整不许交付 |
| `status=interrupted` | 有审批信封 | `resume` |
| `resume` 报“没有待审批信封” | 已经批过/任务不对 | `task <id>` 查看 |
| 快照漂移 | 审批前目标已被改 | 重新跑诊断，生成新信封 |
| 数据库被占用 | 多进程同时写 | SQLite 单机；生产换 Postgres |
| `--creative` 报配置错误 | 缺 LLM model/key | 配 `RUNTIME_LLM_*` 或 `OPENAI_*` |
| checkpointer sqlite 不可用 | 未安装依赖 | `pip install langgraph-checkpoint-sqlite` |
| adapter 报缺映射 | YAML 未覆盖该 action | 补 actions 映射 |
| adapter 报缺 token | 环境变量未设置 | 设置 `token_env` 指向的变量 |
| supervisor 跨进程 resume | 无 MemorySaver 状态时自动回退任务 checkpoint 续跑 | 已支持；失败看 task.checkpoint / error |
| 想看 checkpoint 历史 | 需要 LangGraph sqlite checkpointer | `GET /api/tasks/{id}/checkpoints` 或 Web「Checkpoint」 |
| YAML 解析失败 | 缺 PyYAML | `pip install pyyaml` 或转 JSON |

---

## 七、边界

- **单机 SQLite**：不支持多实例/高并发；生产换 Postgres（`RUNTIME_DB_URL` + psycopg）。
- **Supervisor 默认 `--checkpointer auto`**：装了 `langgraph-checkpoint-sqlite` 用原生 durable 断点；`--checkpointer postgres` 需 DSN（已实测）；未装则回退任务 checkpoint + simple 续跑。
- **Webhook apply**：配置 `--apply-webhook` / `RUNTIME_APPLY_TOKEN`；默认 dry-run。详见 [12_Apply_and_Eval.md](12_Apply_and_Eval.md)。
- **LLM 创意层**：默认关闭，显式 `--creative`；详见 [13_LLM_Creative_Layer.md](13_LLM_Creative_Layer.md)。
- **依赖版本注意**：本机 `langgraph 0.2.76` 与 `langgraph-checkpoint-sqlite 3.x` 存在版本声明冲突（实际测试可用）；生产建议按底座 `langgraph>=1.2` 对齐版本，或只用任务 checkpoint 回退。
- **apply 是 dry-run**：不会改平台后台。
- **Checkpoint 历史仅查看**：`/api/tasks/{id}/checkpoints` 不提供回滚；续跑走审批 / `resume`。
- **03/04/05/07 是确定性校验层**：完整 LLM 创意生成还没接。
- **LangGraph 未接入**：当前是自研编排，语义已对齐底座。

---

**相关**：[运行时 README](../runtime/README.md) · [集成方案](06_Agent_Runtime_Integration.md) · [审批规范](07_Action_Risk_and_Approval.md) · [证据规范](08_Evidence_and_Citation_Spec.md) · [平台适配器](14_Platform_Adapters.md)
