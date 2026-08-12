# 02-source/ — 遗留参考副本

> ⚠️ **此目录仅供参考，不参与运行时/构建/测试。**

这是 prompt_engine 包的早期源码备份（初始提交时引入）。
所有运行时代码、测试和 API 均以 prompt_engine/ 目录为准。

## 与 prompt_engine/ 的差异

- 缺少新增模块：cache_manager、style_detector、llm_caller、prompt_builder、rag_retriever 等
- core/models.py 中 BatchOptimizeRequest.max_length 需与 prompt_engine/models.py 保持一致（当前均为 20）

## 维护规则

- **不要在此目录中修改业务逻辑**——修改应统一在 prompt_engine/ 中进行
- 如果此目录不再需要参考价值，可以安全删除
