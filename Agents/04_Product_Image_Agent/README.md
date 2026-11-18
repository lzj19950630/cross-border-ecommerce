# 04 · Product Image Agent

**主图与详情图生成智能体** · 从一句卖点，到 9 张可直接出图的 Prompt——
v0.5 起还可以选配**批量渲染执行层**，直接调用 OpenAI 兼容图片 API 出图。

> **v0.5 新增**：Campaign Style Lock（多图一致性）、Product Angle Sheet（产品身份基准）、
> `render_openai.py`（单张渲染）、`render_prompt_pack.py`（批量渲染 + 自动跳过非 AI 图位 + 出图后校验）。
> **边界不变**：图内文字仍由设计工具后期叠字；包装清单图仍必须实拍。

---

## 一、它解决什么问题

图片是转化率杠杆最大的部分——但也是最容易做错的部分。

| 痛点 | 表现 | 本模块怎么解 |
|---|---|---|
| **9 张图不知道放什么** | 拍了一堆图，功能重复，关键信息缺 | 固定 9 图分工框架，每张图有明确职责 |
| **主图平台规范踩雷** | ML 主图加文字被下架；Shopee 主图没卖点点击低 | `platform_variant` 参数，输出两套方案 |
| **出图 Prompt 写不出效果** | 丢给 AI 一句话，出来的图不能用 | 结构化 Prompt：主体 + 材质 + 光位 + 构图 + 参数 + 负面词 |
| **图内文案超长** | 图上文字挤成一团，买家看不清 | 每张图标注字数上限 + 实际字数 |

**产出物**：9 图内容规划表 + 每张图的出图 Prompt（含负面词）+ 图内文案 + 合规校验。

---

## 二、9 图框架的来历（已确认采用）

SOP 3.3 写了一句：

> **9 张电商图片生成逻辑**：「9 张图片建议按照以下顺序生成：」

**这句话后面的具体清单，在原始 PDF 里是图片形式，文本提取无法还原。** 因此本模块的 9 图框架是**基于 SOP 的详情页 7 段结构 + 平台图片规范推导**出来的。

> ✅ **2026-10-13 已确认：采用本仓库推导的 9 图框架。** 不再等待 SOP 原文补充。
> 推导依据与职责划分见下方第五节。若日后拿到 SOP 原始清单且与本框架不一致，按 SOP 原文校准并更新 [`CHANGELOG`](../../CHANGELOG.md)。

**推导逻辑**（三步，可复核）：

| 步骤 | 依据 | 产出 |
|---|---|---|
| 1 | SOP 详情页 7 段结构（欢迎语/卖点/场景/参数/售后/注意/标签） | 转换出"信息型图位"：卖点图、参数图、场景图、售后图 |
| 2 | 平台硬规范（Shopee 主图可带字 / ML 禁字；ML 需保修图） | 补出"主图"与"售后/保修图"，且标出平台差异 |
| 3 | 差评高发项（配件缺失、尺寸不符预期） | 补出"尺寸/对比图"与"包装清单图" |

> 第 3 步是本框架与"通用 9 图模板"的区别：**它把「差评对冲」作为图位的设计目标之一**，而不是只考虑"展示产品"。

---

## 三、覆盖的 SOP 章节

| SOP | 内容 | 落在哪个 Prompt |
|---|---|---|
| **3.3** | 9 张电商图片生成逻辑 | `01_image_plan_9grid.md` |
| **3.3** | 详情页内容框架（用作图片信息源） | `01_image_plan_9grid.md` |
| **2.3** | 新店多店铺同款需做图片差异化 | `01_image_plan_9grid.md`（variant 模式） |
| **3.6** | 广告没点击 → 换主图 | `02_image_prompt_generator.md`（iterate 模式） |
| 全章 | 图片合规 | `00_system.md` 内的 IMAGE COMPLIANCE GUARD |

---

## 四、工作流

