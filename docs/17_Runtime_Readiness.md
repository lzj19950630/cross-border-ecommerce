# 17 · 运行时 v1 就绪清单

> 适用版本：v0.29
> 目的：在继续加功能前，明确"哪些已经能生产用、哪些还缺"。

---

## 一、已具备（可演示 / 内部试用）

| 能力 | 状态 | 位置 |
|---|---|---|
| 7 个 Agent 完整链路 | ✅ | `runtime/agent_runners.py` |
| 意图识别 + 复合任务切片 | ✅ | `intent_router.py` / `planner.py` |
| 审批信封 + 风险分级 | ✅ | `actions.py` |
| 人工审批 interrupt / resume | ✅ | `engine.py` / `supervisor.py` |
| 跨进程 durable 断点 | ✅ SQLite/Postgres | `supervisor.py` |
| 证据链 + 引用校验 | ✅ | `evidence.py` |
| 7/7 金标评测 + LLM judge | ✅ | `evals.py` |
| LLM 创意层（03/04/05/07） | ✅ 默认关闭 | `llm.py` / `creative.py` |
| Web 控制台（任务/审批/证据/评测/告警/指标） | ✅ | `web/index.html` |
| 多用户 / 角色 / 动作级权限 | ✅ | `auth.py` |
| API Key / JWT / 刷新 / 注销 / 吊销 | ✅ | `auth.py` / `api.py` |
| 代理 SSO（oauth2-proxy 风格） | ✅ | `RUNTIME_PROXY_AUTH_SECRET` |
| 限流（每分钟） | ✅ | `RUNTIME_RATE_LIMIT` |
| 指标 / 告警 | ✅ | `/api/metrics` / `/api/alerts` |
| 任务取消 / 导出 / 审计 | ✅ | Web / API |
| 交付审核 + ZIP 归档 | ✅ | 机器+人工+manifest |
| API 幂等 / 节点耗时 | ✅ | `Idempotency-Key` / elapsed_ms |
| 租户隔离 | ✅ | `tenant_id`（API 层） |
| 租户级模型配置 + Key 加密 | ✅ | `providers.py` + Fernet |
| 租户/用户管理页 | ✅ | Web「系统管理」 |
| SQLite / Postgres 存储 | ✅ 实测 | `storage.py` / `sqlalchemy_store.py` |
| Docker / Compose / TLS 样例 | ✅ 配置校验 | `cross-border-ecommerce-api/Dockerfile` / `cross-border-ecommerce-api/deploy/` |
| CI（测试 + Postgres + Docker build） | ✅ 工作流 | `.github/workflows/tests.yml` |

---

## 二、已知缺口（生产前必须处理）

| 缺口 | 影响 | 建议 |
|---|---|---|
| **平台沙箱验证** | 适配器 URL/字段是占位 | 用 Shopee/ML 沙箱账号跑通 `ad.set_bid` 等动作 |
| **Docker 镜像未本机构建** | 本机 Docker Hub 网络阻塞 | 由 CI 构建；或配置镜像加速后本地验证 |
| **LLM 未真实调用** | 创意层只用 FakeLLM 测试 | 用真实 Key 跑一次 03/04/05/07 冒烟 |
| **租户隔离是 API 层** | 数据库仍共享，未做 RLS/分库 | 如对外服务，加 Postgres RLS 或分库 |
| **密码策略** | bcrypt 已支持，但无密码重置/复杂度策略 | 接企业 IdP 或加密码策略 |
| **监控看板** | 只有 Web 指标卡片，无历史趋势 | 接 Grafana/Prometheus |
| **平台签名/重试** | 适配器支持 HMAC/重试，但无平台特定签名 | 按平台文档补签名算法 |
| **依赖版本冲突** | 本机旧 langgraph 与 checkpoint 包声明冲突 | 干净 venv 按 `requirements-runtime.txt` |

---

## 三、v1.0 发布标准（建议）

- [ ] CI 全绿（含 Postgres service + Docker build）；
- [ ] 平台沙箱至少跑通 1 个动作（如广告出价）；
- [ ] 真实 LLM 跑通 1 次创意层冒烟；
- [ ] 生产数据卷/备份/恢复演练完成；
- [ ] TLS 反代 + API Key/JWT + 限流已配置；
- [ ] 审批人培训 + 回滚流程确认；
- [ ] 版本号冻结，README/API/CHANGELOG 对齐。

---

## 四、发布步骤

```bash
# 1) 干净环境
python -m venv .venv && . .venv/bin/activate
pip install -r cross-border-ecommerce-api/requirements.txt

# 2) 全量测试（含 Postgres）
RUNTIME_TEST_POSTGRES_URL=... RUNTIME_TEST_POSTGRES_DSN=... \
  python -m unittest discover -s runtime/tests -v

# 3) 评测
python -m runtime eval Templates/eval_case.yaml

# 4) 自检
python -m runtime doctor

# 5) 构建与启动
docker compose -f cross-border-ecommerce-api/docker-compose.yml up -d --build
```

---

## 五、结论

- **内部试用 / 演示**：已经可以。
- **对外生产**：还差平台沙箱验证、真实 LLM 冒烟、监控看板、多租户（如需）。

建议下一步不要继续堆功能，而是按本清单做**真实环境验证**。

---

**相关**：[运维手册](10_Runtime_Operations.md) · [生产清单](15_Production_Checklist.md) · [HTTP API](11_HTTP_API.md) · [平台适配器](14_Platform_Adapters.md)
