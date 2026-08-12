"""独立视频提示词优化引擎（与图片 prompt_engine 完全分离）。

本包不 import `prompt_engine.*`（含 02-source 镜像）；技术机制（Optimizer 编排、
策略注册表、RAG few-shot、LLM 供应商、结构化输出、批量契约）独立实现。
"""

__version__ = "0.1.0"
