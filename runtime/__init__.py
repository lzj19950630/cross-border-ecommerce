"""Agent runtime platform core.

这个包不是一套独立应用，而是从 Multi-Agent-E-commerce-System 的架构中抽出的
「平台核心」：Agent 注册表、意图路由、任务切片、审批信封、证据链、工具桥接。

设计目标：
- 零第三方依赖（纯标准库），可在现有工具箱里直接测试；
- 未来可嵌入 fork 的 LangGraph 底座，替换其硬编码的 3 个业务域；
- 工具箱保持独立：Prompt/模板/脚本仍是真源，runtime 只做编排与契约校验。
"""

__version__ = "0.30.1"
