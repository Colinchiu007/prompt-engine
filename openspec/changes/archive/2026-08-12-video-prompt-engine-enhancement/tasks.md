# Tasks — video-prompt-engine-enhancement

## 1. 知识库扩充
- [x] 1.1 提取 awesome-video-prompts 全量案例（JSON+纯文本）→ 种子扩充
- [x] 1.2 提取 awesome-seedance / awesome-seedance-2 / drama-skills 提示词 → 种子补充
- [x] 1.3 平台分层（veo/kling/seedance/hailuo/doubao/generic）
- [x] 1.4 关键词命中触发检索兜底（rag_retriever）
- [x] 1.5 种子质量过滤 + source 标注

## 2. 结构化重试
- [x] 2.1 optimize JSON 解析失败重试（≤2 次，带提示）
- [x] 2.2 重试耗尽回退原文 + 标记

## 3. 多平台策略
- [x] 3.1 veo 策略（长镜头/真实感）
- [x] 3.2 kling 策略（运动物理/细节）
- [x] 3.3 hailuo 策略（节奏/剪辑）
- [x] 3.4 doubao 策略（中文优先）
- [x] 3.5 注册 + 测试

## 4. SQLite 缓存
- [x] 4.1 cache_manager（内存+SQLite）
- [x] 4.2 接入 optimizer

## 5. 输入分类 + 多候选择优
- [x] 5.1 题材/镜头意图关键词检测
- [x] 5.2 evaluator 评分择优（num_candidates>1）

## 6. evaluator + feedback
- [x] 6.1 evaluator（保真/六要素/镜头字段/长度）
- [x] 6.2 feedback 沉淀种子库

## 7. 中文输出
- [x] 7.1 output_language 参数（模型/策略/API）
- [x] 7.2 zh 输出测试

## 8. videogen 集成
- [x] 8.1 Multi-Publish contract 支持 8020 配置
- [x] 8.2 videogen 优先独立引擎 + 回退 8013
- [x] 8.3 集成测试

## 9. 测试与文档
- [x] 9.1 视频引擎单测扩充（重试/缓存/分类/评估/反馈/中文/平台）
- [x] 9.2 文档更新（PRD/ARCH/CHANGELOG）
- [x] 9.3 推送 PR + CI + 合并
- [x] 9.4 三同步归档 + 记忆
