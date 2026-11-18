# 09 · 金标评测场景规范

> 目标：把"案例 + 人工自检"升级成可回归的评测线。
> 对齐 `Multi-Agent-E-commerce-System` 的做法：固定输入、YAML 真源、run/score 解耦、
> 机械判据 + LLM judge、0/1 + 理由、不适用不判通过。
>
> 模板：[eval_case.yaml](../Templates/eval_case.yaml)

---

## 一、为什么需要

现在改 Prompt 后，效果好不好主要靠人看案例。问题是：

- 没有固定输入，无法对比"改前/改后"；
- 没有评分标准，两个人看同一份产出会得出不同结论；
- 没有机械检查，数字漂移/引用缺失只能靠肉眼。

金标评测线解决这三件事。

---

## 二、场景格式

```yaml
version: 1
scenarios:
  - id: "patinete-market-01"
    surface: "01 市场分析"          # 评测面（对应 Agent）
    input: "分析一下巴西站电动滑板车类目的市场机会"   # 固定输入，LLM 不生成
    rubric:                        # 判据，每条 0/1 + 理由
      - "价格带下界能由 market_metrics.py 复算"
      - "配置机会与头部占据做了交叉判断"
      - "结论区分了【数据】/【判断】/【待确认】"
    deterministic_checks:          # 零 LLM 的机械检查
      - "number_traceable"
      - "required_sections"
    note: "锁定 01 的核心判断链"
```

### 硬规则

1. **输入必须是固定文本**，不能让 LLM 生成评测输入；
2. `id` 全局唯一；
3. `rubric` 非空且不重复；
4. `surface` 必须对应一个 Agent；
5. 判据要可判定，不写"写得好"这种主观描述。

---

## 三、run / score 解耦

| 阶段 | 做什么 | 成本 |
|---|---|---|
| **run** | 用固定输入真跑一次，落产出快照 | 贵（LLM + 工具） |
| **score** | 从快照回评，按 rubric 打分 | 便宜（只烧 judge token） |

好处：改 rubric 或换 judge 时，不需要重跑任务。

---

## 四、两类判据

### 机械判据（零 LLM）

- `number_traceable`：数字必须能在证据块/脚本输出里找到；
- `required_sections`：输出必须含指定章节；
- `attribution_sum`：归因合计 = 差评数；
- `action_envelope_valid`：动作信封通过校验；
- `no_forbidden_action`：不得出现 `forbidden` 动作；
- `citation_resolvable`：正文 `[n]` 必须解析到证据。

### LLM judge

- 判断"引用是否支撑结论"；
- 判断"卖点是否真实、是否有夸大"；
- 判断"文案是否符合 PT-BR 母语表达"。

### 0/1 + 第三值

- 每条判据：`1` 通过 / `0` 失败 / `N/A` 不适用；
- **不适用不能算通过**，否则会稀释跨场景指标。

---

## 五、建议的首批场景

| surface | 场景 | 重点 |
|---|---|---|
| 01 市场分析 | 电动滑板车巴西类目 | 价格带复算、配置交叉判断 |
| 02 产品策略 | 充电宝定价 | 盈亏线、SKU 四角色、券余量 |
| 03 Listing | 充电宝标题/详情 | 字符限制、参数溯源、PT-BR |
| 06 广告 | 充电宝广告诊断 | 盈亏线、P0/P1/P2、不暂停广告 |
| 07 评论 | 电动滑板车差评 | 八类归因、误解型、修补文案 |

---

## 六、落地顺序

1. 先做 **机械判据**（不需要 LLM，最稳定）；
2. 再把现有 `Examples/` 转成固定输入；
3. 最后加 LLM judge，且只对机械判据覆盖不到的维度使用；
4. 每次改 Prompt/SKILL.md，先跑机械判据，再抽样跑 judge。

---

## 七、与现有自检清单的关系

- `docs/04_Result_Checklist.md` 是**人工交付前**的逐项检查；
- 金标评测是**改 Prompt 后**的回归检查；
- 两者不冲突：清单保证单次交付质量，评测保证长期不退化。

---

**相关**：[集成方案](06_Agent_Runtime_Integration.md) · [审批规范](07_Action_Risk_and_Approval.md) · [证据规范](08_Evidence_and_Citation_Spec.md)

---

## 八、运行时确定性评测（v0.13）

```bash
python -m runtime eval Templates/eval_case.yaml
```

实现：`runtime/evals.py`
- 固定输入 → 跑 `RuntimeEngine`；
- 机械判据：`number_traceable` / `required_sections` / `action_envelope_valid` /
  `no_forbidden_action` / `attribution_sum`；
- 不调 LLM、不写数据库（内存 store）；
- 输出 `ok/passed/failed/cases`，可直接进 CI。

当前模板 7 个场景（01–07）全部通过。新增场景只需在 YAML 里加 `deterministic_checks`。
