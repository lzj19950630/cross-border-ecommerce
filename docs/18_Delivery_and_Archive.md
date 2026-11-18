# 18 · 交付审核与归档

> 适用版本：v0.27
> 流程：机器审核 → 人工交付决定 → ZIP 归档。

---

## 一、交付状态

| 状态 | 含义 |
|---|---|
| `not_reviewed` | 尚未机器审核 |
| `pending` | 机器审核通过，等待人工决定 |
| `passed` | 人工通过，可下载 ZIP |
| `rejected` | 人工拒绝 |
| `failed` | 机器审核未通过 |

---

## 二、机器审核

```bash
POST /api/tasks/{thread_id}/delivery/review
```

检查项：

- 任务状态必须 `completed`；
- 至少一个产物；
- 每个产物都有证据；
- 证据块通过 `EvidenceBlock.validate`；
- 审批信封通过 `ActionRegistry` 校验；
- 确定性合规扫描（禁用词/绝对化表述）；
- 任务无 error。

结果写入 `task.delivery_review.machine`，通过则 `delivery_status=pending`，否则 `failed`。

---

## 三、人工交付决定

```bash
POST /api/tasks/{thread_id}/delivery/decision
{
  "decision": "approve | reject",
  "note": "可选"
}
```

- 必须先通过机器审核（否则 409）；
- 记录 `reviewer / reviewed_at / note`；
- `approve` → `delivery_status=passed`；
- `reject` → `delivery_status=rejected`。

---

## 四、ZIP 归档

```bash
GET /api/tasks/{thread_id}/archive
```

只有 `delivery_status=passed` 才能下载，否则 409。

ZIP 内容：

```text
task.json
summary.md
manifest.json
artifacts/<agent>.json
evidence/<agent>.json
envelopes/<id>.json
audits.json
assets/<本地引用的图片/脚本等>
```

- 资产只包含**项目目录内**、且被 artifact 的 `image_path / script_file / reference_image / file / path` 字段引用的文件；
- 不会打包项目目录外的任意路径。

---

## 五、Web 控制台

任务详情：

- `completed` + `not_reviewed/failed` → 「机器审核」；
- `pending` → 「通过交付 / 拒绝交付」；
- `passed` → 「下载 ZIP」。

---

## 六、边界

- 归档是本地 ZIP，不依赖 MinIO/S3；
- 机器审核是确定性检查，不替代人工审美/业务判断；
- 合规扫描只覆盖禁用词/绝对化表述，平台特定规则仍需人工复核；
- 取消任务不会撤销已 apply 的外部动作。

---

**相关**：[HTTP API](11_HTTP_API.md) · [证据规范](08_Evidence_and_Citation_Spec.md) · [审批规范](07_Action_Risk_and_Approval.md) · [生产清单](15_Production_Checklist.md)
