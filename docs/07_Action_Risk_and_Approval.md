# 07 · 动作风险与审批规范

> 本规范对齐 `Multi-Agent-E-commerce-System` 的「效果后置 + 审批批次」：
> 对外动作先登记参数快照，人工批准后才执行；批内同进同退，快照漂移整批回滚。
>
> 代码：`runtime/actions.py` · 模板：[action_approval_envelope.yaml](../Templates/action_approval_envelope.yaml) ·
> 校验：`python -m runtime check-envelope <文件>`

---

## 一、三层风险

| 风险 | 含义 | 例子 | 处理 |
|---|---|---|---|
| `auto` | 只读 / 内部草稿 | 看类目、算指标、写草稿 | 免审，直接执行 |
| `approval` | 对外状态变更 | 改价、改预算、换主图、改 Listing | **必须人工审批** |
| `forbidden` | 平台禁止 / 本项目不做 | 暂停广告、删差评、刷单 | 工具不暴露，直接拒绝 |

---

## 二、动作注册表

| 动作 | 风险 | 所属 Agent | 回滚 |
|---|---|---|---|
| `market.read` | auto | 01 | — |
| `product.update_price` | approval | 02 | 恢复原售价 |
| `product.update_coupon` | approval | 02 | 恢复原券配置 |
| `product.update_sku_structure` | approval | 02 | 恢复原 SKU 列表 |
| `listing.update_title` | approval | 03 | 恢复原标题 |
| `listing.update_description` | approval | 03 | 恢复原详情页 |
| `image.replace_main` | approval | 04 | 恢复原主图 |
| `video.publish` | approval | 05 | 撤回视频 |
| `ad.set_budget` | approval | 06 | 恢复原预算 |
| `ad.set_bid` | approval | 06 | 恢复原出价 |
| `ad.pause` | **forbidden** | 06 | —（本项目明确不暂停广告） |
| `review.patch_listing` | approval | 07 | 恢复原 Listing 片段 |
| `review.request_removal` | **forbidden** | 07 | —（评价操纵） |
| `review.synthetic_review` | **forbidden** | 07 | —（虚假评价） |

> 未知动作一律 `forbidden`（与底座「未知动作默认禁做」一致）。

---

## 三、审批信封字段

```yaml
envelope_id: "ad-20261118-001"
module: "06"
action_type: "ad_budget"
risk: "approval"
decision: "pending"          # pending | approved | rejected
drift_policy: "abort_whole_batch"
requested_by: "agent"
decided_by: null
comment: null
actions:
  - action: "ad.set_budget"
    target: "campaign:123"
    before: {budget: 200}
    after:  {budget: 120}
    reason: "ROAS 低于盈亏线 0.5×，P0 止血"
    evidence: ["ad-report#row-18", "fee-preset#shopee_br"]
    rollback: "恢复 budget=200"
```

### 硬规则

1. `risk` 必须是 `approval`（`auto` 不需要信封；`forbidden` 不许进信封）；
2. 每条动作必须有 `target` / `before` / `after` / `reason` / `evidence` / `rollback`；
3. **`evidence` 不能为空**——动作必须有依据；
4. `approved` 必须记录 `decided_by`；
5. `drift_policy` 只能是 `abort_whole_batch` / `apply_anyway`；
6. 默认 `abort_whole_batch`：任一 `before` 与当前快照不一致 → 整批不动。

---

## 四、与 06 的 P0/P1/P2 的关系

- **P0/P1/P2 是优先级**，回答"先做什么"；
- **risk 是风险级别**，回答"能不能直接做"；
- 两者正交：P0 也可能是 `forbidden`（例如"暂停广告"被禁止），
  P2 也可能需要审批（例如"加预算"）。

示例：

| 诊断 | 优先级 | 建议动作 | 风险 |
|---|---|---|---|
| ROAS < 0.5×盈亏线 | P0 | 降预算 | approval |
| CTR < 2% | P1 | 换主图 | approval（04） |
| ROAS 达标 | P2 | 加预算 | approval |
| 想暂停广告 | P0 | 暂停 | **forbidden** → 改为降预算 |

---

## 五、校验与漂移

```bash
# 校验信封结构/风险/证据/回滚
python -m runtime check-envelope Templates/action_approval_envelope.yaml

# 运行时在 apply 前做快照比对
# 代码：ApprovalEnvelope.check_drift(current_snapshots)
```

漂移示例：

```text
信封 before: {budget: 200}
当前快照:   {budget: 180}   # 别人已经改过
→ 报错：快照漂移，整批回滚，不执行
```

---

## 六、审计

建议在底座里落一张 `approval_batches` 表（或复用其现有审批表），至少记录：

- `envelope_id` / `thread_id` / `slice_no`
- `actions` 参数快照
- `decision` / `decided_by` / `comment` / `decided_at`
- `apply_result`（成功/失败/回滚原因）

这样可以回答：**谁、在什么时候、批准了什么、依据是什么、执行结果如何。**

---

**相关**：[runtime/README](../runtime/README.md) · [集成方案](06_Agent_Runtime_Integration.md) · [证据规范](08_Evidence_and_Citation_Spec.md)

---

## 八、Phase 2 演示（内存 dry-run）

```bash
# 06 广告诊断 → 生成 ad.set_bid 审批信封 → 任务 interrupted
python -m runtime run "广告 ROAS 太低，怎么降预算"

# 同一次进程内批准 → completed；apply 为 dry-run，不改平台后台
python -m runtime run "广告 ROAS 太低，怎么降预算" --decision approve
```

代码路径：

```text
AdvertisingRunner
  → ad_metrics.py diagnose --json
  → 取 P0 广告组
  → ApprovalEnvelope(action=ad.set_bid, before={cpc}, after={affordable_cpc})
  → RuntimeEngine 停在 interrupted
  → resume(approve) → 审计 + dry-run apply
```

Phase 3 接真实底座后，把 `_default_apply` 换成事务内的 `apply_batch_actions` 即可。

---

## 九、SQLite 跨进程审批（v0.9）

```bash
# 1) 运行，停在审批（默认写 .runtime/runtime.db）
python -m runtime run "广告 ROAS 太低，怎么降预算"

# 2) 新进程批准
python -m runtime resume <thread_id> --decision approve --comment "同意降出价"

# 3) 查看任务
python -m runtime task <thread_id>
python -m runtime tasks
```

存储：`tasks` / `envelopes` / `audits` 三张表；审批决定与 apply 结果都会落审计。
默认数据库路径 `.runtime/runtime.db`，可用 `--db` 覆盖。

---

## 十、审计与导出（v0.10）

```bash
# 查看某任务的审批审计（decision / decided_by / comment / apply 结果）
python -m runtime audits <thread_id>

# 导出任务：task.json + summary.md + 产物/证据/信封
python -m runtime export <thread_id> --out ./exports/ad-001
```

`summary.md` 会列出每个切片的证据条数与审批信封，方便人工复核。

---

## 十一、真实 Apply（v0.13）

审批通过后，默认仍为 dry-run；配置 webhook 后会真实 POST：

```bash
python -m runtime resume <thread_id> \
  --decision approve \
  --apply-webhook http://127.0.0.1:9000/apply
```

- 请求体 = `ApprovalEnvelope` JSON；
- `2xx` = 成功，写审计 `mode=webhook`；
- 非 2xx / 超时 = `ApplyError`，不会静默当成功；
- Token 走 `RUNTIME_APPLY_TOKEN`，不打印。

详见 [12_Apply_and_Eval.md](12_Apply_and_Eval.md)。
