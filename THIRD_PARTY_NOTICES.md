# Third-Party Notices / 第三方来源说明

本仓库主体为 MIT 许可。以下列出编写过程中参考过的外部项目与设计思路。

---

## moondream69/Multi-Agent-E-commerce-System

- **仓库**：https://github.com/moondream69/Multi-Agent-E-commerce-System
- **参考日期**：2026-11-18
- **许可**：MIT（仓库内提供 `LICENSE`）
- **借鉴的设计思路**：
  - Manager 规划切片（≤N 片 + 依赖声明 + 审批点）；
  - LangGraph supervisor 扇出、切片边界 `interrupt`、durable resume；
  - 三层动作风险 `auto / approval / forbidden`；
  - 审批批次「效果后置 + 参数快照 + 批内同进同退」；
  - 引用小点与机械防伪引；
  - 金标场景 YAML + run/score 解耦 + 机械判据 + LLM judge；
  - 动作注册表作为单一事实来源。
- **未复制其源代码**：`runtime/` 中的契约、路由、规划、审批信封、证据校验、工具桥接均为按本工具箱
  7 Agent 场景独立实现；未引入 FastAPI / LangGraph / Postgres / Milvus / Redis / Langfuse 等依赖。
- **未采用的部分**：
  - 订单/库存/客服三个业务域（与本工具箱的 7 Agent 版图不同）；
  - 其完整运行时的数据库/消息/前端/观测栈；
  - Milvus + RAG 语料链（本工具箱当前不需要）。
- **后续**：若正式 fork 其底座，将在独立仓库/目录中保留其 MIT 版权声明与 LICENSE。

---

## coolqoo/1click-ecom-detailpage

- **仓库**：https://github.com/coolqoo/1click-ecom-detailpage
- **参考日期**：2026-11-18
- **许可状态**：仓库 README 声明 MIT License，但参考时仓库内**未提供 LICENSE 文件**
  （GitHub API 的 license 字段为空）。本仓库未复制其源代码，仅借鉴公开的设计思路；
  如后续需要复用其代码，请先向原作者确认许可。
- **借鉴的设计思路**：
  - **Campaign Style Lock**：多图生成时先锁定统一视觉系统，每条 Prompt 复用同一段风格锁；
  - **Product Angle Sheet**：先用多角度基准图锁定产品身份，再生成正式图；
  - **job-dir 资产组织**：`main/`、`detail/`、`prompts/` 等目录结构与每次任务独立目录；
  - **OpenAI 兼容图片接口直出**：`/images/generations` 与 `/images/edits` 的调用方式；
  - **批量图包的"主图 + 详情图"交付思路**。
- **未采用的部分**（与本项目规则冲突）：
  - 其默认关闭合规审查、允许模拟好评/夸张对比；
  - 其 English (US) baseline → localization 的语言路线；
  - 其把图内文字交给图像模型渲染的做法；
  - 其 5 主图 + 7–9 详情图的通用 Amazon PDP 结构。
- **本项目的实现差异**：
  - `scripts/render_openai.py` 与 `scripts/render_prompt_pack.py` 为独立实现，**未复制其代码**；
  - 合规定义、平台规则、9 图框架、PT-BR 文字策略、像素级校验均来自本仓库；
  - 批量适配器强制跳过 `layout` 与 `photo_required` 图位，且不把 `overlay_copy` 送进图像模型。

---

## 其他

本仓库引用的平台规则、费率表、SOP 来源已在对应文档中逐项标注。
若你认为某处来源标注不完整，请提交 Issue，我们会补充。
