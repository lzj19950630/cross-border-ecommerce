# 04 · check_main_image.py 测试夹具

5 张合成图，**每张都埋了已知的合规项与违规项**。
clone 下来跑一遍，输出与下表一致 = 校验脚本工作正常。

```bash
cd Agents/04_Product_Image_Agent/scripts

python check_main_image.py ../tests/ml_pass.png       --platform mercadolivre   # 预期 ✅
python check_main_image.py ../tests/amazon_fail.png   --platform amazon         # 预期 ❌ coverage
python check_main_image.py ../tests/shopee_fix.png    --platform shopee  --fix ../tests/shopee_fixed.png
python check_main_image.py ../tests/ml_chaotic.png    --platform mercadolivre   # 预期 ❌ square
python check_main_image.py ../tests/shopee_fixed.png  --platform shopee         # 预期 ✅
```

---

## 夹具清单与预期结果（实测值）

| 夹具 | 构造 | 平台 | 预期判定 |
|---|---|---|---|
| `ml_pass.png` | 1200×1200 米色干净底 `#F5F0E8`，主体占 88% | mercadolivre | **✅ 通过** |
| `amazon_fail.png` | 2000×2000 纯白底，主体只占 **60%** | amazon | **❌ coverage** 60% < 85% |
| `shopee_fix.png` | 900×900 米白底 `#FAFAF8`（非纯白），主体占 **56%** | shopee | **❌ white_bg 0%** + **❌ coverage** |
| `shopee_fixed.png` | 上者经 `--fix` 输出 | shopee | **✅ 通过**（1024px / 白底 100% / 占比 80%） |
| `ml_chaotic.png` | **1100×1000 非正方形** + 边缘随机噪声背景 | mercadolivre | **❌ square** + **⚠️ bg_uniformity** + **⚠️ coverage 100%*** |

### 实测记录（2026-10-16）

| 夹具 | 关键输出 |
|---|---|
| ml_pass | ✅ size 1200px · ✅ square · ⚠️ coverage 100%（>97% 上限，正确告警）· ✅ bg_uniformity 100% |
| amazon_fail | ❌ coverage 60% < 85% · ✅ white_bg 100% · ✅ square |
| shopee_fix | ❌ white_bg 0.0% < 90% · ❌ coverage 56% < 60% · ⚠️ size 900 < 1024 |
| shopee_fixed | ✅ 1024px · ✅ white_bg 100% · ✅ coverage 80%（`--fix` 精准达标） |
| ml_chaotic | ❌ square 1100×1000 · ⚠️ bg_uniformity 84%（背景略花）· ⚠️ size 1000 < 1200 · ⚠️ coverage 100%* |

> **\* 关于 ml_chaotic 的 coverage=100%**：占比用「非背景像素包围盒」测量，
> 噪声像素本身就是非背景 → 包围盒被撑满全图。**杂乱背景下 bbox 占比法必然失效**
> —— 这不是 bug，恰恰是脚本同时输出 `bg_uniformity` 警告的原因：
> 背景花掉的图，占比数字不可信，先清背景再谈占比。

---

## 这组夹具覆盖了什么

| 能力 | 被哪张验证 |
|---|---|
| ML「背景干净即可，不要求纯白」（2026 新规） | `ml_pass`（米色底也判过） |
| Amazon 白底纯度 + 85% 占比红线 | `amazon_fail` |
| 近白像素拉纯白 + 占比重排的 `--fix` | `shopee_fix` → `shopee_fixed` |
| 非正方形检测 | `ml_chaotic` |
| 背景杂乱提示 + bbox 占比法在杂乱背景下的失效边界 | `ml_chaotic` |
| 占比超上限告警（>97%） | `ml_pass`（100% 贴边） |

**不覆盖**：图内文字占比（需 OCR，列为人工确认项）、真实产品照片（夹具为合成图，只测几何与颜色）。

---

## 渲染脚本测试（v0.5）

夹具：[`sample_prompt_pack.yaml`](./sample_prompt_pack.yaml)（5 个图位：1/2/4 可渲染，3 layout，8 photo_required）。

```bash
cd Agents/04_Product_Image_Agent/scripts

# 1) 图位筛选：应显示 1/2/4 可渲染，3 layout，8 photo_required
python render_prompt_pack.py ../tests/sample_prompt_pack.yaml --list

# 2) 执行计划：3 个 planned，不调用 API
python render_prompt_pack.py ../tests/sample_prompt_pack.yaml \
  --dry-run --allow-no-reference --job-dir "$TEMP/04-dry" --json

# 3) 批量 Prompt 模式：3 个 prompt_only，Prompt 文件含否定清单
python render_prompt_pack.py ../tests/sample_prompt_pack.yaml \
  --render-mode prompt --allow-no-reference --job-dir "$TEMP/04-pack" --json

# 4) 参考图缺失且未加 --allow-no-reference：应报 [INPUT_MISSING] 并 exit 1
python render_prompt_pack.py ../tests/sample_prompt_pack.yaml --render-mode prompt \
  --job-dir "$TEMP/04-block" ; echo "exit=$?"
```

预期：

| 测试 | 预期 |
|---|---|
| `--list` | slot 1/2/4 yes；slot 3 `layout`；slot 8 `photo_required` |
| `--dry-run` | `status=planned`，`skipped` 含 3 与 8 |
| `--render-mode prompt` | 3 个 `prompt_only`；`prompts/*.txt` 末尾有 `Avoid / negative constraints` |
| 无参考图 | exit 1，报 `[INPUT_MISSING]` 列出 slot 1, 2, 4 |

> 这些测试**不需要 API Key**：`--render-mode prompt` 只落 Prompt，不调用图片接口。

### 一键自测（含 mock 图片接口）

```bash
python tests/test_render.py
```

脚本会启动本地 mock API，验证 `generations`、`edits`、图位跳过、manifest 落盘、
`overlay_copy` 不进入出图 Prompt。**不需要真实 Key，也不会访问外网。**

---

**脚本**：[`scripts/check_main_image.py`](../scripts/check_main_image.py) · [`render_openai.py`](../scripts/render_openai.py) · [`render_prompt_pack.py`](../scripts/render_prompt_pack.py) · **规则卡**：[Shopee](../references/platform-shopee.md) · [Mercado Livre](../references/platform-mercadolivre.md) · [Amazon](../references/platform-amazon.md) · [Style Lock](../references/style-lock.md) · [Angle Sheet](../references/product-angle-sheet.md)
