---
name: sop-ecom-image
description: >-
  跨境电商商品图生成 Skill，Shopee 巴西站与 Mercado Livre 专精。9 图框架规划、产品身份锁定、
  Campaign Style Lock 多图一致性、可选 Product Angle Sheet、平台规则内置
  （ML 新规：白底/纯色/实景按类目）、OpenAI 兼容 API 批量出图、像素级合规校验与自动修复。
  当用户要做商品主图、场景图、详情图、白底图、9 张图、图合规检查、换背景、SKU 换色时使用。
  中文「做图 / 主图 / 场景图 / 详情图 / 合规检查 / 批量出图」同样触发。
  NOT for 视频剪辑、纯格式转换、批量压缩。
allowed-tools:
  - Bash(python *)
  - Read
  - Write
metadata:
  version: 0.5.0
  category: e-commerce/image-generation
  license: MIT
---

# 04 · Product Image Skill（Shopee BR / Mercado Livre 专精）

把一张产品照 + 一份参数表，变成**一整套符合平台规范、可直接上架**的商品图。

**与 GitHub 上其它电商生图 Skill 的区别**：它们全部面向 Amazon / 淘宝 / 小红书 / TikTok Shop。
本 Skill 专精两个平台 —— **Mercado Livre（规则最特殊：按类目区分背景、首图禁无关文字）**
和 **Shopee 巴西（首图推荐叠字、饱和度高的葡语大字报风格）**，并保留 9 图规划框架。

---

## 三不红线（先读，不可协商）

1. **不剥离 C2PA / SynthID 等隐形水印标记**
2. **不教唆规避平台 AI 标注**（例如「用 PS 改一下就不用披露 AI 图」）
3. **不造假实拍** —— AI 生成图不得冒充「100% 实拍」

复刻可识别真人的请求 → 拒绝（涉及 right-of-publicity，与水印无关）。

---

## 产品身份锁定（Product Identity Lock）—— 每次出图前必做

生图最大的事故不是"图不好看"，是**产品被画得不像了**（Logo 拼错、颜色跑偏、形状改变）。
所以在任何出图之前，先把产品身份固定下来，并**原样带进每一条 prompt**。

| 字段 | 说明 | 示例 |
|---|---|---|
| `product_type` | 品类 + 形态 | 充电宝（圆角长方体） |
| `shape` | 形状描述，越具体越好 | 圆角矩形机身，四角半径约 8mm |
| `color` | **hex 色值**，不用形容词 | 机身 `#1C1C1E`，按键 `#3A3A3C` |
| `logo_text` | 产品上的文字，逐字符给出 | `HX-20000`（屏幕显示） |
| `materials` | 材质与表面处理 | 磨砂塑料 + 阳极氧化铝片 |
| `ports_layout` | 接口/部件位置 | 顶部：USB-C×1 + USB-A×2 |
| `must_not_change` | 绝不能变的点 | 屏幕数字、Logo 位置、按键数量 |

> **规则**：`must_not_change` 里的每一项，在后续**每一条** prompt 的否定清单里重复出现。
> 这是防止「越画越不像」的唯一有效手段。

---

## 最小输入

```text
1. 产品图 1 张（手机随手拍也行，白底/实景都可）
2. 参数表 spec_table（尺寸/容量/材质，来自 03 Listing Agent 的输出）
3. 目标平台：shopee | mercadolivre | amazon
4. 品类（决定 ML 的背景规则，见平台路由表）
```

---

## 工作流总览

```text
① 身份锁定 → ② 平台规则路由 → ③ 图序列规划 → ④ 建 Campaign Style Lock
→ ⑤（可选）生成 Product Angle Sheet → ⑥ 逐图组装 Prompt
→ ⑦ 出图（三通道任选；B 通道可用批量适配器） → ⑧ 像素级合规校验（--fix 自动修复） → ⑨ 交付
```

> **v0.5 的新增点**：④ 风格锁与 ⑤ 角度基准图解决"9 张图像拼凑"和"越画越不像"；
> ⑦ 的通道 B 现在有**实际可执行的脚本**，不再只是"请你自行调 API"。
> 但图内文字仍不由模型渲染——这条底线不变。

---

## ① 平台规则路由（读对应规则卡，不要凭记忆）