```text
输入：03 Listing Creative 的输出（core_selling_point / secondary_points / spec_table / forbidden_words）
        ▲
        └── 【阻塞规则】core_selling_point 或 forbidden_words 为空 → 拒绝执行，报错
                         ▼
        ┌──────────────────────────────────┐
        │ 00_system.md                     │  角色 + 平台图片规范 + 图片合规守卫
        └──────────────┬───────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │ 01_image_plan_9grid.md           │  Step 1  9 图内容规划（每张图放什么）
        │                                  │  Step 2  图内文案撰写（含字数控制）
        └──────────────┬───────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │ style-lock.md                    │  Step 3  建 Campaign Style Lock
        │ product-angle-sheet.md           │  Step 3.5（可选）生成 Angle Sheet
        └──────────────┬───────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │ 02_image_prompt_generator.md     │  Step 4  逐图生成出图 Prompt
        │                                  │  Step 5  负面 Prompt + 合规校验
        └──────────────┬───────────────────┘
                       ▼
        输出：output_image_prompt_pack.yaml
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  通道 A/C：交给 ImageGen      通道 B：render_prompt_pack.py
  / Midjourney / 即梦          （无 API 自动降级为 Prompt）
          │                         │
          └────────────┬────────────┘
                       ▼
        check_main_image.py 像素级校验（不过不交付）
```

**本模块的边界**：

- **默认不强制渲染**：只出「规划 + Prompt + 校验」也能完整交付；
- 通道 B 是**可选执行层**，不配置 API 时自动降级为只输出 Prompt；
- **图内文字仍由设计工具后期叠字**，渲染器不会把 `overlay_copy` 送进图像模型；
- 渲染后的品控由 [`docs/04_Result_Checklist.md`](../../docs/04_Result_Checklist.md) 的 C 段负责。

---

## 四·五、Skill 形态（v0.4 新增，v0.5 扩展）

本模块已按社区标准 Skill 结构组织（对标 GitHub 头部电商生图 Skill），
**可以被 Claude Code / Codex / Cursor / WorkBuddy 等任何读取 `SKILL.md` 的 Agent 直接安装调用**：

```text
04_Product_Image_Agent/
├── SKILL.md                        # Agent 入口：意图识别 → 规则路由 → 出图 → 校验
├── references/
│   ├── platform-shopee.md          # Shopee 巴西规则卡（首图推荐叠字 / 2MB 上限 / 9 图）
│   ├── platform-mercadolivre.md    # ML 规则卡（2026 新规：背景按类目 / 占比 95% / 首图禁促销文字）
│   ├── platform-amazon.md          # Amazon 对照卡（最严白底标准）
│   ├── scenarios-9grid.md          # 9 图场景库（每图位：目的/构图/prompt 骨架/平台差异）
│   ├── style-lock.md               # 多图一致性规则卡（v0.5）⭐
│   └── product-angle-sheet.md      # 产品角度基准图规则卡（v0.5）⭐
├── scripts/
│   ├── check_main_image.py         # 像素级合规校验 + --fix 自动修复（Pillow）⭐
│   ├── render_openai.py            # 单张渲染：OpenAI 兼容 API（纯标准库）⭐
│   ├── render_prompt_pack.py       # 批量渲染：读图包 / 跳过非 AI 图位 / 自动校验 ⭐
│   └── README.md                   # 三个脚本的用法、依赖、边界
├── tests/
│   ├── README.md                   # 5 张合成图 + 图包夹具 + 预期结果（clone 即可自测）⭐
│   ├── sample_prompt_pack.yaml     # 批量渲染夹具（layout / photo_required 跳过测试）
│   ├── test_render.py              # mock API 一键自测（generations / edits / 跳过 / manifest）⭐
│   └── *.png                       # ml_pass · amazon_fail · shopee_fix/fixed · ml_chaotic
├── prompts/ templates/ examples/   # 原有四件套
```

**用法**：

```bash
# 批量渲染（无 API 时自动降级为只输出 Prompt；layout / photo_required 自动跳过）
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml \
  --reference product.png --platform shopee

# 先看计划 / 只跑指定图位
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml --list
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml \
  --reference product.png --platform shopee --only 1,2

# 出图后必跑的合规校验（像素级，非"看一眼"）
python scripts/check_main_image.py 出图.png --platform mercadolivre
python scripts/check_main_image.py 出图.png --platform shopee --fix 修复后.png
```

