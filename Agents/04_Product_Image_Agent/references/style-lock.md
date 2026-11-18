# Campaign Style Lock · 多图一致性规则卡

> **一句话**：9 张图不是 9 次独立创作，而是**同一套视觉系统里的 9 个镜头**。
> 风格锁就是这套系统的"宪法"——每条 Prompt 第一段原样复用它，只允许改画面目的与局部构图。

---

## 一、什么时候必须用

| 场景 | 是否必须 |
|---|---|
| 生成 2 张以上商品图（9 图框架、详情页图包、广告组图） | ✅ **必须** |
| 只生成 1 张主图 | 可选（但建议保留，方便后续 iterate 复用） |
| `mode = iterate` 换主图 | ✅ **必须复用原锁**，否则新旧图像两套视觉 |
| 跨平台复用（Shopee → ML） | ❌ **不能复用同一把锁**——平台背景/文字规则不同 |

---

## 二、风格锁字段（10 项，缺一不可）

| # | 字段 | 说明 | 示例 |
|---|---|---|---|
| 1 | `visual_direction` | 整体视觉方向 | `clean premium tech ecommerce` |
| 2 | `palette` | 2–3 主色 + 1 点缀色，**用 hex** | `["#FFFFFF", "#1C1C1E", "#007AFF"]` |
| 3 | `temperature` | 冷暖调 | `neutral-cool` |
| 4 | `lighting` | 主光方向 / 软硬 / 阴影 | `soft studio key light from upper left` |
| 5 | `background_system` | 统一的背景体系 | `clean white studio` / 类目允许的实景 |
| 6 | `layout_system` | 留白、标签、圆角矩形、编号 | `rounded rectangular labels, 9% margin` |
| 7 | `icon_system` | 图标线宽/颜色/复杂度 | `thin-line icons, single accent color` |
| 8 | `product_presentation` | 角度、占比、位置、材质表现 | `front view, 80% of frame, stable scale` |
| 9 | `must_not_change` | 从产品身份锁定继承的不可变项 | Logo 字符、接口数量、屏幕数字 |
| 10 | `text_policy` | 图内文字策略 | **后期叠字，不进出图 Prompt**（PT-BR 变音符号） |

> 第 9、10 项是本项目与通用风格锁的区别：
> **必须把「产品身份锁定」和「图内文字后期叠字」写进锁里**，否则多图一致性会以牺牲参数准确性为代价。

---

## 三、三平台默认锁（起点，不是终点）

### Shopee 巴西站

```text
Campaign Style Lock: warm, high-saturation Brazilian ecommerce visual system;
clean white or light solid background; product occupies 70-85% of frame;
warm key light with soft shadows; one product-matched accent color;
rounded info labels with generous whitespace; top-right 12% reserved for
platform price badge; PT-BR overlay copy is added in post-production and
must not be rendered by the image model; keep product shape, color, logo
and ports exactly as in the reference image.
```

**差异点**：允许高饱和、暖调、大字报感；但**图内文字仍不用模型渲染**。

### Mercado Livre

```text
Campaign Style Lock: clean, neutral-cool ecommerce visual system;
background must be clean and category-appropriate (white / solid / real-life);
product occupies 85-95% of frame; soft diffused studio lighting;
no promotional text, no platform badges, no watermarks, no borders on the
main image; consistent thin-line labels only on secondary images;
PT-BR overlay copy is added in post-production; keep product shape, color,
logo and ports exactly as in the reference image.
```

**差异点**：首图禁一切无关文字；背景按类目；占比要求最高。

### Amazon

```text
Campaign Style Lock: strict Amazon main-image system;
pure white RGB(255,255,255) background; product occupies 85% or more of frame;
soft even studio lighting; no text, no logo overlays, no watermarks, no props,
no borders; consistent camera angle and scale across the set; keep product
shape, color, logo and ports exactly as in the reference image.
```

**差异点**：最严白底 + 零文字。

---

## 四、写法规则

1. **用英文写锁**（图像模型对英文更稳）；图内文案用 PT-BR，但**不进锁**。
2. **每条 Prompt 第一段原样粘贴 `style_lock_prompt`**，不要改写、不要缩略。
3. **只允许改**：frame objective、主体动作、场景、局部构图、短文案占位符。
4. **不允许改**：色板、色温、光向、背景体系、字体系统、图标风格、产品占比与位置。
5. **重生单张图时复用原锁**，不要因为"这张不好看"就换风格。
6. **否定清单必须包含 `must_not_change` 全部条目**。
7. **不写竞品品牌名、不写平台官方标识、不写虚构认证**。
8. **不把 `overlay_copy` 写进 Prompt**——后期叠字。

---

## 五、输出模板中的位置

`templates/output_image_prompt_pack.yaml` 增加：

```yaml
campaign_style_lock:
  enabled: true
  visual_direction: ""
  palette: []
  temperature: ""
  lighting: ""
  background_system: ""
  layout_system: ""
  icon_system: ""
  product_presentation: ""
  text_policy: "图内文字后期叠字，不进出图 Prompt"
  style_lock_prompt: ""    # ← 英文；每条图 Prompt 第一段原样复用
```

`prompts[].prompt` 的组装顺序变成：

```text
[Campaign Style Lock 原文]
+ [产品身份锁定 / Angle Sheet 引用]
+ [本图目的与构图]
+ [光影与背景]
+ [平台技术参数]
+ [否定清单（含 must_not_change）]
```

---

## 六、自检

- [ ] 2 张以上图，是否 100% 复用了同一段 `style_lock_prompt`？
- [ ] 色板是否全部用 hex，而不是"深灰/浅蓝"？
- [ ] 光向、色温、背景是否与首图一致？
- [ ] 是否误把 PT-BR 文案写进了出图 Prompt？
- [ ] `must_not_change` 是否出现在每条否定清单里？
- [ ] 跨平台是否重新建锁，而不是直接复用 Shopee 的锁？

---

**返回**：[04 SKILL](../SKILL.md) · **相关**：[产品身份锁定](../SKILL.md#产品身份锁定product-identity-lock每次出图前必做) · [产品角度基准图](product-angle-sheet.md) · [9 图场景库](scenarios-9grid.md)
