# Design — 视频提示词引擎全面增强

## Context
现有引擎（eb6fb2d）已验证真实 LLM 链路；本 change 补齐与图片引擎的机制差距 + 视频特性。

## Decisions

### D1 知识库扩充（P0）
- 种子来源：awesome-video-prompts（README 全量案例，JSON+纯文本提示词）、awesome-seedance（商用用例）、awesome-seedance-2（提示词）、drama-skills（分镜）、seedance2-skill（语法）
- 结构：`VideoPromptEntry.platform` 分层；纯文本提示词也入库（few-shot 价值）
- 检索：向量 TF-IDF + 关键词命中兜底（命中关键词 → 匹配平台种子 top_k）
- 目标 100-300 条

### D2 结构化重试（P0）
- optimize 中 post_process_video 解析失败 → 带"只输出严格 JSON 数组/对象"提示重试 ≤2 次；耗尽回退原文 + 标记

### D3 多平台策略（P0）
- BaseVideoStrategy 派生：veo（长镜头/真实感）、kling（运动物理/细节）、hailuo（节奏/剪辑）、doubao（中文优先）；平台差异参数注入 system prompt

### D4 SQLite 缓存（P0）
- 复刻图片 CacheManager：内存 dict + SQLite（video_prompt_cache.db），key=platform|prompt|creative|max_length|lang

### D5 输入分类 + 多候选择优（P1）
- 题材分类（历史/科幻/广告/短剧/自然/人物）+ 镜头意图（动态/静态/特写/全景）关键词检测
- num_candidates>1 时 evaluator 评分择优

### D6 evaluator + feedback（P1）
- evaluator：保真一致性（原文实体命中）、六要素完整、镜头字段合法、长度达标（150-300 词）
- feedback：好/坏反馈 → 沉淀入种子库（append + 质量分调整）

### D7 中文输出（P1）
- output_language=zh：保留中文主体 + 镜头术语双语（shot/camera 字段仍英文枚举，prompt 中文）

### D8 videogen 集成（P2）
- Multi-Publish：video-prompt-engine-contract 支持 VIDEO_PROMPT_PORT=8020 配置；videogen 优先走独立引擎，失败/未配置回退 8013 domain=video（兼容）

## Risks
- 知识库扩充数据质量参差 → quality_score 过滤 + source 标注
- 多平台策略差异基于公开资料 → 标注"首版近似"，平台实测后续校准
- videogen 切换 → 默认保留 8013 回退，逐步灰度

## Migration
- 独立引擎先全量增强（不破坏现有 8020 契约），videogen 配置切换可选
