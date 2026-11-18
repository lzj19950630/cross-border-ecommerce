# ROADMAP

## 版本路线

| 版本 | 主题 | 内容 | 状态 |
|---|---|---|---|
| **v0.1** | 创意簇 | 03 Listing / 04 Image / 05 Video + 方法论文档 + 案例库 | ✅ 已完成 |
| **v0.2** | 运营簇 | 06 Advertising / 07 Review + 闭环案例 | ✅ 已完成 |
| **v0.3** | 分析簇 | 01 Market Research（含脚本）/ 02 Product Strategy | ✅ 已完成 |
| **v0.5** | 生图执行层 | 04 Campaign Style Lock / Product Angle Sheet / 可选批量渲染 + 出图后校验 | ✅ 已完成 |
| **v0.6** | Agent 运行时核心 | 7 Agent 能力卡 / 意图路由 / 任务切片 / 审批信封 / 证据链 / 工具桥接 | ✅ 已完成 |
| **v0.7** | Phase 2 内存编排 | 01/02/06 Runner + 审批中断/resume + 内存存储 + 90 个测试 | ✅ 已完成 |
| **v0.8** | Phase 3a 全链路 | 7 个 Agent Runner + 审批后继续 07 + 内存全链路 | ✅ 已完成 |
| **v0.9** | Phase 3b 持久化 | SQLite 存储 + run/resume/task 跨进程 + 100 个测试 | ✅ 已完成 |
| **v0.10** | Phase 3c 运维加固 | doctor/audits/export + 引擎证据/信封不变量 + 110 个测试 | ✅ 已完成 |
| **v0.11** | Phase 3d 运行时接入 | LangGraph 层执行器 + SQLAlchemy/Postgres-ready + FastAPI | ✅ 已完成 |
| **v0.12** | Phase 4a Supervisor | LangGraph StateGraph + interrupt/resume + CLI/API 可切换 | ✅ 已完成 |
| **v0.13** | Phase 4b 持久/apply/评测 | 跨进程 checkpoint 回退 + Webhook apply + 确定性评测 | ✅ 已完成 |
| **v0.14** | Phase 5a LLM 创意层 | 03/04/05/07 生成 + 原生 SQLite checkpointer | ✅ 已完成 |
| **v0.15** | Phase 5b 控制台/评测 | Web 控制台 + LLM judge + 依赖对齐 | ✅ 已完成 |
| **v0.16** | Phase 5c 平台适配/评测面板 | 配置驱动平台适配器 + /api/evals + Web 评测 | ✅ 已完成 |
| **v0.17** | Phase 5d 生产加固 | API Key/CORS + 证据卡片 + Docker + 上线清单 | ✅ 已完成 |
| **v0.18** | Phase 5e 多用户/适配器增强 | 多用户/角色 + 重试/幂等/HMAC | ✅ 已完成 |
| **v0.19** | Phase 5f JWT/动作权限 | JWT 登录 + 动作级审批策略 | ✅ 已完成 |
| **v0.20** | Phase 5g 生产验证 | 真实 Postgres + bcrypt + CI | ✅ 已完成 |
| **v0.21** | Phase 6a 评测历史/刷新 | 评测历史 + JWT 刷新 + 导出审计 + Web 过滤 | ✅ 已完成 |
| **v0.22** | Phase 6b 趋势/导出/反代 | 评测趋势图 + 任务导出 API + TLS 反代样例 | ✅ 已完成 |
| **v0.23** | Phase 6c 监控/告警/代理SSO | 指标 + 告警 + proxy auth + CI Docker | ✅ 已完成 |
| **v0.24** | Phase 6d Token 吊销 | logout + token 吊销 + 刷新轮换 | ✅ 已完成 |
| **v0.25** | Phase 6e 全覆盖/取消 | 7/7 Agent 评测 + 任务取消 | ✅ 已完成 |
| **v0.26** | Phase 7a 限流/看板/就绪 | 请求限流 + 指标看板 + v1 就绪清单 | ✅ 已完成 |
| **v0.27** | Phase 7b 交付/幂等/租户 | 交付审核 + ZIP + API 幂等 + 租户隔离 | ✅ 已完成 |
| **v0.28** | Phase 8a 租户模型/加密 | 租户级 provider 配置 + Key 加密 | ✅ 已完成 |
| **v0.29** | Phase 8b 目录/系统管理 | API/Admin 拆分 + 租户/用户/模型管理页 | ✅ 已完成 |
| **v0.30** | Phase 8c Agent/追踪 | Agent 管理页 + 全链路追踪 + Checkpoint 历史 | ✅ 已完成 |
| v1.0 | 串联 | 完整工作流一键跑通，输出上架素材包 | 📋 规划 |
| V2 | API | 接入 Shopee / Mercado Livre 平台 API | 📋 规划 |
| V3 | Web | 网页应用，可视化工作流 | 📋 规划 |
| V4 | 自动化 | 定时执行 + 闭环优化 | 📋 规划 |

