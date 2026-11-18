# cross-border-ecommerce-api

FastAPI 运行时入口与部署文件。平台核心代码在仓库根目录的 `runtime/`（共享包，不复制）。

## 开发启动

```bash
# 推荐（本目录内）
cd cross-border-ecommerce-api
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或平台 CLI
python -m runtime serve --port 8000
```

装配参数通过环境变量控制，也可写入本目录 `.env`（参考 `.env.example`，真实环境变量优先）：

```dotenv
RUNTIME_ENGINE=supervisor          # simple | supervisor
RUNTIME_EXECUTOR=langgraph         # auto | sequential | langgraph
RUNTIME_CHECKPOINTER=sqlite        # auto | memory | sqlite
RUNTIME_CHECKPOINT_DB=.runtime/checkpoints.db
RUNTIME_CREATIVE=1                 # 启用 LLM 创意层
```

默认数据目录锚定到仓库根目录 `.runtime/`，从本目录启动与 `python -m runtime serve` 共用同一份数据。

## Docker

```bash
# 在仓库根目录
docker compose -f cross-border-ecommerce-api/docker-compose.yml up -d --build

# 含 Caddy TLS
docker compose \
  -f cross-border-ecommerce-api/docker-compose.yml \
  -f cross-border-ecommerce-api/docker-compose.prod.yml up -d --build
```

- 构建上下文是仓库根目录（`context: ..`）；
- 依赖文件：`requirements.txt`；
- TLS 样例：`deploy/Caddyfile` / `deploy/nginx.conf`；
- 卷：`runtime-data` / `pgdata`。

## 环境变量

见 `docker-compose.yml`；核心变量：

```dotenv
RUNTIME_DB_URL=postgresql+psycopg://runtime:runtime@db:5432/runtime
RUNTIME_CHECKPOINT_DSN=postgresql://runtime:runtime@db:5432/runtime
RUNTIME_API_KEY=...
RUNTIME_JWT_SECRET=...
RUNTIME_SECRET_KEY=...
RUNTIME_LLM_BASE_URL=...
RUNTIME_LLM_MODEL=...
RUNTIME_LLM_API_KEY=...
```

## 与 admin 的关系

- `../cross-border-ecommerce-admin/` 是零构建 Web 控制台；
- FastAPI 在 `/` 同源托管它；
- API 文档：`/docs`。
