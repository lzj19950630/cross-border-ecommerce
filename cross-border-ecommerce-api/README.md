# cross-border-ecommerce-api

FastAPI 运行时入口与部署文件。平台核心代码在仓库根目录的 `runtime/`（共享包，不复制）。

## 开发启动

```bash
# 推荐
python -m runtime serve --port 8000

# 或直接跑本目录入口
python cross-border-ecommerce-api/main.py
```

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