✅ **7 个 Agent 模块全部完成。**

---

## v0.1 · 创意簇 ✅

| 模块 | 内容 |
|---|---|
| 03 Listing Creative | 关键词七类分词 · 标题五段公式 · 详情页 7 段 · 卖点分层 · 参数一致性校验 |
| 04 Product Image | 9 图规划 · 逐图出图 Prompt · 负面 Prompt 库 · 图片合规守卫 |
| 05 Product Video | 15s/30s 双版本脚本 · 分镜表 · AI 视频 Prompt · 配音稿 · 字幕 · 静音可读性检查 |

---

## v0.2 · 运营簇 ✅

### 06 Advertising Optimization Agent

- [x] 输入模板：广告数据 + 成本结构（含数据质量门槛：曝光 < 1,000 拒绝分析）
- [x] 四类漏斗诊断（严格按 CTR → 加购率 → 转化率 → ROAS 顺序判定）
- [x] 盈亏线 ROAS 核算 + ROAS 敏感性表 + 达标线差距分析
- [x] 预算 × ROI 双变量模型 + 分阶段目标 + 分时段预算节律
- [x] 完整案例：充电宝 4 个广告组，四类症状齐全，整体 ROAS 1,84 亏损

### 07 Review Analysis Agent

- [x] 八类差评归因 + 好评 5 维度分析
- [x] **误解型差评识别**（三种判定：缺失说明 / 说明不醒目 / 买家未阅读）
- [x] 详情页修补建议 + 参数红线提炼 + 卖点频次×情感强度排序
- [x] 完整案例：电动滑板车，可修复差评 84,6%，误解型占 38,5%

### 闭环案例

- [x] `Examples/03_Closed_Loop/`：广告侧 + 评论侧两条回流路径的完整演示

---

## v0.3 · 分析簇 ✅

### 01 Market Research Agent

**这一批的瓶颈是"数据怎么进得来"，所以直接连脚本一起做了。**

- [x] `scripts/shaduola_parser.py`：格式标准化（洗货币符号 / 千分位 / 万单位 / 空值 / 日期 / 补算 GMV）
- [x] `scripts/market_metrics.py`：容量 / CR3·CR10·HHI / 价格分箱 / **波谷检测** / 配置交叉表
- [x] `scripts/make_sample.py` + `samples/`：可复现样本（含预期结果，用于验证环境）
- [x] 前置判断 Prompt（SOP 1.1，**判定不通过时停止，不做下游**）
- [x] 市场分析 Prompt（SOP 1.2–1.6，含"数据不足要直说"的硬要求）
- [x] 完整案例：电动滑板车（全部数字可由三条命令复现）
- [x] **设计原则**：能算的别让模型猜——确定性计算交脚本，判断交 Agent

**波谷检测的三个实现要点**（踩坑改出来的）：
1. 在原始曲线上检测，**默认不做平滑**（3 点滑动平均会抹掉陡峭波谷）
2. 跌幅显著性过滤（默认 15%）
3. 价格带数量上限（默认 5，超出按跌幅取前几名）

