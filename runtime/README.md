# runtime · Agent Runtime Platform Core

> **这不是一套独立应用**，而是从 `Multi-Agent-E-commerce-System` 的架构里抽出来的
> **平台核心 + 契约层**：Agent 注册表、意图路由、任务切片、审批信封、证据链、工具桥接。
>
> 目标：让现在的 7 个 Agent 先具备"可被编排"的形状；将来把这一层嵌进 fork 的
> LangGraph 底座时，不需要重写业务规则。

---

## 一、它解决什么

| 问题 | 本层提供 |
|---|---|
| 后续要多 Agent、意图识别、路由分发 | `IntentRouter`：规则优先 + LLM 兜底 + 低置信度追问 |
| 复杂任务要拆步骤、定依赖 | `ManagerPlanner` + `SlicePlan`：切片、依赖、执行分层 |
| 新增 Agent 要改很多地方 | `AgentRegistry`：7 个 Agent 的能力卡集中一处 |
| 危险动作不能直接执行 | `ActionRegistry` + `ApprovalEnvelope`：风险分级 + 改前/改后快照 + 回滚 |
| 结论不能编 | `EvidenceBlock` + `check_citations`：每个 `[n]` 必须能落到证据 |
| 现有脚本要接进运行时 | `ToolRegistry`：白名单调用 11 个确定性脚本 |

---

## 二、目录

```text
runtime/
├── __init__.py
├── contracts.py        # AgentSpec / RouteDecision / Slice / SlicePlan / EvalCase
├── agent_registry.py   # 7 个 Agent 的能力卡 + 工作流顺序 + 上游关系
├── intent_router.py    # 意图识别与路由（规则优先，LLM 可注入）
├── planner.py          # Manager 切片（依赖、审批点、执行分层）
├── actions.py          # 动作风险注册表 + 审批信封 + 快照漂移
├── evidence.py         # 证据块 + 引用机械校验
├── tools.py            # 现有脚本 → 运行时工具白名单
├── storage.py          # 任务/产物/证据/审批存储（内存 / SQLite）
├── agent_runners.py    # 7 个 Agent Runner（调真实脚本）
├── engine.py           # 路由 → 切片 → 执行 → 审批 → 续跑编排
├── executors.py        # 顺序 / LangGraph 层执行器
├── supervisor.py       # LangGraph supervisor + 跨进程 checkpoint 回退
├── apply.py            # dry-run / Webhook apply
├── evals.py            # 确定性评测跑批
├── llm.py              # 可选 LLM 客户端
├── creative.py         # 03/04/05/07 LLM 创意层
├── web/                # 零构建 Web 控制台
├── platforms.py        # 平台动作适配器（重试/幂等/HMAC）
├── auth.py             # 多用户/角色认证
├── providers.py        # 租户级模型配置 + Key 加密
├── metrics.py          # Prometheus 指标
├── alerts.py           # 失败/审批积压告警
├── requirements-runtime.txt
├── integrations/       # SQLAlchemyStore（Postgres-ready）
├── factory.py          # 存储工厂（SQLite / DB URL）
├── doctor.py           # 环境/脚本/样本/SQLite 自检
├── export.py           # 任务导出（JSON + Markdown）
├── api.py              # FastAPI 服务
├── cli.py / __main__.py
└── tests/
```

核心为纯标准库；LangGraph / SQLAlchemy / FastAPI 为可选集成。
缺少时执行器自动回退、存储回退 SQLite、API 不可用但编排仍可跑。

---

## 三、快速验证

