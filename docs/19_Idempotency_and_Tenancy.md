# 19 · 幂等、执行耗时与租户隔离

> 适用版本：v0.27

---

## 一、API 幂等

```bash
POST /api/tasks
Idempotency-Key: <唯一键>
```

- 同一租户 + 同一 owner + 同一 key → 返回已存在任务；
- 响应里带 `idempotent_replay: true`；
- 也支持 body 字段 `idempotency_key`；
- 当前是**应用层扫描**实现，不是数据库唯一索引；高并发下仍可能重复，生产建议加唯一索引。

---

## 二、执行耗时

任务切片现在记录：

| 字段 | 含义 |
|---|---|
| `started_at` / `finished_at` | 节点起止时间 |
| `elapsed_ms` | 耗时（毫秒） |
| `retries` | LLM 创意层重试次数 |

Web 任务详情表格已展示耗时列。

---

## 三、租户隔离

### 配置

API Key：

```bash
export RUNTIME_API_KEYS='{
  "acme-key": "acme:alice:admin",
  "beta-key": "beta:bob:operator"
}'
```

格式：`tenant:name:role`；两段格式 `name:role` 仍兼容（tenant 为空）。

JWT 用户：

```json
{"alice": {"password_bcrypt": "...", "role": "admin", "tenant": "acme"}}
```

代理 SSO：

```text
X-Proxy-Auth: <secret>
X-Auth-Request-User: alice
X-Auth-Request-Role: admin
X-Auth-Request-Tenant: acme
```

### 行为

- 任务写入 `tenant_id`；
- 有 tenant 的 principal 只能看到同 tenant 的任务；
- admin 在 tenant 内看全部，operator/viewer 只看自己的；
- 无 tenant 的旧 API Key = 全局 admin（兼容旧用法）；
- 旧任务 `tenant_id=""` 对有 tenant 的用户不可见。

### 边界

- 隔离在 API/Repository 层，数据库仍是共享库；
- 若要物理隔离，按租户分库或加 RLS；
- 没有租户管理 UI/创建流程，当前靠环境变量配置。

---

**相关**：[多用户/角色](16_Multi_User_and_Roles.md) · [HTTP API](11_HTTP_API.md) · [生产清单](15_Production_Checklist.md)