### 02 Product Strategy Agent

- [x] 产品定位 Prompt（1.7 + 3.1，含上架前 8 问）
- [x] 定价与 SKU Prompt（1.9 + 3.2，含逐 SKU 毛利验算 + 盈亏线）
- [x] **`decision_approved` 阻塞机制**——不做选品决策，只做规格化
- [x] SKU 四角色结构 + 价格阶梯双向检查（过大/过小）+ 优惠券设计
- [x] 完整案例：电动滑板车（毛利余量 R$ 98,95 与拟发券 R$ 100 的闭环）

---

## v0.6 · Agent Runtime 平台核心 ✅

**目标：让 7 个 Agent 先具备"可被编排"的形状，为 V4 做准备；工具箱本身仍可独立使用。**

- [x] `runtime/contracts.py`：AgentSpec / RouteDecision / SlicePlan / EvalCase
- [x] `runtime/agent_registry.py`：7 个 Agent 的能力卡 + 工具 + 审批策略
- [x] `runtime/intent_router.py`：规则优先 + LLM 兜底 + 低置信追问
- [x] `runtime/planner.py`：切片、依赖、执行分层、审批点
- [x] `runtime/actions.py`：三层风险 + 审批信封 + 快照漂移
- [x] `runtime/evidence.py`：证据块 + 引用机械校验
- [x] `runtime/tools.py`：现有脚本 → 白名单工具
- [x] `runtime/cli.py` + `runtime/tests/`（无需 API Key）
- [x] 契约模板：审批信封 / 证据块 / 任务计划 / 评测场景
- [x] 文档：06 集成方案 / 07 审批规范 / 08 证据规范 / 09 评测规范

---

## v0.7 · Phase 2 内存编排 ✅

**目标：不接数据库、不接 LangGraph，先把"路由→切片→执行→审批"跑通。**

- [x] `runtime/storage.py`：任务/产物/证据/审批内存存储
- [x] `runtime/agent_runners.py`：01/02/06 Runner（调真实脚本）+ 03/04/05/07 Stub
- [x] `runtime/engine.py`：逐层执行切片；06 生成审批信封后 `interrupted`
- [x] `resume`：approve/reject + 审计 + 快照漂移拒绝 + dry-run apply
- [x] CLI：`python -m runtime run "..." [--decision approve|reject]`
- [x] 90 个测试：路由/切片/审批/证据/工具/Runner/Engine/CLI

**下一步（Phase 3）**：fork 底座，接 Postgres + artifact 表，补 03/04/05 Runner，再把内存引擎替换成 LangGraph。

---

## v0.8 · Phase 3a 全链路 ✅

**目标：7 个 Agent 都能在内存编排里跑，06 审批后继续后续切片。**

- [x] 03 Listing Runner：`title_lint` + `spec_consistency`
- [x] 04 商品图 Runner：像素校验 + 9 图骨架
- [x] 05 视频 Runner：`video_timing` 时长/字幕校验
- [x] 07 评论 Runner：`review_stats` 归因聚合
- [x] 审批后继续执行剩余切片（06 批准 → 07）
- [x] 全链路测试：01→02→03→04/05→06→审批→07
- [x] 95 个测试通过

**仍待**：Postgres 持久化、LangGraph supervisor、事务 apply、评测/前端。

---

## v0.9 · Phase 3b 持久化 ✅

**目标：run 和审批 resume 能跨进程，不再依赖内存。**

- [x] `runtime/storage.py`：`TaskStore` 协议 + `InMemoryStore` + `SQLiteStore`
- [x] SQLite 表：tasks / envelopes / audits
- [x] CLI：`run --db` / `resume` / `task` / `tasks`
- [x] 跨进程：run 停在审批 → 新进程 resume 批准 → task 查看
- [x] 全链路跨进程：01→02→03→04/05→06 审批→07
- [x] 100 个测试通过

**仍待**：Postgres 实现、LangGraph supervisor、事务 apply、评测/前端。

---

## v0.10 · Phase 3c 运维加固 ✅

