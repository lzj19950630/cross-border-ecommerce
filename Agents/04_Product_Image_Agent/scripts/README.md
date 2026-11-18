# 04 · scripts 使用说明

> 三个脚本，三种职责，**互不越界**：
>
> | 脚本 | 负责 | 不负责 |
> |---|---|---|
> | `render_openai.py` | 调 OpenAI 兼容图片接口，把 Prompt 画成图 | 不决定画什么、不校验合规 |
> | `render_prompt_pack.py` | 读 04 的图包，批量挑图位、调渲染器、跑校验 | 不生成 Prompt 内容 |
> | `check_main_image.py` | 像素级校验主图（尺寸/占比/背景/文件大小） | 不修产品瑕疵、不测 OCR 文字 |

---

## 一、依赖

| 脚本 | 依赖 |
|---|---|
| `render_openai.py` | Python 3.10+ **标准库** |
| `render_prompt_pack.py` | 标准库；读 `.yaml` 需要 **PyYAML**（可选，也可读 `.json`） |
| `check_main_image.py` | **Pillow**（`pip install pillow`） |

```bash
python -m py_compile render_openai.py render_prompt_pack.py
python check_main_image.py --help
python render_openai.py --help
python render_prompt_pack.py --help
```

---

## 二、`check_main_image.py` · 像素级校验

```bash
python check_main_image.py 出图.png --platform mercadolivre
python check_main_image.py 出图.png --platform shopee --fix 修复后.png
python check_main_image.py 出图.png --platform amazon --json
```

- 检查项：`size_min` / `square` / `coverage` / `white_bg` / `bg_uniformity` / `file_size`
- `--fix` 能自动修：近白拉纯白、补成正方形、按目标占比重排画布
- 退出码：`0` 通过（可含 WARN/INFO/MANUAL），`1` 有 FAIL 项

夹具与预期结果见 [`../tests/README.md`](../tests/README.md)。

---

## 三、`render_openai.py` · 单张渲染

### 配置（环境变量或 `.env`）

| 配置 | 可用变量名（任一） |
|---|---|
| API 根地址 | `IMAGE_API_BASE` / `IMG_BASE_URL` / `OPENAI_BASE_URL` / `OPENAI_API_BASE` |
| 模型名 | `IMAGE_MODEL` / `IMG_MODEL` / `OPENAI_IMAGE_MODEL` / `OPENAI_MODEL` |
| API Key | `IMAGE_API_KEY` / `IMG_API_KEY` / `OPENAI_API_KEY` / `API_KEY` |

```dotenv
IMAGE_API_BASE=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-1
IMAGE_API_KEY=your-api-key
```

> `.env` 已在根目录 `.gitignore` 中；不要把 Key 提交到仓库。
> 脚本不会把 Key 打印到 stdout/stderr。

### 三种模式

| 模式 | 行为 |
|---|---|
| `auto`（默认） | 三项配置齐全 → 出图；缺任一 → 只输出 Prompt |
| `prompt` | 永远只输出 Prompt（适合没配 API 或只想拿 Prompt 包） |
| `image` | 强制出图；配置不全直接报错 |

### 常用命令

```bash
# 只出 Prompt（无 API 也能跑）
python render_openai.py --mode prompt \
  --prompt-file prompt.txt --job-dir ../generated-images/pack-001 --asset-type main

# 直接出图 + 参考图锁产品身份
python render_openai.py \
  --prompt-file prompt.txt --image product.png \
  --job-dir ../generated-images/pack-001 --asset-type main --size 1024x1024

# 否定清单：会并入 Prompt 正文（OpenAI Images API 无独立 negative 字段）
python render_openai.py --mode prompt \
  --prompt "studio packshot..." --negative-prompt "no text, no watermark"

# JSON 摘要（供批量适配器解析）
python render_openai.py --mode prompt --prompt "..." --json
```

### 输出目录