```bash
# 意图路由
python -m runtime route "帮我看下巴西站滑板车类目市场容量和价格带"

# 意图 + 切片计划
python -m runtime plan "先分析类目市场，然后定价，再做主图和广告"

# 执行一次任务（7 个 Agent 可跑；默认 SQLite 持久化）
python -m runtime run "帮我看下巴西站滑板车类目的市场容量和价格带"
python -m runtime run "广告 ROAS 太低，怎么降预算"                 # 停在审批，exit 2
python -m runtime run "广告 ROAS 太低，怎么降预算" --decision approve  # 批准后 completed

# 查看工具 / 动作注册表
python -m runtime tools
python -m runtime actions

# 校验审批信封 / 证据链（支持 .yaml / .json）
python -m runtime check-envelope Templates/action_approval_envelope.yaml
python -m runtime check-evidence --text output.md --evidence Templates/evidence_block.yaml

# 跨进程：run 停在审批 → resume 批准 → task/tasks 查看
python -m runtime run "广告 ROAS 太低，怎么降预算"
python -m runtime resume <thread_id> --decision approve
python -m runtime task <thread_id>
python -m runtime tasks

# 启动 HTTP 服务（simple / supervisor）
python -m runtime serve --port 8000
python -m runtime serve --engine supervisor --port 8000

# 引擎/执行器选择
python -m runtime run "先分析市场，然后定价" --executor sequential
python -m runtime run "广告 ROAS 太低，怎么降预算" --engine supervisor --decision approve

# 跨进程续跑：supervisor 无 MemorySaver 状态时回退任务 checkpoint
python -m runtime run "广告 ROAS 太低，怎么降预算" --engine supervisor
python -m runtime resume <thread_id> --engine supervisor --decision approve

# 真实 apply：审批通过后 POST 到外部执行器
python -m runtime resume <thread_id> --decision approve --apply-webhook http://127.0.0.1:9000/apply

# 确定性评测
python -m runtime eval Templates/eval_case.yaml

# LLM 创意层（默认关闭；需 LLM 配置）
python -m runtime run "帮我写一个商品标题" --creative

# Web 控制台 + LLM judge
python -m runtime serve --port 8000 --checkpointer sqlite
python -m runtime eval Templates/eval_case.yaml --judge

# 平台动作映射（按官方 API 填写）
python -m runtime resume <thread_id> --decision approve   --apply-adapter Templates/platform_adapter.example.yaml

# 单元测试（206 个，含 Postgres 集成）
python -m unittest discover -s runtime/tests -v
```

---

## 四、7 个 Agent 的能力卡

| Agent key | 领域 | 工具 | 审批策略 |
|---|---|---|---|
| `market_research` | 01 市场分析 | `shaduola_parser` / `market_metrics` | 只读 |
| `product_strategy` | 02 产品策略 | `sku_pricing` | 改价/发券审批 |
| `listing_creative` | 03 Listing | `title_lint` / `spec_consistency` | 改 Listing 审批 |
| `product_image` | 04 商品图 | `check_main_image` / 可选渲染 | 换主图审批 |
| `product_video` | 05 视频 | `video_timing` | 只出草稿 |
| `advertising` | 06 广告 | `ad_metrics` | 改预算/出价审批 |
| `review_analysis` | 07 评论 | `review_stats` | 修补 Listing 审批 |

每个 Agent 的 `input_schema` / `output_schema` 在 `agent_registry.py` 里声明。
新增 Agent 只需要在 `AGENTS` 里加一条，并在 `WORKFLOW_ORDER` / `UPSTREAM` 里登记关系。

---

## 五、Phase 2/3a/3b 已实现（SQLite 编排）