**目标：让运行时能自检、能审计、能导出、不会把坏产出当成功。**

- [x] `python -m runtime doctor`：Python/脚本/样本/SQLite/可选依赖自检
- [x] `python -m runtime audits <id>`：审批审计
- [x] `python -m runtime export <id> --out <dir>`：产物/证据/信封/摘要导出
- [x] 引擎不变量：`ok` 产出必须有证据；信封必须通过校验
- [x] 任务状态白名单 `VALID_TASK_STATUSES`
- [x] 110 个测试通过

**仍待**：Postgres 实现、LangGraph supervisor、事务 apply、评测/前端。

---

## v0.12 · Phase 4a LangGraph Supervisor ✅

**目标：用 LangGraph 原生的 interrupt/resume 表达审批断点。**

- [x] `runtime/supervisor.py`：plan → execute_layer → approval → resume → 完成
- [x] `interrupt(payload)` 携带待审批信封；`Command(resume=...)` 批准/拒绝
- [x] CLI `--engine simple|supervisor`
- [x] FastAPI `create_app(engine_type="supervisor")` / `serve --engine supervisor`
- [x] 全链路：06 审批断点 → 批准 → 07 执行
- [x] 130 个测试通过

**仍待**：durable checkpointer（跨重启）、真实事务 apply、评测/前端。

---

## v0.13 · Phase 4b 持久续跑 / apply / 评测 ✅

**目标：Supervisor 断点跨进程可用；审批通过后能真的调用外部执行器；评测可回归。**

- [x] `TaskRecord.checkpoint`：保存 current_layer/status
- [x] Supervisor 同进程用 `Command(resume)`；新进程无 MemorySaver 状态时回退任务 checkpoint 续跑
- [x] `runtime/apply.py`：DryRun / Webhook apply（Bearer token 走环境变量）
- [x] CLI `--apply-webhook`
- [x] `runtime/evals.py` + `python -m runtime eval Templates/eval_case.yaml`
- [x] 机械判据：证据/章节/信封合法/无禁止动作/归因合计
- [x] 140 个测试通过

**仍待（P5）**：LLM 创意层、标准 durable checkpointer、真实平台适配、前端。

---

## v0.14 · Phase 5a LLM 创意层 + 原生 checkpointer ✅

**目标：补齐生成式内容，并让 supervisor 断点真正 durable。**

- [x] `runtime/llm.py`：OpenAI 兼容客户端 + FakeLLM
- [x] `runtime/creative.py`：03 标题/详情、04 9 图 Prompt、05 脚本、07 修补建议
- [x] LLM 失败回退确定性结果；03/05 仍过工具校验
- [x] `--creative` / `serve --creative`（默认关闭）
- [x] `langgraph-checkpoint-sqlite`：Supervisor 原生跨进程 durable 断点
- [x] `--checkpointer auto|memory|sqlite`
- [x] 148 个测试通过

**仍待（P5b）**：真实平台适配、前端、LLM judge、可视化评测看板。

---

## v0.15 · Phase 5b Web 控制台 + LLM judge ✅

**目标：能可视化操作，评测能加 judge，依赖能对齐。**

- [x] `cross-border-ecommerce-admin/index.html`：任务列表/创建/详情/审批/证据/审计
- [x] FastAPI 同源托管 `/` + `/static`
- [x] `runtime/evals.py` + `--judge`：LLM judge（0/1 + 理由，FakeLLM 测试）
- [x] `cross-border-ecommerce-api/requirements.txt`：可选依赖与版本对齐
- [x] 153 个测试通过

**仍待（P5c）**：真实平台适配器、认证/多用户、可视化评测看板。

---

## v0.16 · Phase 5c 平台适配器 + 评测面板 ✅

**目标：审批动作能按平台配置真实调用；评测结果能进 Web。**

