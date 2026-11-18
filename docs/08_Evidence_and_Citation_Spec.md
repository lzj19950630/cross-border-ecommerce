# 08 · 证据链与引用规范

> 目标：让"不编数据"从一条原则变成可机械校验的交付要求。
> 对齐 `Multi-Agent-E-commerce-System` 的切块级溯源与机械防伪引。
>
> 代码：`runtime/evidence.py` · 模板：[evidence_block.yaml](../Templates/evidence_block.yaml) ·
> 校验：`python -m runtime check-evidence --text <正文> --evidence <证据块>`

---

## 一、基本规则

1. **每个结论/数字都要有证据**：来源 + 定位（行号、字段、切块、评论 ID 等）；
2. 正文用 `[1]`、`[2]` 引用证据清单的第 n 条；
3. 正文里的 `[n]` **必须能解析到证据清单**；解析不到 = 疑似伪造，直接报错；
4. 没有证据的结论 → 报 `[EVIDENCE_MISSING]`，不许交付；
5. 证据不存在/查不到 → 写"未查到"，不编；
6. 某些检查项确实不适用 → 用"不适用（N/A）"，不要强行判"通过"。

---

## 二、证据类型

| `evidence_type` | 用于 | `source` 示例 | `locator` 示例 |
|---|---|---|---|
| `spec_table` | 参数/规格 | 03 输出的 `spec_table` | `capacity` |
| `data_file` | 类目/评论原始数据 | `samples/sample_patinete_eletrico.csv` | `row 18` |
| `ad_report` | 广告报表 | `sample-ad-report.csv` | `row 18 / group=G2` |
| `review` | 评论原文 | `sample-reviews.csv` | `review_id=8821` |
| `fee_rule` | 平台费率 | `platform_fees.json` | `shopee_br.tiers` |
| `platform_rule` | 平台规则 | 官方规则页 | `章节/条款` |
| `metric_report` | 脚本输出指标 | `market_metrics.py` stdout | `price_bands[2]` |
| `manual` | 人工确认 | 人工记录 | `会议/日期` |

---

## 三、证据块格式

```yaml
items:
  - claim_id: "C-06-01"
    claim: "该组 CTR 为 1.2%，低于 2% 基准"
    evidence_type: "ad_report"
    source: "Agents/06_Advertising_Optimization_Agent/examples/sample-ad-report.csv"
    locator: "row 18 / group=G2"
    retrieved_at: "2026-11-18"
    confidence: 1.0
```

### 校验规则

- `claim_id` 唯一、非空；
- `claim` 非空；
- `evidence_type` 必须在允许集合内；
- `source` / `locator` 非空；
- `retrieved_at` 必须是 `YYYY-MM-DD`；
- `confidence` 必须在 0~1（可选）。

---

## 四、正文引用示例

```markdown
## 诊断结论

该组 CTR 为 1.2%，低于 2% 基准 `[1]`；按 Shopee BR 的佣金分档，
该价格带的佣金率为 14% `[2]`。盈亏线 ROAS 为 2.82 `[3]`。

> 证据：
> [1] sample-ad-report.csv · row 18 / group=G2
> [2] platform_fees.json · shopee_br.tiers
> [3] ad_metrics.py calc · stdout / breakeven_roas
```

校验：

```bash
python -m runtime check-evidence --text output.md --evidence evidence.json
```

---

## 五、各模块怎么用

| 模块 | 必须带证据的内容 |
|---|---|
| 01 市场分析 | 容量/集中度/价格带/配置机会的每个数字 |
| 02 产品策略 | 成本、费率、净利率、盈亏价、券余量 |
| 03 Listing | 标题/卖点里的参数，必须能追到 `spec_table` |
| 04 图片 | 图内参数、认证声明、包装清单 |
| 05 视频 | 台词里的每个数字 |
| 06 广告 | 花费、CTR、CVR、ROAS、盈亏线、动作依据 |
| 07 评论 | 每条归因引用评论原文；修补建议对应评论类别 |

---

## 六、与审批信封的关系

审批信封里的每条动作都必须有 `evidence`：

```yaml
actions:
  - action: "ad.set_budget"
    evidence:
      - "ad-report#row-18"
      - "fee-preset#shopee_br"
```

没有证据的动作 = 没有依据的对外变更，审批层应直接拒绝。

---

## 七、失败语义

| 情况 | 标记 | 行为 |
|---|---|---|
| 输入字段缺失 | `[INPUT_MISSING]` | 停止，列出缺失字段 |
| 证据缺失 | `[EVIDENCE_MISSING]` | 停止，不许交付 |
| 数字无法溯源 | `[UNTRACEABLE_NUMBER]` | 停止，回到数据源 |
| 指标可疑 | `[METRIC_SUSPECT]` | 标注并人工复核 |
| 不适用 | `[NOT_APPLICABLE]` | 不判通过、不判失败 |
| 部分完成 | `[PARTIAL]` | 输出"未完成 + 原因" |

---

**相关**：[集成方案](06_Agent_Runtime_Integration.md) · [审批规范](07_Action_Risk_and_Approval.md) · [评测规范](09_Eval_Golden_Scenarios.md)
