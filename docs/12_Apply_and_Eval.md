# 12 · 真实 Apply 与确定性评测

> 适用版本：v0.13
> 两件事：审批通过后怎么真的执行；改了 Prompt/工具后怎么快速回归。

---

## 一、Webhook Apply

### 原理

审批通过后，`ApprovalEnvelope` 会被 POST 到外部执行器：

```text
RuntimeEngine.resume(approve)
  → decide_pending
  → apply_fn(envelope)
  → POST <webhook-url>
  → 2xx = applied
  → 写入 audits
```

### 启动

```bash
# 默认 dry-run；配置 webhook 后真实调用
python -m runtime resume <thread_id> \
  --decision approve \
  --apply-webhook http://127.0.0.1:9000/apply
```

```bash
# API 服务
python -m runtime serve --apply-webhook http://127.0.0.1:9000/apply
```

Token：

```bash
export RUNTIME_APPLY_TOKEN=your-token
```

请求头：`Authorization: Bearer <token>`。

### 请求体

```json
{
  "envelope_id": "ad-...",
  "module": "06",
  "action_type": "ad_bid",
  "risk": "approval",
  "decision": "approved",
  "actions": [
    {
      "action": "ad.set_bid",
      "target": "campaign:B 精准匹配-参数词",
      "before": {"cpc": 0.25},
      "after": {"cpc": 0.0844},
      "reason": "ROAS 1.35 < 盈亏线一半（2.82）—— P0 止血",
      "evidence": ["ad-report#B 精准匹配-参数词", "ad-metrics#affordable_cpc"],
      "rollback": "恢复 cpc=0.25"
    }
  ]
}
```

### 响应

- `2xx`：成功；响应体非 JSON 时按文本截断记录；
- 非 `2xx` / 网络错误 / 超时：抛 `ApplyError`，审批不会静默当成功；
- 审计记录：

```json
{"mode": "webhook", "status": 200, "actions": ["ad.set_bid"]}
```

### 安全边界

- 不执行任意 shell；
- Token 只从参数/环境变量读取，不打印；
- 默认 dry-run，必须显式配置 webhook 才会外部调用；
- 真实平台适配器（Shopee/ML API）建议放在 webhook 后面的执行服务里。

---

## 二、确定性评测

### 命令

```bash
python -m runtime eval Templates/eval_case.yaml
```

输出：

```json
{
  "ok": true,
  "passed": 3,
  "failed": 0,
  "cases": [
    {"id": "patinete-market-01", "status": "completed", "passed": true, "checks": [...]}
  ]
}
```

### 现有机械判据

| 判据 | 检查 |
|---|---|
| `number_traceable` / `evidence_present` | 每个产物都有证据条目 |
| `required_sections` | 产物/切片非空 |
| `action_envelope_valid` | 审批信封通过 `ActionRegistry` 校验 |
| `no_forbidden_action` | 信封里没有 forbidden 动作 |
| `attribution_sum` | 07 的归因差异为 0 |

### LLM judge（可选）

```bash
python -m runtime eval Templates/eval_case.yaml --judge
```

- 每条 rubric 由 LLM 判 0/1 + 理由；
- 判据数量不符/非布尔 → `judge_error`，case 失败；
- 测试用 `FakeLLM`，不真实调用；
- 需要 LLM 配置（`RUNTIME_LLM_*` / `OPENAI_*`）。

### 评测历史

```bash
curl -X POST /api/evals          # 跑一次并保存
curl /api/evals                  # 最近 20 次
```

Web 控制台「评测历史」可查看趋势图 + `created_at/ok/passed/failed`。历史存储：
InMemory / SQLite（`eval_runs` 表）/ Postgres（`runtime_eval_runs`）。

### 新增场景

在 `Templates/eval_case.yaml`（或任意 YAML/JSON）追加：

```yaml
- id: "my-case-01"
  surface: "06 广告诊断"
  input: "固定输入，LLM 不生成"
  rubric:
    - "判据 1"
  deterministic_checks:
    - "number_traceable"
    - "action_envelope_valid"
```

- 输入必须是固定文本；
- `id` 全局唯一；
- 未知检查项会直接失败；
- 不跑 LLM，零成本、可进 CI。

---

## 三、边界

- Webhook 是通用执行接口，不内置平台 API；
- 评测是确定性检查，不替代 LLM judge；
- 尚未接前端评测看板。

---

**相关**：[运行时 README](../runtime/README.md) · [运维手册](10_Runtime_Operations.md) · [HTTP API](11_HTTP_API.md) · [审批规范](07_Action_Risk_and_Approval.md) · [评测规范](09_Eval_Golden_Scenarios.md) · [LLM 创意层](13_LLM_Creative_Layer.md) · [平台适配器](14_Platform_Adapters.md)