- [x] `runtime/platforms.py`：YAML/JSON 动作映射 → HTTP 请求
- [x] `--apply-adapter` / `create_app(apply_adapter=...)`
- [x] `POST /api/evals`：确定性评测 API
- [x] Web 控制台「运行评测」按钮 + 结果展示
- [x] 平台适配器 mock 测试（路径/body/token/缺映射/缺 token）
- [x] 158 个测试通过

**仍待（P5e）**：多用户/角色、平台沙箱验证、可视化评测看板。

---

## v0.17 · Phase 5d 生产加固 ✅

**目标：能安全地给别人用，而不是只能本机跑。**

- [x] 可选 API Key 认证（`RUNTIME_API_KEY`）：`/api/*` 保护，health/首页公开
- [x] CORS 白名单（`RUNTIME_CORS_ORIGINS`）
- [x] Web 控制台 API Key 输入 + 证据卡片
- [x] `cross-border-ecommerce-api/Dockerfile` + `cross-border-ecommerce-api/docker-compose.yml` + `.dockerignore`
- [x] `cross-border-ecommerce-api/requirements.txt` 加 psycopg
- [x] `docs/15_Production_Checklist.md` 上线清单
- [x] 160 个测试通过

**仍待（P5e）**：多用户/角色、平台沙箱验证、可视化评测看板。

---

## v0.18 · Phase 5e 多用户/角色 + 适配器增强 ✅

**目标：能分人用、能安全重试。**

- [x] `runtime/auth.py`：`RUNTIME_API_KEYS` 多用户 + admin/operator/viewer
- [x] 任务 `owner` + API 权限过滤 + 审计 `decided_by`
- [x] Web 控制台 Key 输入 / 证据卡片
- [x] 适配器 `retry` / `idempotency_header` / `hmac_sha256` 签名
- [x] `docs/16_Multi_User_and_Roles.md`
- [x] 169 个测试通过

**仍待（P6）**：平台沙箱验证、可视化评测看板、SSO。

---

## v0.19 · Phase 5f JWT 登录 + 动作级审批权限 ✅

**目标：不再只靠静态 Key；审批动作按角色限制。**

- [x] `POST /api/auth/login`：用户名/密码 → JWT（HS256，stdlib 实现）
- [x] `RUNTIME_USERS`（password_sha256 + role）
- [x] Middleware 同时接受 API Key 与 JWT
- [x] Web 控制台登录/退出
- [x] `RUNTIME_ACTION_ROLES`：动作 → 允许角色（支持通配 `ad.*`）
- [x] 审批前检查每个动作的角色权限
- [x] 172 个测试通过

**仍待（P6）**：平台沙箱验证、可视化评测看板、SSO。

---

## v0.20 · Phase 5g 生产验证 ✅

**目标：不是"Postgres-ready"，而是真跑过。**

- [x] Docker 启动 Postgres 16，`SQLAlchemyStore` 跨引擎续跑通过
- [x] `langgraph-checkpoint-postgres`：Supervisor 原生 durable 断点跨进程通过
- [x] bcrypt 密码哈希（兼容旧 sha256）
- [x] `.github/workflows/tests.yml`：Python + Postgres service + 04 渲染自测
- [x] docker-compose 改为 Postgres + postgres checkpointer（配置校验通过）
- [x] 175 个测试通过（2 个 Postgres 集成测试在无 env 时 skip）

**仍待（P6）**：平台沙箱验证、可视化评测看板、SSO。

---

## v0.21 · Phase 6a 评测历史 / JWT 刷新 / 导出审计 ✅

- [x] 评测结果持久化：InMemory / SQLite / SQLAlchemy
- [x] `POST /api/evals` 保存 + `GET /api/evals` 历史
- [x] Web「评测历史」+ 状态筛选
- [x] JWT 刷新端点（未过期 token → 新 token）
- [x] 导出包含 `audits.json`
- [x] 177 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P7）**：平台沙箱验证、监控看板、多租户隔离。

---

## v0.22 · Phase 6b 评测趋势 / 任务导出 / TLS 反代 ✅

