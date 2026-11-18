# cross-border-ecommerce-admin

零构建单页后台（原生 HTML/CSS/JS），由 FastAPI 在 `/` 同源托管。

- 登录 / API Key
- 任务创建、列表、详情
- 审批 / 交付审核 / ZIP 归档
- 证据卡片 / 审计
- 评测 / 评测历史趋势
- 告警 / 指标
- 系统管理：租户 / 用户 / 模型配置（v0.29）

启动：

```bash
python -m runtime serve --port 8000
# http://127.0.0.1:8000/
```

无需 Node / 构建步骤。
