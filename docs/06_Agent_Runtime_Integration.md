# 06 · 从工具箱到 Agent Runtime：集成方案

> 目标：保留现在的 Prompt/模板/脚本作为"真源"，把 7 个 Agent 变成可编排、可路由、
> 可审批的运行时；底座选型参考 `Multi-Agent-E-commerce-System`，但**不整包合并**。
>
> **当前进度（v0.29）**：7 个 Agent 全链路、SQLite/Postgres（实测）、FastAPI + Web 控制台、
> LangGraph supervisor + 原生 Postgres checkpointer、平台适配器、7/7 评测 + LLM judge、
> LLM 创意层、多用户/JWT/租户/动作权限、bcrypt、Docker/CI/TLS、指标/告警/限流、
> 取消、交付审核 + ZIP、幂等、租户级模型配置 + Key 加密、系统管理页均已接入。
> P9 做平台沙箱/真实 LLM 冒烟/监控看板。见 [`runtime/README.md`](../runtime/README.md)。

---

## 一、为什么要分两层

| 层 | 内容 | 是否依赖运行时 |
|---|---|---|
| **工具箱层**（现有仓库） | Prompt、SKILL.md、模板、案例、确定性脚本 | ❌ 不依赖；三个文件就能跑 |
| **运行时层**（`runtime/` + 底座） | 意图路由、任务切片、子图编排、审批、证据、评测 | ✅ 依赖 Postgres/LangGraph 等 |

这样设计的好处：

1. 不破坏现在"不需要 API key、不需要装环境"的用法；
2. 运行时可以独立迭代，不会把 Prompt 仓库变成一个大应用；
3. 对于简单任务，可以只跑工具箱，不必启动一套服务。

---

## 二、目标架构

```text
用户输入
  │
  ▼
IntentRouter（规则优先 + LLM 兜底）
  │
  ├─ 单意图 ──────────────► Agent 子图（01~07 之一）
  │
  └─ 复合/复杂 ──► ManagerPlanner（≤7 切片 + 依赖 + 审批点）
                        │
                        ▼
                  LangGraph Supervisor
                  ├─ 01 Market Research
                  ├─ 02 Product Strategy
                  ├─ 03 Listing Creative
                  ├─ 04 Product Image
                  ├─ 05 Product Video
                  ├─ 06 Advertising
                  └─ 07 Review Analysis
                        │
                        ▼
             Artifact + EvidenceBlock + ApprovalEnvelope
                        │
                        ▼
             审批中心（人工）→ 事务执行 / 打回重规划
                        │
                        ▼
             Evals（金标场景）+ Observability
```

---

## 三、底座怎么选、怎么改

**推荐底座**：`Multi-Agent-E-commerce-System`（MIT）。

### 保留

| 模块 | 原因 |
|---|---|
| `core/planning.py` 的切片/依赖/校验思路 | 已经是成熟实现，换成 7 个 Agent 即可 |
| `core/graph.py` 的 supervisor + Send 扇出 | 多 Agent 编排的核心 |
| `core/approvals.py` + `interrupt` | 人工审批与断点恢复 |
| `agents/registry.py` 的风险分类思路 | 与 `runtime/actions.py` 对齐 |
| `core/citations.py` | 引用解析与机械防伪引 |
| `evals/` + `docs/evals/` | 金标场景与评分 |
| `api/`、`db/`、前端四视图 | 任务/审批/数据台的壳 |

### 替换

| 底座 | 替换为 |
|---|---|
| `AGENTS = (选品, 订单, 客服)` | `runtime.agent_registry.WORKFLOW_ORDER`（7 个） |
| `fallback_route` 三类关键词 | `runtime.intent_router.IntentRouter` |
| 订单/库存/工单业务域 | 01~07 的 7 个 Agent 子图（不需要订单域就剥离） |
| 底座工具分发 | `runtime.tools.ToolRegistry`（白名单脚本） |
| 审批批次动作 | `runtime.actions.ApprovalEnvelope` |
| 引用结构 | `runtime.evidence.EvidenceBlock` |
| `db/models.py` 业务表 | 增加 `artifacts` / `artifact_versions` / `evidence` 表（或 JSONB 列） |

### 先剥离

第一版不接：Milvus / ClickHouse / Langfuse / 订单 / 客户 / 工单。
只留：FastAPI + LangGraph + Postgres + Redis + 可选前端。
等 01~07 跑通后再把观测和 RAG 加回来。

---

## 四、7 个 Agent 的接入方式

每个 Agent 一个 LangGraph 子图，统一状态：

```python
{
    "request": str,
    "slice": dict,
    "inputs": dict,          # 来自上游 artifact
    "artifacts": dict,       # 本 Agent 产出
    "evidence": list[dict],  # 证据块
    "approval": dict | None, # 审批信封（如有）
}
```

| Agent | 子图入口 | 主要工具 | 产物 |
|---|---|---|---|
| 01 | `01_market_research` | `shaduola_parser` / `market_metrics` | 市场分析报告 |
| 02 | `02_product_strategy` | `sku_pricing` | 产品需求表 / SKU / 盈亏线 |
| 03 | `03_listing_creative` | `title_lint` / `spec_consistency` | Listing 包 |
| 04 | `04_product_image` | `check_main_image` / 可选渲染 | 图片 Prompt 包 |
| 05 | `05_product_video` | `video_timing` | 视频脚本/分镜/字幕 |
| 06 | `06_advertising` | `ad_metrics` | 诊断 + 动作 + 审批信封 |
| 07 | `07_review_analysis` | `review_stats` | 归因 + 修补建议 |