校验不过的图**不许交付**；`--fix` 能自动修的（白底不纯、留白过多、非正方形）会直接修好并复检。
批量渲染的每个图位状态、输出路径与校验结果都记录在 `render_manifest.json`。

---

## 五、9 图框架

| # | 图位 | 职责 | 信息来源 | 平台差异 |
|---|---|---|---|---|
| 1 | **主图** | 一眼说清"这是什么" | `product_name` + 平台规则卡 | ⚠️ ML 首图禁促销文字；Shopee 推荐叠字 |
| 2 | **核心卖点图** | 一句话主卖点视觉化 | `core_selling_point` | 通用 |
| 3 | **参数规格图** | 把 `spec_table` 可视化 | `spec_table` | 通用 |
| 4 | **使用场景图 A** | 主场景代入 | `usage_scope[0]` | 通用 |
| 5 | **使用场景图 B** | 次场景 / 人群代入 | `usage_scope[1]` | 通用 |
| 6 | **细节特写图** | 材质、做工、关键部件 | `secondary_points` | 通用 |
| 7 | **尺寸/对比图** | 消除"尺寸不符预期" | `spec_table` 尺寸项 | ML 建议加 |
| 8 | **包装清单图** | 明确"含什么 / 不含什么" | `package_content` | **差评对冲关键图** |
| 9 | **售后/保修图** | 降低购买顾虑 | `warranty` | **巴西站强建议** |

> 第 8、9 张图是最容易被忽略、但收益最直接的两张：**第 8 张对冲"以为含 X"的误解型差评，第 9 张是巴西消费法语境下的信任要素。**

---

## 六、Prompt 文件

| 文件 | 作用 |
|---|---|
| [`prompts/00_system.md`](./prompts/00_system.md) | 系统 Prompt：角色 + 平台图片规范 + IMAGE COMPLIANCE GUARD |
| [`prompts/01_image_plan_9grid.md`](./prompts/01_image_plan_9grid.md) | 任务 Prompt：9 图规划 + 图内文案 |
| [`prompts/02_image_prompt_generator.md`](./prompts/02_image_prompt_generator.md) | 任务 Prompt：逐图出图 Prompt + 负面词 |

## 七、模板与案例

| 文件 | 说明 |
|---|---|
| [`templates/input_image_brief.md`](./templates/input_image_brief.md) | 标准输入 |
| [`templates/output_image_prompt_pack.yaml`](./templates/output_image_prompt_pack.yaml) | 标准输出 |
| [`examples/pet_carrier.md`](./examples/pet_carrier.md) | 真实案例：宠物外出包（9 图完整规划） |

---

## 八、已知限制

| 限制 | 说明 |
|---|---|
| **默认不强制渲染** | 仍可只产出 Prompt 与设计规格；v0.5 的渲染器是可选执行层，不配 API 也能完整交付 Prompt 包 |
| **批量适配器读 YAML 需 PyYAML** | 也可把图包另存为 `.json`；渲染器本身纯标准库 |
| **图像模型不保证 Logo / 文字 100% 准确** | 图内文字仍后期叠字；Logo / 屏幕数字需对照 Angle Sheet 人工复核 |
| **9 图框架为推导版** | SOP 原始清单未提取到，已确认采用本仓库推导版本（见第二节）；未来若拿到原文可校准 |
| **无法自动判断所有生成图是否合规** | 像素校验只覆盖尺寸/占比/背景/文件大小；认证、评价、场景越界仍需人工执行 C 段清单 |
| **不生成认证标识** | 无认证的商品绝不出认证图，这是硬拦截 |
| **真人出镜有约束** | AI 生成人物不得与真实可识别个人相似；不得用真实买家照片再生成 |
| **平台规范会变** | 主图规则变更频繁，**发布前必须复核** |

---

**返回**：[Agents 索引](../README.md) · **上游**：[03 Listing Creative](../03_Listing_Creative_Agent/) · **文档**：[平台字段规范](../../docs/02_Platform_Output_Spec.md) · [合规红线](../../docs/03_Compliance_Guard.md)