- [x] Web 评测历史趋势图（SVG，无第三方图表库）
- [x] `GET /api/tasks/{id}/export` + Web「导出 JSON」
- [x] `deploy/Caddyfile` / `deploy/nginx.conf` / `cross-border-ecommerce-api/docker-compose.prod.yml`
- [x] `docker compose -f cross-border-ecommerce-api/docker-compose.yml -f cross-border-ecommerce-api/docker-compose.prod.yml config` 通过
- [x] 178 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P7）**：平台沙箱验证、监控看板、多租户隔离。

---

## v0.23 · Phase 6c 监控 / 告警 / 代理 SSO ✅

- [x] `GET /api/metrics`（JSON）+ `GET /metrics`（Prometheus 文本）
- [x] `GET /api/alerts`：失败/阻塞任务 + 审批积压
- [x] Web「告警」「指标」按钮
- [x] 代理 SSO：`RUNTIME_PROXY_AUTH_SECRET` + `X-Auth-Request-User/Role`
- [x] CI 增加 Docker build + 容器 doctor 自检
- [x] 182 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P7）**：平台沙箱验证、监控看板、多租户隔离。

---

## v0.24 · Phase 6d JWT 注销 / Token 吊销 ✅

- [x] JWT 增加 `jti`
- [x] `revoked_tokens` 表：InMemory / SQLite / Postgres
- [x] `POST /api/auth/logout` 吊销当前 token
- [x] `POST /api/auth/refresh` 轮换旧 token（旧 token 立即失效）
- [x] Web 退出调用 logout
- [x] 185 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P7）**：平台沙箱验证、监控看板、多租户隔离。

---

## v0.25 · Phase 6e 7/7 评测覆盖 + 任务取消 ✅

- [x] 评测 case 覆盖 01–07（新增 02/03/04/05）
- [x] 新机械判据：skus/title/image_plan/video_timing
- [x] `POST /api/tasks/{id}/cancel` + Web「取消任务」
- [x] `cancelled` 状态
- [x] 188 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P7）**：平台沙箱验证、监控看板、多租户隔离。

---

## v0.26 · Phase 7a 限流 / 指标看板 / v1 就绪 ✅

- [x] `RUNTIME_RATE_LIMIT`：每分钟请求限流（429 + Retry-After）
- [x] Web 指标看板：任务数/待审批/评测/失败 + 状态分布条 + 告警摘要
- [x] `docs/17_Runtime_Readiness.md`：v1 就绪清单与缺口
- [x] 190 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P8）**：平台沙箱验证、真实 LLM 冒烟、租户级密钥加密。

---

## v0.27 · Phase 7b 交付审核 / 幂等 / 租户 ✅

- [x] 机器交付审核（状态/产物/证据/信封/合规）
- [x] 人工交付决定 + `delivery_status`
- [x] ZIP 归档（task/artifacts/evidence/envelopes/audits/summary/manifest/assets）
- [x] API `Idempotency-Key`
- [x] 节点耗时/重试记录
- [x] `tenant_id` 租户隔离
- [x] 200 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P8）**：平台沙箱验证、真实 LLM 冒烟、租户级密钥加密。

---

## v0.28 · Phase 8a 租户级模型配置 + Key 加密 ✅

- [x] `ProviderService`：租户级 base_url/model/api_key
- [x] `RUNTIME_SECRET_KEY` + Fernet 加密保存
- [x] `/api/providers` CRUD + `/test` 测试连接
- [x] 创意层按租户选择模型，回退全局 LLM
- [x] 204 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P8b）**：平台沙箱验证、真实 LLM 冒烟、监控看板。

---

## v0.29 · Phase 8b 目录重构 + 系统管理 ✅

- [x] `cross-border-ecommerce-api/`：入口/依赖/Docker/Compose/TLS
- [x] `cross-border-ecommerce-admin/`：零构建单页后台
- [x] 租户 CRUD API + 页面
- [x] 用户 CRUD / 密码重置 API + 页面
- [x] 租户级模型配置 API + 页面（保存/测试）
- [x] `.gitignore` 忽略 `github/`
- [x] 206 个测试通过（2 个 Postgres 集成在无 env 时 skip）

