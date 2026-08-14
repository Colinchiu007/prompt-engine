"""prompt_engine_core — 图片/视频提示词引擎共享内核（领域无关机械件）。

分层原则：
- core 只放行为一致、领域无关的机械件（原子写/文本工具/注册器/LLM 传输/知识库骨架/TF-IDF）
- 领域层（models/strategies/classifier/evaluator/cache key/种子资产）保留在各自引擎包
- 两引擎允许依赖 core；core 禁止反向依赖任何引擎包
"""

__version__ = "0.1.0"