```text
<job-dir>/
├── angle-sheet/   # --asset-type angle-sheet（临时基准图，不上架）
├── main/          # --asset-type main
├── detail/        # --asset-type detail
├── extras/        # --asset-type extras
├── custom/        # --asset-type custom
└── prompts/       # Prompt 副本（--no-save-prompt 可关闭）
```

---


## 四、`render_prompt_pack.py` · 批量渲染

读 `templates/output_image_prompt_pack.yaml`（或 `.json`），自动筛选可渲染图位。

### 四条硬规则

1. `type = layout`、`type = photo_required` **一律跳过**（参数图/尺寸图/售后图/包装清单图）；
2. `overlay_copy` **不送进图像模型**——图内文字后期叠字；
3. 图位 `reference_image_needed: true` 但没 `--reference` → **阻塞**（`[INPUT_MISSING]`）；
   显式 `--allow-no-reference` 才继续，并在 manifest 留警告；
4. 出图后默认只校验 **slot 1 主图**；`--check-all` 才检查全部 1:1 图。

### 常用命令

```bash
# 看哪些图位会渲染 / 哪些被跳过
python render_prompt_pack.py ../templates/output_image_prompt_pack.yaml --list

# 只看执行计划
python render_prompt_pack.py ../templates/output_image_prompt_pack.yaml \
  --dry-run --reference product.png

# 正式跑（没 API 会自动降级为只输出 Prompt）
python render_prompt_pack.py ../templates/output_image_prompt_pack.yaml \
  --reference product.png --platform shopee

# 只跑主图和卖点图，尺寸覆盖为 1200x1200
python render_prompt_pack.py ../templates/output_image_prompt_pack.yaml \
  --reference product.png --platform shopee --only 1,2 --size 1200x1200

# 校验失败时生成修复副本（只对设置了 --fix 的图位）
python render_prompt_pack.py ../templates/output_image_prompt_pack.yaml \
  --reference product.png --platform shopee --fix
```

### 输出

```text
generated-images/<product-slug>-pack-<yyyymmdd-hhmmss>/
├── main/                  # slot 1（以及显式 asset_type=main 的图）
├── detail/                # 其余 AI 图位
├── prompts/               # 每图位最终 Prompt（已合并 negative）+ negative 单独副本
└── render_manifest.json   # 渲染状态 / 输出路径 / 校验结果 / 跳过项 / 警告
```

`render_manifest.json` 是复现依据：记录每个图位的 `status`（`rendered` / `prompt_only` /
`planned` / `error`）、`images`、`checks`、`skipped` 原因与警告。

---

## 五、自测

```bash
cd Agents/04_Product_Image_Agent/scripts

# 1) 单张 Prompt 模式（不需要 API）
python render_openai.py --mode prompt --prompt "test" \
  --negative-prompt "no watermark" --job-dir "$TEMP/04-test" --json

# 2) 批量 Prompt 模式（不需要 API）
python render_prompt_pack.py ../tests/sample_prompt_pack.yaml \
  --render-mode prompt --allow-no-reference --job-dir "$TEMP/04-pack-test" --json

# 3) 像素校验夹具
python check_main_image.py ../tests/ml_pass.png --platform mercadolivre
python check_main_image.py ../tests/amazon_fail.png --platform amazon

# 4) 一键 mock API 自测（generations / edits / 图位跳过 / manifest）
python ../tests/test_render.py
```

---

## 六、边界与合规

- **不操作平台后台**：不改价、不改预算、不代上架。
- **不生成图内文字**：文字由设计工具后期叠字，避免 PT-BR 变音符号错误。
- **不渲染 `photo_required` 图位**：包装清单图必须实拍。
- **不伪造认证/评价/销量**：Prompt 与出图都受 04 的 I1–I8 合规扫描约束。
- **参考图只能用自有产品实拍**：不要用竞品图或未授权素材。

---

**返回**：[04 SKILL](../SKILL.md) · **规则卡**：[Style Lock](../references/style-lock.md) · [Angle Sheet](../references/product-angle-sheet.md) · **测试**：[tests](../tests/README.md)
