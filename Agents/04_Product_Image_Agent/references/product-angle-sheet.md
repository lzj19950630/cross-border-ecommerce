# Product Angle Sheet · 产品角度基准图

> **解决什么问题**：只有一张产品照片时，直接生成 9 张图，产品会"越画越不像"——
> Logo 拼错、接口少一个、颜色跑偏。角度基准图先用一张临时图**锁定产品身份**，
> 再让所有正式图以它为参考图。

---

## 一、什么时候用

| 场景 | 是否使用 |
|---|---|
| 只有 1 张产品照，要生成 3 张以上正式图 | ✅ **建议使用** |
| 产品有正面 Logo、屏幕文字、特殊接口/按键 | ✅ **强烈建议** |
| 产品材质/颜色很难用文字描述（渐变、纹理、金属拉丝） | ✅ **建议** |
| 已有 3 个以上角度的清晰实拍图 | 可跳过，直接把实拍图作为参考图 |
| 纯场景图 / 不需要严格保真的概念图 | 可跳过 |

> **角度基准图是临时工作图，不是上架图**。不要上传到平台，也不要用它做首图。

---

## 二、流程

```text
[Step 1] 读产品身份锁定字段（product_type / shape / color hex / logo_text /
         materials / ports_layout / must_not_change）
[Step 2] 写 Angle Sheet Prompt（模板见下）
[Step 3] 调用渲染器生成一张多角度基准图
[Step 4] 一致性 Gate：形状/颜色/Logo/包装是否明显跑偏？
         → 跑偏：改 Prompt 重生，直到稳定
         → 稳定：进入 Step 5
[Step 5] 正式图全部以该基准图为 --reference，并在每条 Prompt 里加固定引用句
[Step 6] 正式图出图后跑 check_main_image.py 校验主图
```

---

## 三、Angle Sheet Prompt 模板（英文）

```text
Product identity reference sheet for ecommerce image generation.
Show the SAME product in multiple views on one clean light neutral studio background:
1) front view, 2) left 45-degree view, 3) right 45-degree view,
4) side profile showing thickness, 5) back view,
6) close-up of ports / buttons / screen / key structure,
7) product with its retail packaging if available.
Product details: {product_type}; shape: {shape}; color: {color_hex};
materials: {materials}; logo/text: "{logo_text}" rendered exactly;
ports/layout: {ports_layout}.
Keep all views visually consistent in scale, color and material.
No promotional badges, no price, no rating, no "best seller" labels,
no marketing headline, no watermark, no border, no extra products.
Clean studio lighting, accurate color, high detail.
```

### 与正式图的区别

| 项 | Angle Sheet | 正式图 |
|---|---|---|
| 目的 | 锁产品身份 | 转化 / 卖点表达 |
| 文字 | ❌ 无营销文字 | 仅允许平台规则内的短文案（后期叠字） |
| 背景 | 干净浅色工作室 | 按平台/类目 |
| 构图 | 多角度平铺 | 单镜头、单信息 |
| 是否上架 | ❌ 否 | ✅ 是 |

---

## 四、正式图引用规则

每条正式图 Prompt 必须包含固定一句：

```text
Use the product angle sheet only as product identity reference.
```

**只允许这一句**。不要展开描述角度图的内容，否则模型会把"多角度平铺"画进正式图。

正式图 Prompt 的结构：

```text
[Campaign Style Lock]
Use the product angle sheet only as product identity reference.
[本图目的与构图]
[光影 / 背景 / 平台参数]
[否定清单：含 must_not_change]
```

---

## 五、命令

```bash
# 1) 生成角度基准图（配置了 API 时直接出图；没有则只出 Prompt）
python scripts/render_openai.py \
  --asset-type angle-sheet \
  --prompt-file angle-sheet-prompt.txt \
  --image product.png \
  --job-dir generated-images/<product>-pack-<timestamp> \
  --size 1024x1024

# 2) 正式图批量渲染：把基准图作为 --reference
python scripts/render_prompt_pack.py output_image_prompt_pack.yaml \
  --reference generated-images/<product>-pack-<timestamp>/angle-sheet/<基准图>.png \
  --platform shopee

# 3) 主图校验
python scripts/check_main_image.py generated-images/<product>-pack-<timestamp>/main/<主图>.png \
  --platform shopee
```

> 若生图模型不支持多角度拼图，可退化为"正面 + 45° + 背面"三张基准图，
> 但正式图只能引用其中与当前镜头最接近的一张，避免身份漂移。

---

## 六、一致性 Gate（不过不进入正式图）

- [ ] 产品形状与实拍一致（圆角/厚度/比例）
- [ ] 颜色与 hex 值一致（不是"看起来差不多"）
- [ ] Logo / 屏幕文字逐字符正确
- [ ] 接口、按键、指示灯数量与位置正确
- [ ] 材质表现正确（磨砂/亮面/金属/织物）
- [ ] 包装盒（如有）与实物一致
- [ ] 没有促销角标、价格、评分、平台属性词
- [ ] 没有多余配件或"赠品"暗示

任何一项不过 → **先重生角度图，不要带病生成正式图**。

---

## 七、合规提醒

- 参考图必须是**自己的产品实拍**；不要用竞品图或未授权图片。
- 角度图不得伪造认证标识、销量、评价、平台官方元素。
- 角度图不得出现可识别真人。
- 正式图仍执行 [图片合规扫描](../templates/output_image_prompt_pack.yaml) 的 I1–I8 项。

---

**返回**：[04 SKILL](../SKILL.md) · **相关**：[Campaign Style Lock](style-lock.md) · [9 图场景库](scenarios-9grid.md) · [Shopee 规则卡](platform-shopee.md)
