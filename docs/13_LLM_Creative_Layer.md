# 13 · LLM 创意层

> 适用版本：v0.14
> 默认关闭；显式 `--creative` 才启用。测试用 FakeLLM，不访问网络。

---

## 一、它解决什么

01/02/06 本来就是确定性计算；03/04/05/07 之前只有"校验 + 骨架"。
LLM 创意层补上生成能力：

| Agent | LLM 生成 | 确定性校验 |
|---|---|---|
| 03 Listing | PT-BR 标题 / 详情页 / 次级卖点 | `title_lint` + `spec_consistency` |
| 04 商品图 | 9 图规划 + 逐图英文 Prompt | 结构检查 + 像素校验（base） |
| 05 视频 | PT-BR 台词 / 分镜 / 字幕 | `video_timing` 时长/字幕 |
| 07 评论 | PT-BR 修补建议 + 卖点排行 | 归因聚合（base） |

设计原则：

1. **LLM 失败 → 回退确定性结果**，任务不中断，消息里标注；
2. **LLM 产出仍要过工具校验**，不过就失败；
3. **不把 LLM 输出当证据**（证据仍来自工具/数据）；
4. **默认关闭**，避免误烧 token。

---

## 二、配置

```bash
# 任选一组
export RUNTIME_LLM_BASE_URL=https://api.openai.com/v1
export RUNTIME_LLM_MODEL=gpt-4.1-mini
export RUNTIME_LLM_API_KEY=...

# 或复用 OpenAI / DeepSeek
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
# export DEEPSEEK_API_KEY=...
# export DEEPSEEK_MODEL=...
```

`python -m runtime doctor` 会显示 `optional:llm` 是否已配置（不打印 Key）。

---

## 三、使用

```bash
# 单 Agent
python -m runtime run "帮我写一个商品标题" --creative

# 全链路（03/04/05/07 用 LLM，01/02/06 仍确定性）
python -m runtime run "走一遍完整链路" --creative --engine supervisor --decision approve

# API 服务
python -m runtime serve --creative --port 8000
```

未配置 LLM 时：

```json
{"status":"config_error","error":"启用 --creative 需要 LLM 配置（...）"}
```

---

## 四、输出约定

| Agent | 期望 JSON 字段 |
|---|---|
| 03 | `title` / `description` / `secondary_points` |
| 04 | `image_plan` / `prompts` |
| 05 | `script` / `storyboard` / `subtitles` |
| 07 | `patch_suggestions` / `selling_points_ranked` |

LLM 输出会合并进 artifact，并标记 `creative_source: "llm"`。

03 的标题会重新跑：

```bash
title_lint.py <title> --platform <platform> --json
spec_consistency.py --spec <spec_table> --title <title> --json
```

不过校验 → 任务 `failed`，不会把不合规标题交付。

---

## 五、LLM 客户端

`runtime/llm.py`：

- `OpenAICompatibleClient`：`/chat/completions` + `response_format=json_object`；
- `FakeLLM`：测试替身；
- `load_llm_from_env()`：缺 model/key 返回 `None`（不抛异常）。

安全：

- Key 只从环境变量读取，不打印；
- 请求超时 90s；
- HTTP/网络/JSON 错误统一 `LLMError`；
- 不在测试中真实调用。

---

## 六、边界

- 不是自动 Agent 循环；只是"确定性 Runner + 一次创意生成"；
- 04 的 Prompt 不做像素校验（需要实际出图后再跑 `check_main_image`）；
- 05 的台词会过 `video_timing`，但分镜/画面质量仍需人工；
- 07 的修补建议需人工确认后走审批信封。

---

**相关**：[运行时 README](../runtime/README.md) · [HTTP API](11_HTTP_API.md) · [Apply/评测](12_Apply_and_Eval.md) · [证据规范](08_Evidence_and_Citation_Spec.md)
