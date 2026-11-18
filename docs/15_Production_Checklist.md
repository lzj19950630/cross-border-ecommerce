# 15 · 生产上线清单

> 适用版本：v0.29
> 目标：把本地原型推进到"可给别人用"的最小生产形态。

---

## 一、安全

- [ ] **开启认证**：单密钥 `RUNTIME_API_KEY=<强随机值>`，或多用户
  `RUNTIME_API_KEYS='{"key1":"alice:admin","key2":"bob:operator"}'`
  - `/api/*` 默认需要 `Authorization: Bearer <key>` 或 `X-API-Key`；
  - `/api/health` 与 `/` 保持公开。
- [ ] **Web 控制台填 Key**：页面右上角输入后存 localStorage；换人/换机需重新输入。
- [ ] **角色分配**：admin/operator/viewer 按人发放，审批人至少 operator。
- [ ] **JWT（可选）**：`RUNTIME_JWT_SECRET` + `RUNTIME_USERS`；密码用慢哈希（当前实现是 sha256，生产建议改造）。
- [ ] **动作权限**：`RUNTIME_ACTION_ROLES` 限制高危动作（如改价仅 admin）。
- [ ] **TLS 反向代理**：Nginx/Caddy/Traefik 终止 TLS，内网只暴露反代端口；样例见 [`cross-border-ecommerce-api/deploy/`](../cross-border-ecommerce-api/deploy/README.md)。
- [ ] **CORS 白名单**：`RUNTIME_CORS_ORIGINS=https://your-console.example.com`；
  不设置则同源访问（推荐）。
- [ ] **密钥不进仓库**：`.env`、`*.key` 已在 `.gitignore`；用环境变量/Secret Manager。
- [ ] **租户模型 Key**：`RUNTIME_SECRET_KEY` 放 Secret Manager；丢失会导致已存 Key 无法解密。
- [ ] **轮换**：API Key / LLM Key / 平台 Token 定期轮换；审计里保留 decided_by。
- [ ] **JWT 注销**：用户退出/离职调用 `/api/auth/logout`；refresh 会轮换旧 token。
- [ ] **限流**：反代层限流 + `RUNTIME_RATE_LIMIT`（应用内单进程）；多实例请用 Redis/网关。
- [ ] **代理 SSO（可选）**：`RUNTIME_PROXY_AUTH_SECRET` + 反代注入用户/角色头；反代必须剥离客户端同名头。
- [ ] **上传边界**：当前 API 不接收文件；若后续加，限制大小与类型。

---

## 二、数据与持久化

- [ ] **任务库**：
  - 单机：默认 `.runtime/runtime.db`（SQLite）；
  - 生产：`RUNTIME_DB_URL=postgresql+psycopg://user:pass@host:5432/runtime`。
- [ ] **LangGraph 断点**：
  - `--checkpointer sqlite --checkpoint-db /data/checkpoints.db`；或
  - `--checkpointer postgres --checkpoint-db <DSN>`（需 `langgraph-checkpoint-postgres` + `psycopg`）。
- [ ] **备份**：SQLite 文件 + checkpoints 文件；Postgres 用 pg_dump（已用 Docker Postgres 验证存储/断点）。
- [ ] **CI**：`.github/workflows/tests.yml` 含 Postgres service，合并前必须绿。
- [ ] **恢复演练**：至少验证一次"备份 → 恢复 → 任务可读"。
- [ ] **保留策略**：审计/任务保留周期（如 90 天），避免无限增长。

---

## 三、部署

```bash
docker compose -f cross-border-ecommerce-api/docker-compose.yml up -d --build
# 可选 TLS 反代
docker compose -f cross-border-ecommerce-api/docker-compose.yml -f cross-border-ecommerce-api/docker-compose.prod.yml up -d
```

- 卷：`runtime-data:/data`；
- 端口：`8000`（建议只在内网监听，由反代暴露）；
- 健康检查：`GET /api/health`；
- 日志：`docker compose logs -f runtime`。

### 环境变量

```dotenv
RUNTIME_API_KEY=...
RUNTIME_CORS_ORIGINS=https://console.example.com
RUNTIME_DB_URL=postgresql+psycopg://runtime:...@db:5432/runtime
RUNTIME_CHECKPOINT_DSN=postgresql://runtime:...@db:5432/runtime
RUNTIME_LLM_BASE_URL=https://api.openai.com/v1
RUNTIME_LLM_MODEL=gpt-4.1-mini
RUNTIME_LLM_API_KEY=...
RUNTIME_APPLY_TOKEN=...
```

---

## 四、平台执行

- [ ] 用**沙箱账号**验证 `platform_adapter.example.yaml` 的 URL/字段；
- [ ] 动作按类型拆信封（出价/预算/改价分开），降低部分执行影响；
- [ ] 平台侧幂等键/补偿策略已确认；
- [ ] 请求签名（HMAC 等）在适配器或网关层实现；
- [ ] 失败告警：`PlatformAdapterError` 进日志/通知；
- [ ] 审批人培训：批准前看 `before/after/evidence/rollback`。

---

## 五、LLM / 成本

- [ ] `--creative` 默认关闭；只在需要时开启；
- [ ] 设定模型/超时/并发上限（当前单请求）；
- [ ] 监控 token 成本；
- [ ] LLM 失败回退确定性结果，不阻塞任务；
- [ ] judge 只在评测时启用，不进入用户请求链路。

---

## 六、可观测性

- [ ] `/api/health` 进探针；`/api/metrics` / `/metrics` 接 Prometheus；`/api/alerts` 接告警；
- [ ] 任务失败/审批拒绝/适配器失败有日志；
- [ ] 审计表可作为审批追溯源；
- [ ] 建议接入 Langfuse/OpenTelemetry（当前未内置）。

---

## 七、已知边界

- Web 无多用户/角色；API Key 是单租户密钥；
- 无请求签名/重试/限流/分布式事务；
- 平台 API 字段是占位示例；
- 依赖版本需按 `cross-border-ecommerce-api/requirements.txt` 在干净 venv 对齐。

---

## 八、上线前 5 分钟检查

```bash
python -m runtime doctor
python -m runtime eval Templates/eval_case.yaml
python -m runtime serve --port 8000 --checkpointer sqlite
curl -s localhost:8000/api/health
```

再确认：

- [ ] API Key 已设置
- [ ] CORS 白名单已设置
- [ ] 数据卷已挂载
- [ ] 备份任务已配置
- [ ] 平台适配器已在沙箱验证
- [ ] 审批人知道怎么批准/拒绝

---

**相关**：[运维手册](10_Runtime_Operations.md) · [HTTP API](11_HTTP_API.md) · [平台适配器](14_Platform_Adapters.md) · [Apply/评测](12_Apply_and_Eval.md) · [v1 就绪清单](17_Runtime_Readiness.md)