| 能力 | 状态 |
|---|---|
| 01 市场分析 Runner（读指标 JSON → 产物 + 证据） | ✅ |
| 02 产品策略 Runner（调 `sku_pricing matrix` → SKU/盈亏线 + 证据） | ✅ |
| 03 Listing Runner（`title_lint` + `spec_consistency`） | ✅ |
| 04 商品图 Runner（像素校验 + 9 图骨架） | ✅ |
| 05 视频 Runner（`video_timing` 时长/字幕校验） | ✅ |
| 06 广告 Runner（`ad_metrics diagnose` → 诊断 + 证据 + 审批信封） | ✅ |
| 07 评论 Runner（`review_stats` 归因聚合） | ✅ |
| 审批中断：06 生成 P0 动作后任务停在 `interrupted` | ✅ |
| `resume`：approve/reject + 审计 + 快照漂移拒绝 + **继续执行剩余切片** | ✅ |
| 7 Agent 全链路：01→02→03→04/05→06→审批→07 | ✅ |
| 跨进程：run → resume → task | ✅（SQLite / SQLAlchemy） |
| LangGraph 层执行器 | ✅（默认优先，失败回退 sequential） |
| LangGraph supervisor | ✅（interrupt/resume + 跨进程 checkpoint 回退） |
| 真实 apply | ✅（Webhook，默认 dry-run） |
| 确定性评测 | ✅（eval_case.yaml mechanical checks） |
| 评测历史 | ✅（`GET /api/evals` + Web 趋势图） |
| 任务导出 | ✅（`GET /api/tasks/{id}/export` + Web） |
| 指标 / 告警 | ✅（`/api/metrics` / `/metrics` / `/api/alerts`） |
| 代理 SSO | ✅（`RUNTIME_PROXY_AUTH_SECRET`） |
| JWT 注销/吊销/刷新轮换 | ✅（`revoked_tokens` 持久化） |
| 7/7 Agent 评测覆盖 | ✅（01–07 全部有 case） |
| 任务取消 | ✅（`POST /api/tasks/{id}/cancel`） |
| 请求限流 | ✅（`RUNTIME_RATE_LIMIT`） |
| 指标看板 | ✅（Web 指标卡片/状态分布） |
| v1 就绪清单 | ✅（`docs/17_Runtime_Readiness.md`） |
| 交付审核 + ZIP 归档 | ✅（机器+人工+manifest） |
| API 幂等 + 节点耗时 | ✅（`Idempotency-Key` / elapsed_ms） |
| 租户隔离 | ✅（tenant_id） |
| 租户级模型配置 | ✅（加密 Key + 测试连接） |
| 租户/用户管理 | ✅（API + Web 系统管理） |
| TLS 反代样例 | ✅（`cross-border-ecommerce-api/deploy/` Caddy / Nginx） |
| JWT 刷新 / 导出审计 | ✅ |
| LLM 创意层 | ✅（03/04/05/07；默认关闭） |
| Web 控制台 | ✅（零构建，同源托管） |
| 平台动作适配器 | ✅（YAML 映射，mock 测试） |
| API Key 认证 + CORS | ✅（可选，环境变量配置） |
| 多用户/角色 + 任务归属 | ✅（admin/operator/viewer） |
| JWT 登录 + 动作级审批策略 | ✅（`RUNTIME_JWT_SECRET` / `RUNTIME_ACTION_ROLES`） |
| bcrypt 密码哈希 | ✅（兼容旧 sha256） |
| Postgres 存储/checkpointer | ✅（本机 Docker Postgres 实测） |
| CI | ✅（`.github/workflows/tests.yml`） |
| 适配器重试/幂等/HMAC | ✅ |
| Docker 部署 | ✅（`cross-border-ecommerce-api/Dockerfile` + compose） |
| LLM judge | ✅（FakeLLM 测试，无真实调用） |
| 原生 durable checkpointer | ✅（SQLite） |
| HTTP API | ✅（FastAPI） |
| 运维：doctor / audits / export | ✅ |
| 存储 | 内存 / SQLite（stdlib，跨进程） |
| 真实平台执行 | dry-run（下一步接事务 apply） |

任务状态：`completed` / `interrupted` / `clarify` / `blocked` / `failed` / `rejected`。

---

## 六、如何嵌进 Multi-Agent-E-commerce-System

推荐做法：**fork 底座，保留平台核心，替换业务域。**

| 底座文件 | 改法 |
|---|---|
| `core/planning.py` 的 `AGENTS` | 改为 `runtime.agent_registry.WORKFLOW_ORDER` / `AgentRegistry` |
| `core/planning.py` 的 `fallback_route` | 改为 `runtime.intent_router.IntentRouter` |
| `core/graph.py` 的 `AgentRunner` 映射 | 7 个 key 映射到 7 个 LangGraph 子图 |
| `agents/registry.py` | 合并 `runtime.actions.DEFAULT_ACTION_REGISTRY` |
| `agents/executor.py` 的工具分发 | 改为 `runtime.tools.ToolRegistry.run` |
| `core/approvals.py` | 保留审批批次；信封结构对齐 `runtime.actions.ApprovalEnvelope` |
| `core/citations.py` | 保留引用解析；证据结构对齐 `runtime.evidence.EvidenceBlock` |
| `db/models.py` | 增加 `artifacts` / `artifact_versions` / `evidence`（或 JSONB 列） |
| `docs/evals/*.yaml` | 按 `runtime.contracts.EvalCase` 增加 7 个 Agent 的金标场景 |

**建议的入口流程**：

```text
POST /api/tasks
  → IntentRouter.route()
      → 单意图：直接执行对应 Agent 子图
      → 多意图/复杂：ManagerPlanner.plan() → LangGraph supervisor 扇出
  → 子图调用 ToolRegistry（确定性脚本）
  → 输出 artifact + EvidenceBlock
  → 对外动作 → ApprovalEnvelope → 审批中心 → 事务 apply
```

---

## 七、分阶段落地

