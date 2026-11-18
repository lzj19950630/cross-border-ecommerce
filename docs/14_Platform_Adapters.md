# 14 · 平台动作适配器

> 适用版本：v0.16
> 用一份 YAML 把内部审批动作映射成平台 HTTP 请求；**不内置任何平台的私有 API 字段**。

---

## 一、为什么用配置映射

内部动作是稳定的：

```text
ad.set_bid / ad.set_budget / product.update_price / listing.update_title / image.replace_main
```

平台 API 的 URL、字段、鉴权各不一样，而且会变。把差异放在 YAML 里：

- 换平台只改配置，不改代码；
- 动作映射缺一个就**执行前直接报错**；
- 便于审计：配置文件和代码一起 review。

---

## 二、配置格式

```yaml
name: "shopee-example"
base_url: "https://api.example.com"
timeout: 30
headers:
  Content-Type: "application/json"
auth:
  type: "bearer"              # bearer | header | none
  token_env: "SHOPEE_ACCESS_TOKEN"
actions:
  ad.set_bid:
    method: "POST"
    path: "/ads/campaigns/{target}/bid"
    body:
      campaign_id: "{target}"
      bid: "{after.cpc}"
      reason: "{reason}"
```

### 模板变量

| 变量 | 来源 |
|---|---|
| `{target}` | action.target（路径里会 URL 编码） |
| `{action}` | action.action |
| `{reason}` | action.reason |
| `{before.xxx}` | action.before 的字段 |
| `{after.xxx}` | action.after 的字段 |
| `{envelope_id}` | 审批信封 ID |
| `{module}` | 模块编号（02/03/04/06/07） |
| `{action_type}` | 信封动作类型 |

- 整个字符串就是一个变量（如 `"{after.cpc}"`）→ 保留原始类型（数字/布尔）；
- 嵌入在字符串里 → 转成字符串拼接；
- 变量不存在 → 直接报错，不发请求。

### 鉴权

- `bearer`：`Authorization: Bearer <env>`；
- `header`：自定义头（默认 `X-API-Key`）+ env；
- `none`：不鉴权；
- Token 只从环境变量读取，不写配置文件、不打印。

---

## 三、使用

```bash
export SHOPEE_ACCESS_TOKEN=...
python -m runtime resume <thread_id> \
  --decision approve \
  --apply-adapter Templates/platform_adapter.example.yaml
```

API 服务：

```bash
python -m runtime serve --apply-adapter Templates/platform_adapter.example.yaml
```

优先级：`--apply-adapter` > `--apply-webhook` > dry-run。

---

## 四、执行语义

```text
ApprovalEnvelope
  → 检查所有 action 是否都有映射（缺一个就整体拒绝）
  → 逐条发送 HTTP
  → 2xx = 成功
  → 非 2xx / 网络错误 / 超时 → PlatformAdapterError
  → 审计记录 mode=adapter:<name>
```

注意：

- **部分执行风险**：多条动作逐条发送，若第 2 条失败，第 1 条可能已在平台生效；
  平台侧需要幂等键/事务补偿；本项目不做分布式事务。
- 建议动作按类型拆信封（`ad_bid` / `ad_budget` 分开），降低部分执行影响。
- 适配器只做 HTTP 映射，不做平台字段校验；字段值来自 `before/after` 快照。

---

## 五、重试 / 幂等 / 签名

```yaml
retry:
  attempts: 3          # 只对 5xx / 网络 / 超时重试；4xx 不重试
  backoff: 0.5         # 指数退避：0.5s / 1s / 2s

idempotency_header: "Idempotency-Key"
# 值 = <envelope_id>:<序号>:<action>

signing:
  type: "hmac_sha256"
  secret_env: "PLATFORM_SIGNING_SECRET"
  header: "X-Signature"
  prefix: "sha256="    # 对原始请求体做 HMAC
```

- Token / 签名密钥只从环境变量读取；
- 响应非 2xx 且不可重试 → `PlatformAdapterError`；
- 重试会复用同一 `Idempotency-Key`，平台侧应保证幂等；
- 测试覆盖：重试 3 次、幂等头、HMAC 签名。

---

## 六、示例配置

仓库内：

- [`Templates/platform_adapter.example.yaml`](../Templates/platform_adapter.example.yaml)

包含 `ad.set_bid` / `ad.set_budget` / `product.update_price` / `listing.update_title` /
`image.replace_main` 的占位映射。

> ⚠️ URL 与字段是**占位示例**，必须按目标平台官方 API 文档替换后再用。

---

## 七、测试

`runtime/tests/test_platforms.py` 使用本地 mock HTTP 服务验证：

- 路径变量 + URL 编码；
- body 变量替换与数字类型保留；
- Bearer token；
- 缺映射 / 缺 token → 报错；
- 引擎审批通过后真实调用适配器并写审计。

---

## 八、边界

- 不内置 Shopee / ML / TikTok Shop 私有 API；
- 已支持 HMAC 签名与重试；限流、平台侧事务补偿仍需在网关/平台实现。
- 不做平台侧事务补偿；
- 生产使用前必须用平台沙箱账号验证。

---

**相关**：[Apply/评测](12_Apply_and_Eval.md) · [审批规范](07_Action_Risk_and_Approval.md) · [运维手册](10_Runtime_Operations.md)