工具调用统一走 `runtime.tools.ToolRegistry.run()`：
只允许白名单脚本，参数列表传递，不执行任意 shell。

---

## 五、意图识别与路由

```text
1. 规则关键词（runtime/intent_router.py）
2. 复合标记（然后/接着/全流程/完整链路…）→ MULTI_AGENT
3. 无命中/歧义 → 注入的 LLM Router
4. LLM 失败/低置信 → CLARIFY（追问，不硬路由）
5. 单意图 → 直接执行；多意图 → ManagerPlanner
```

**为什么规则优先**：
- 便宜、确定、可测试；
- 常见请求（"看类目 / 算价格 / 改广告"）不需要烧 LLM；
- LLM 只处理模糊/复合请求，失败有兜底。

---

## 六、落地阶段

| Phase | 内容 | 验收 |
|---|---|---|
| **P1 ✅** | `runtime/` 平台核心 + 契约 + 测试 | `python -m unittest discover -s runtime/tests` 全绿 |
| **P2 ✅（内存版）** | 内存编排引擎 + 01/02/06 Runner + 审批中断/resume | 01→02 跑通；06 动作可进审批并 dry-run 执行 |
| **P3a ✅（内存版）** | 补 03/04/05/07 Runner + 审批后继续执行剩余切片 | 7 Agent 全链路跑通 |
| **P3b ✅（SQLite）** | SQLite 持久化 + CLI run/resume/task/tasks | 跨进程审批跑通；100 个测试 |
| **P3c ✅（运维）** | doctor/audits/export + 引擎证据/信封不变量 | 坏产出不会被当成功；110 个测试 |
| **P3d ✅（接入）** | LangGraph 层执行器 + SQLAlchemy/Postgres-ready + FastAPI | HTTP 审批闭环；122 个测试 |
| **P4a ✅（Supervisor）** | LangGraph StateGraph + interrupt/resume + 可切换引擎 | 全链路审批断点；130 个测试 |
| **P4b ✅（持久/apply/评测）** | 跨进程 checkpoint 回退 + Webhook apply + 确定性评测 | 140 个测试；跨进程续跑 |
| **P5a ✅（LLM/checkpointer）** | 03/04/05/07 LLM 创意层 + 原生 SQLite checkpointer | 生成式内容；148 个测试 |
| **P5b ✅（控制台/评测）** | Web 控制台 + LLM judge + 依赖对齐 | 153 个测试；可视化操作 |
| **P5c ✅（平台适配/评测面板）** | 配置驱动平台适配器 + `/api/evals` + Web 评测 | 158 个测试；可配置真实调用 |
| **P5d ✅（生产加固）** | API Key/CORS + 证据卡片 + Docker + 上线清单 | 160 个测试 |
| **P5e ✅（多用户/适配器）** | 多用户/角色 + 任务归属 + 重试/幂等/HMAC | 169 个测试 |
| **P5f ✅（JWT/动作权限）** | JWT 登录 + 动作级审批策略 + Web 登录 | 172 个测试 |
| **P5g ✅（生产验证）** | 真实 Postgres 存储/checkpointer + bcrypt + CI | 175 个测试 |
| **P6a ✅（历史/刷新）** | 评测历史 + JWT 刷新 + 导出审计 + Web 过滤 | 177 个测试 |
| **P6b ✅（趋势/导出/反代）** | 评测趋势图 + 任务导出 + Caddy/Nginx 样例 | 178 个测试 |
| **P6c ✅（监控/告警/SSO）** | 指标 + 告警 + 代理 SSO + CI Docker | 182 个测试 |
| **P6d ✅（Token 吊销）** | logout + 吊销 + 刷新轮换 | 185 个测试 |
| **P6e ✅（全覆盖/取消）** | 7/7 Agent 评测 + 任务取消 | 188 个测试 |
| **P7a ✅（限流/看板/就绪）** | 请求限流 + 指标看板 + v1 就绪清单 | 190 个测试 |
| **P7b ✅（交付/幂等/租户）** | 交付审核 + ZIP + API 幂等 + 租户隔离 | 200 个测试 |
| **P8a ✅（租户模型/加密）** | 租户级 provider 配置 + Key 加密 + 测试连接 | 204 个测试 |
| **P8b ✅（目录/系统管理）** | API/Admin 拆分 + 租户/用户/模型管理页 | 206 个测试 |
| **P9 📋** | 平台沙箱验证 + 真实 LLM 冒烟 + 监控看板 | 生产可用 |
| **P4 📋** | 金标评测 + 前端审批中心 + 证据链展示 | 引用可溯源；评测可跑批 |

---

## 七、不要做的事

- ❌ 不要把底座 9 个服务原样搬进工具箱仓库；
- ❌ 不要让 LLM 直接执行外部动作（必须过审批信封）；
- ❌ 不要把 Prompt 塞进一个巨型上下文（每片只带本片需要的上下文）；
- ❌ 不要在没有证据的情况下输出数字/结论；
- ❌ 不要在 P2 之前就接 Milvus/Langfuse/全部前端。

---

**相关**：[runtime/README](../runtime/README.md) · [审批规范](07_Action_Risk_and_Approval.md) · [证据规范](08_Evidence_and_Citation_Spec.md) · [评测规范](09_Eval_Golden_Scenarios.md) · [运维手册](10_Runtime_Operations.md)