| platform | 规则卡 | 关键差异 |
|---|---|---|
| `shopee` | [references/platform-shopee.md](references/platform-shopee.md) | 首图**推荐叠字**（PT-BR 大字报）、饱和度高、9 图上限、单图 ≤2MB |
| `mercadolivre` | [references/platform-mercadolivre.md](references/platform-mercadolivre.md) | **背景不再强制纯白**（白/纯色/实景按类目），但首图禁促销文字；占比要求最高（~95%） |
| `amazon` | [references/platform-amazon.md](references/platform-amazon.md) | 最严：纯白 RGB(255,255,255) 必须 + 主体 ≥85% + 禁一切文字 |

**注意**：三个平台对「首图能不能有字」的答案**互相矛盾**，一套图不能直接复用 ——
这正是本 Skill 按平台出规则卡的原因。

---

## ② 图序列规划

规划走的是本仓库的 **9 图框架**（Shopee 上限 9 张，正好逐格规划）。

每个图位（目的 / 构图 / prompt 骨架 / 平台差异）见
[references/scenarios-9grid.md](references/scenarios-9grid.md)。

ML 没有张数上限（建议 6–8 张），前 5 张按 ML 首图规则执行，其余可用场景图。

---

## ③ 多图一致性：Campaign Style Lock（v0.5 新增）

**2 张以上图必须建风格锁。** 完整字段、三平台默认锁、写法规则见
[references/style-lock.md](references/style-lock.md)。

三条硬规则：

1. **每条 Prompt 第一段原样复用** `style_lock_prompt`，不改写、不缩略；
2. **只允许改**画面目的、场景、局部构图；色板、光向、背景体系、字体、图标、产品占比不动；
3. **图内文字仍后期叠字**，不把 `overlay_copy` 写进出图 Prompt。

输出模板字段：`campaign_style_lock`（含 `style_lock_prompt`）。

---

## ④ 产品角度基准图（可选，v0.5 新增）

**触发条件**：只有 1 张产品照、却要出 3 张以上正式图；或产品有 Logo / 屏幕文字 / 特殊接口，
怕"越画越不像"。

```text
生成多角度 Angle Sheet → 一致性 Gate（形状/颜色/Logo/接口/包装）
→ 通过后，正式图全部以它为参考图
```

完整 Prompt 模板、命令与 Gate 清单见
[references/product-angle-sheet.md](references/product-angle-sheet.md)。

> Angle Sheet 是**临时工作图**，不是上架图；正式图 Prompt 只允许写一句
> `Use the product angle sheet only as product identity reference.`

---

## ⑤ Prompt 组装：五槽位 + 七条铁律

每条出图 prompt 按「风格锁 + 五个槽位」组装：

```text
[Campaign Style Lock 原文]
+ [产品身份 / Angle Sheet 引用句]
+ [场景与构图] + [光影] + [平台技术参数] + [否定清单]
```

七条铁律（来自一线实战，逐条硬性执行）：

1. **颜色用 hex 码**，不用形容词 —— `#1C1C1E`，不写"深灰色"
2. **产品占比必须数字化** —— `product occupies 82% of frame height`
3. **留白必须显式声明** —— `even 9% margin on all sides`
4. **否定清单不能省** —— 且必须包含 `must_not_change` 全部条目
5. **平台预留空间** —— Shopee 首图右上留 12% 给价格角标；ML 首图四边留白
6. **图内文字三层架构** —— 主标语 ≤4 词 / 卖点 ≤7 词 / 角标仅数字（**仅 Shopee**；ML 首图禁）
7. **批量出图优于反复调参** —— 一次出 5 版选 1，不要逐张精修

---

## ⑥ 出图通道（三选一，按环境自动降级）

| 通道 | 条件 | 用法 |
|---|---|---|
| **A. Agent 内置生图** | 你所在的 AI 环境自带画图工具 | 直接把组装好的 prompt 交给生图工具 |
| **B. OpenAI 兼容 API**（v0.5 带脚本） | `IMAGE_API_BASE` + `IMAGE_MODEL` + `IMAGE_API_KEY`（兼容 `OPENAI_*` / `IMG_*` 别名） | 单张：`render_openai.py`；批量：`render_prompt_pack.py` |
| **C. 仅输出 Prompt 包** | 没有 API 或不想配 | 渲染器 `--mode auto` 自动降级；批量适配器写 `prompts/` + `render_manifest.json` |