**仍待（P9）**：平台沙箱验证、真实 LLM 冒烟、监控看板。

---

## v1.0 · 串联 📋

- [ ] `workflow.md`：定义完整执行顺序与中断条件（01→02→03→04/05→上架→06/07→回流）
- [ ] 输出统一的「上架素材包」目录结构
- [ ] 一键脚本（把各模块 Prompt 与脚本按顺序串起来）
- [ ] 端到端案例复现验证

## V2 · 接入 API 📋

- [ ] Shopee Open Platform API（商品 / 订单 / 广告数据）
- [ ] Mercado Livre API（items / orders / ads）
- [ ] 关键词数据自动拉取（替代手工导入三榜）
- [ ] **类目数据自动拉取**（替代手工导出，直连 01 的脚本层）
- [ ] 广告数据自动拉取（供 06 使用，去掉手工填表）
- [ ] 评论数据自动拉取（供 07 使用）

## V3 · 网页应用 📋

- [ ] 可视化工作流界面
- [ ] 指标报告可视化（价格曲线、波谷标注、配置交叉表）
- [ ] 素材预览与管理
- [ ] 多店铺 / 多平台切换

## V4 · 自动化 Agent 系统 📋

- [ ] 定时执行（每日数据采集 → 诊断 → 建议）
- [ ] 闭环优化（执行动作 → 回收数据 → 验证效果）
- [ ] 异常告警（CTR 骤降 / ROAS 跌破盈亏线 / 差评激增）

---

## 已知待办（技术债）

| # | 项 | 影响 | 处置 |
|---|---|---|---|
| 1 | ~~SOP 的「9 图生成逻辑」原始清单未提取到~~ | ✅ **已确认采用本仓库推导的 9 图框架** | 已关闭，见 [`04 README`](./Agents/04_Product_Image_Agent/README.md) |
| 2 | SOP 原文说详情页"8 个部分"但只列了 7 项 | 本仓库按 7 段执行 | 待确认是否有缺漏 |
| 3 | 平台字数 / 字段规则可能滞后 | 文档写的是编写时的公开规则 | 已在多处标注"发布前复核"；后续可加自动化校验 |
| 4 | ~~编号体系与原始规划不一致~~ | ✅ **已确认**（按工作簇重排） | 已关闭，见 [`CHANGELOG`](./CHANGELOG.md) |
| 5 | 06/07 的输入依赖手工填表 | 广告数据与评论数据需人工导出整理 | V2 接入 API 后消除 |
| 6 | 复盘数据无法自动回流 | `iterate` 模式需人工把 06/07 的输出粘贴回 03/04 | v1.0 串联后消除 |
| 7 | 01 的数据源依赖手工导出 | 虾多拉导出格式可能变化，需维护 `--mapping` | V2 接 API 后消除 |
| 8 | 脚本未计入巴西税费 | 指标层与定价层都未含税费，实际毛利率会偏低 | 须在使用时自行补税费项，已在文档中标注 |
| 9 | 配置维度抽取为启发式 | 配置只在标题里时靠正则，抽取率可能偏低 | 报告会标出失败数；建议把配置拆成独立列 |

---

## 不打算做的事

为了不误导使用者，明确列出**本工具箱不做**的事：

| 不做 | 原因 |
|---|---|
| 刷单 / 测评工具 | 平台明令禁止，见 [`docs/03_Compliance_Guard.md`](./docs/03_Compliance_Guard.md) |
| 组织性举报竞品的工具 | 不正当竞争 |
| 自动抢预约 / 绕过风控 | 技术手段规避平台规则 |
| 抓取竞品数据并直接复用素材 | 版权风险 |
| 承诺收益 / 保证出单的功能 | 无法负责 |
| **代替人做选品决策** | 02 模块需人工确认 `decision_approved`；选品涉及公司战略、资金与风险偏好，Agent 无法代劳 |

---

**返回**：[项目首页](./README.md) · [架构拆解](./docs/00_Architecture_SOP_to_Agent.md)
