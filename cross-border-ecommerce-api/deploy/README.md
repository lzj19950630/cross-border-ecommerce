# deploy · TLS 反代样例

> 生产建议：只暴露反代（80/443），`runtime:8000` 只在 Docker 内网。

---

## 方式 A · Caddy（推荐，自动 HTTPS）

```bash
docker compose -f cross-border-ecommerce-api/docker-compose.yml -f cross-border-ecommerce-api/docker-compose.prod.yml up -d
```

- Caddy 自动申请/续期证书；
- 修改 `deploy/Caddyfile` 的域名；
- 反代到 `runtime:8000`。

## 方式 B · Nginx

1. 把 `deploy/nginx.conf` 放到 Nginx 配置目录；
2. 证书放到 `/etc/nginx/certs/`；
3. 反代到 `runtime:8000`；
4. `limit_req_zone`/`limit_req` 已给出基础限流示例。

---

## 必要检查

- [ ] 域名 DNS 已指向反代；
- [ ] TLS 证书有效；
- [ ] `RUNTIME_API_KEY` / `RUNTIME_API_KEYS` / JWT 已配置；
- [ ] `RUNTIME_CORS_ORIGINS` 只放自己的控制台域名；
- [ ] 8000 端口未直接暴露到公网；
- [ ] `/api/health` 接监控探针；
- [ ] 访问日志/错误日志已接入。

## 已知边界

- 反代只做 TLS/限流，不做认证；
- WebSocket 未使用（当前是 REST）；
- Caddy/Nginx 配置未在本机启动验证，按环境调整。