**配置**（`.env` 或环境变量，三种命名脚本都认）：

```dotenv
IMAGE_API_BASE=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-1
IMAGE_API_KEY=your-api-key
```

### 单张渲染

```bash
# 配置齐全自动出图；没有配置则只输出 Prompt
python scripts/render_openai.py \
  --prompt-file prompts/slot-01.txt \
  --image product.png \
  --job-dir generated-images/pack-001 \
  --asset-type main \
  --size 1024x1024
```

### 批量渲染（推荐）

```bash
# 先看哪些图位会被渲染（layout / photo_required 会自动跳过）
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml --list

# 只看执行计划，不出图
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml --dry-run --reference product.png

# 正式跑：没有 API 时自动降级为只输出 Prompt
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml \
  --reference product.png --platform shopee
```

**批量适配器的四条硬规则**：

1. `type = layout`（参数图/尺寸图/售后图）与 `type = photo_required`（包装清单图）
   **一律跳过**，不交给图像模型；
2. `overlay_copy` **不送进图像模型**——图内文字仍由设计工具后期叠字；
3. 图位标记 `reference_image_needed: true` 但没给参考图 → **阻塞**（`[INPUT_MISSING]`）；
   显式加 `--allow-no-reference` 才继续，且会在 manifest 里留下警告；
4. 出图后默认只校验 **slot 1 主图**；`--check-all` 才检查全部 1:1 图
   （场景图用主图标准会被误判）。

**模型路由**（如可用）：
- 场景图 / 生活图 / 多版本尝试 → 快模型（Flare 类）
- 需要保留 Logo / 屏幕文字 / 局部编辑 → 强模型（Sunburst 类）

---

## ⑦ 出图后必须过像素校验（不是"看一眼"）

```bash
python scripts/check_main_image.py 出图.png --platform mercadolivre
python scripts/check_main_image.py 出图.png --platform shopee --fix 修复后.png
```

脚本会**逐像素**检查：尺寸、正方形、主体占比、背景纯净度/均匀度、文件大小，
失败项会直接列出；`--fix` 能自动修的（白底不纯、留白过多、非正方形）会直接修。

批量适配器会在 `render_manifest.json` 里记录每个图位的渲染状态、输出路径与校验结果；
校验不过的图**不许交付**。

**校验标准来自平台规则卡，不是拍脑袋。**
**自测**：[`tests/`](tests/README.md) 内置 5 张合成夹具 + 1 份图包夹具 + 1 个 mock API 自测脚本
（`tests/test_render.py`，不需要真实 Key），clone 后跑一遍即可验证脚本是否正常。

---

## 已知限制

| 限制 | 说明 |
|---|---|
| **默认不强制渲染** | 本 Skill 仍可只输出「规划 + Prompt + 校验」；通道 B/C 是可选执行层，不配 API 也能完整交付 Prompt 包 |
| **批量适配器读 YAML 需 PyYAML** | 也可把图包另存为 `.json`；渲染脚本本身纯标准库 |
| **图内文字检测不自动** | 有没有违规叠字需要人工确认（OCR 依赖重，暂未内置） |
| **图像模型不保证文字/Logo 100% 准确** | 图内文字仍后期叠字；Logo/屏幕数字需人工比对 Angle Sheet |
| **ML 类目背景规则会变** | 白底/实景按类目划分，出大目录前先去 ML 卖家中心核对当前类目 |
| **平台规则为编写时公开值** | 发布前必须到卖家中心复核 |
| **不替代修图** | 复杂的产品瑕疵修图仍需人工 |

---

**返回**：[04 模块 README](README.md) · **规则卡**：[Shopee](references/platform-shopee.md) · [Mercado Livre](references/platform-mercadolivre.md) · [Amazon](references/platform-amazon.md) · **多图一致性**：[Campaign Style Lock](references/style-lock.md) · **产品身份**：[Product Angle Sheet](references/product-angle-sheet.md) · **9 图场景库**：[scenarios-9grid.md](references/scenarios-9grid.md)