| Phase | 内容 | 验证标准 |
|---|---|---|
| **P1 ✅** | 契约 + 注册表 + 路由 + 切片 + 审批/证据结构 | `runtime/tests` 全绿；CLI 能出计划 |
| **P2 ✅（内存版）** | 内存编排引擎 + 01/02/06 Runner + 审批中断/resume | 01→02 跑通；06 动作能进审批并 dry-run 执行 |
| **P3a ✅（内存版）** | 补 03/04/05/07 Runner + 审批后继续执行剩余切片 | 7 Agent 全链路跑通 |
| **P3b ✅（SQLite）** | SQLite 持久化 + CLI run/resume/task/tasks | 跨进程审批跑通；100 个测试 |
| **P3c ✅（运维）** | doctor/audits/export + 引擎证据/信封不变量 | 坏产出不会被当成功 |
| **P3d ✅（接入）** | LangGraph 层执行器 + SQLAlchemy/Postgres-ready + FastAPI | HTTP 审批闭环 |
| **P4a ✅（Supervisor）** | LangGraph StateGraph + interrupt/resume + CLI/API 可切换引擎 | 全链路审批断点 |
| **P4b ✅（持久/apply/评测）** | 跨进程 checkpoint 回退 + Webhook apply + 确定性评测 | 跨进程续跑 |
| **P5a ✅（LLM/checkpointer）** | 03/04/05/07 LLM 创意层 + 原生 SQLite checkpointer | 生成式内容 |
| **P5b ✅（控制台/评测）** | Web 控制台 + LLM judge + 依赖对齐 | 可视化操作 |
| **P5c ✅（平台适配/评测面板）** | 配置驱动平台适配器 + /api/evals + Web 评测 | 可配置真实调用 |
| **P5d ✅（生产加固）** | API Key/CORS + 证据卡片 + Docker + 上线清单 | 生产雏形 |
| **P5e ✅（多用户/适配器）** | 多用户/角色 + 任务归属 + 重试/幂等/HMAC | 生产雏形 |
| **P5f ✅（JWT/动作权限）** | JWT 登录 + 动作级审批策略 + Web 登录 | 172 个测试 |
| **P5g ✅（生产验证）** | 真实 Postgres 存储/checkpointer + bcrypt + CI | 175 个测试 |
| **P6a ✅（历史/刷新）** | 评测历史 + JWT 刷新 + 导出审计 + Web 过滤 | 生产雏形 |
| **P6b ✅（趋势/导出/反代）** | 评测趋势图 + 任务导出 + Caddy/Nginx 样例 | 生产雏形 |
| **P6c ✅（监控/告警/SSO）** | 指标 + 告警 + 代理 SSO + CI Docker | 生产雏形 |
| **P6d ✅（Token 吊销）** | logout + 吊销 + 刷新轮换 | 生产雏形 |
| **P6e ✅（全覆盖/取消）** | 7/7 Agent 评测 + 任务取消 | 生产雏形 |
| **P7a ✅（限流/看板/就绪）** | 请求限流 + 指标看板 + v1 就绪清单 | 生产雏形 |
| **P7b ✅（交付/幂等/租户）** | 交付审核 + ZIP + API 幂等 + 租户隔离 | 生产雏形 |
| **P8a ✅（租户模型/加密）** | 租户级 provider 配置 + Key 加密 + 测试连接 | 生产雏形 |
| **P8b ✅（目录/系统管理）** | API/Admin 拆分 + 租户/用户/模型管理页 | 206 个测试 |
| **P9 📋** | 平台沙箱验证 + 真实 LLM 冒烟 + 监控看板 | 生产可用 |
| **P4 📋** | 金标评测 + 前端审批中心 + 证据链展示 | 引用可溯源；评测可跑批 |

---

## 八、边界

- **不执行平台后台操作**：审批通过后由执行层落地，本层只产出信封。
- **不生成业务内容**：Prompt 仍以 `Agents/*/SKILL.md` 和 `prompts/` 为真源。
- **不依赖 LLM 才能跑**：路由规则、切片、审批、证据校验都是确定性的；
  LLM 只在无关键词/歧义时由调用方注入。
- **不替代底座**：LangGraph、FastAPI、Postgres、审批 UI 仍由底座提供。

---

**返回**：[项目 README](../README.md) · **契约模板**：[审批信封](../Templates/action_approval_envelope.yaml) · [证据块](../Templates/evidence_block.yaml) · [任务计划](../Templates/workflow_plan.yaml) · **集成文档**：[docs/06_Agent_Runtime_Integration.md](../docs/06_Agent_Runtime_Integration.md) · **运维手册**：[docs/10_Runtime_Operations.md](../docs/10_Runtime_Operations.md) · **Apply/评测**：[docs/12_Apply_and_Eval.md](../docs/12_Apply_and_Eval.md)
