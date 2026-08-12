# PRD — 独立视频提示词优化引擎（video-prompt-engine）

> 版本：v1.0 ｜ 日期：2026-08-12 ｜ 状态：待评审
> 关联 OpenSpec change：`video-prompt-engine` ｜ 仓库：prompt-engine（`video_prompt_engine/` 独立包）

## 1. 背景与目标

### 1.1 背景
- 图片 prompt-engine（`prompt_engine/`，8013）是图片提示词优化引擎。此前 video 领域被加为其 `domain=video` 分支（同一服务、共享知识库/缓存/框架）。
- **用户明确要求：视频提示词优化引擎与图片引擎分开，不要混在一起。**
- 需要一个视频专属关键词/提示词库，复用 7 个开源仓库：img-prompt（5040 标签）、awesome-video-prompts（50 结构化提示词）、seedance2-skill（Seedance 撰写指南）、awesome-seedance / awesome-seedance-2-prompts（商用用例）、drama-skills（短剧分镜）、stable-diffusion-videos（动画技术参考）。

### 1.2 目标
- **P0**：独立 Python 包 `video_prompt_engine/` + 独立 REST 服务（端口 8020），与图片引擎零耦合（不 import `prompt_engine.*`、不共享知识库/缓存/配置）。
- **P0**：技术机制复刻（Optimizer 编排 / 策略注册表 / RAG few-shot / LLM 供应商 / 结构化输出 / 批量契约），架构与图片引擎相同、实现独立。
- **P0**：视频关键词库（7 仓库 → 关键词词典 + few-shot 种子 + 平台策略指令）。
- **P1**：结构化视频输出（shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint）+ Fact-Fidelity 事实保真。
- **P1**：批量契约（单批 ≤20、有界并发 8、结果顺序一致、逐条非空 fail closed）。

### 1.3 非目标
- 不迁移既有 `prompt_engine` 的 domain=video 分支（保留兼容；独立引擎为视频优化正式落点，文档标注）。
- 不强制 Multi-Publish videogen 切换到 8020（列为后续可选迁移）。
- 不引入外部向量库依赖（TF-IDF 自实现）。

## 2. 与图片引擎的分离边界

| 维度 | 图片引擎 prompt_engine（8013） | 视频引擎 video_prompt_engine（8020） |
|---|---|---|
| Python 包 | `prompt_engine/` | `video_prompt_engine/`（不 import prompt_engine.*） |
| REST 端口 | 8013 | 8020 |
| 知识库 | prompts_db（图片种子） | video_prompts_db（视频种子） |
| 策略 | midjourney/sd/dalle/... | generic_video/seedance/veo/kling/... |
| 模型 | 图片 + 旧 video 分支模型 | 视频专用模型（独立定义） |
| 缓存/配置 | 共享于 prompt_engine | 独立（video 引擎内存缓存 + config_video.yaml） |
| 机制 | Optimizer/策略注册/RAG/LLM/模板 | 复刻相同机制（独立实现） |

## 3. 功能逻辑

### 3.1 优化主流程（Optimizer）
```
请求 → 内存缓存命中? → 直接返回
     → 策略加载（get_strategy(platform)，未知回退 generic_video）
     → system prompt（策略.build_system_prompt + context 注入 + 关键词维度提示 + RAG few-shot）
     → LLM 调用（num_candidates 次，推理块剥离）
     → 结构化后处理（post_process_video：渲染单串 + video 字段收敛）
     → fail-closed 校验（error→detail→空串）
     → 缓存写入 → 返回
```

### 3.2 批量优化（Batch）
- `POST /v1/video/optimize/batch`：单批 ≤20 条；`asyncio.Semaphore(8)` 有界并发；`gather` 保持顺序；逐条 fail closed。
- 12 条单批 200（对齐 videogen 12 场景单批）；>20 由调用方分块兜底。

### 3.3 视频关键词库（7 仓库复用）
| 来源 | 资产 | 用途 |
|---|---|---|
| img-prompt（5040 标签） | `keywords_video.json`：视频维度关键词（镜头/运镜/光影/色彩/风格/场景/动作，中英） | 输入增强 + `GET /v1/video/keywords` 查询 |
| awesome-video-prompts（50） | few-shot 种子（结构化 JSON 提示词） | RAG 高质量示例 |
| seedance2-skill | Seedance 平台策略指令（@引用/多模态约束） | strategies/seedance.py system prompt |
| awesome-seedance / -2 | 商用用例提示词 | few-shot 补充 |
| drama-skills | 短剧分镜/视频提示词模板 | 策略模板素材 |
| stable-diffusion-videos | 动画技术 | 参考（不入库） |

### 3.4 策略体系
- `BaseVideoStrategy`：build_system_prompt / post_process_video / extract_video_meta / render / @register。
- 首期：`generic_video`（六要素：主体→动作→环境→色彩→光影→风格/镜头；Fact-Fidelity 保真）、`seedance`（@引用语法、多模态输入约束、运镜复刻）。
- 输出结构化：`{prompt, shot, camera, motion_intensity, scene_transition, continuity_token, duration_hint}`。

## 4. 数据校验

### 4.1 请求（/v1/video/optimize）
| 字段 | 校验 | 越界/非法 |
|---|---|---|
| prompt | 非空，≤2000 | 空 → 422 |
| domain | 恒 'video' | 非 video → 422 |
| platform | 视频平台枚举 | 未知 → 回退 generic_video |
| creative_level | 1-10 | 收敛 |
| max_length | 50-2000 | 收敛（默认 500） |
| num_candidates | 1-5 | 收敛 |
| negative_prompt | ≤500 | 截断 |
| context | 白名单键 | 未知键忽略 + warning；敏感键拦截 |

### 4.2 响应 fail closed
`error` 非空 → 失败；`detail` 非空 → 422 语义；`optimized_prompt` 非空字符串；视频字段越界收敛、缺失给默认。

### 4.3 配置（config_video.yaml）
| 键 | 默认 | 说明 |
|---|---|---|
| server.port | 8020 | 独立端口 |
| knowledge.persist_dir | video_prompts_db | 独立向量库 |
| knowledge.retrieval.top_k | 3 | few-shot 数量 |
| llm.provider/model/key | 从环境/配置 | 复用图片引擎同供应商机制 |

## 5. 交互逻辑与显示项

### 5.1 调用方（Multi-Publish videogen 等）
- 后续 videogen 集成可切换到 `PROMPT_VIDEO_PORT=8020`（本次文档标注，不强制）。
- 错误码：`VIDEO_OPTIMIZE_FAILED`（error）、`VIDEO_OPTIMIZE_EMPTY`（空串）、`VIDEO_BATCH_COUNT_MISMATCH`（数量不一致）、`CONTEXT_SENSITIVE_KEY`（敏感键）。

### 5.2 显示项（关键词库 UI 预留）
- `GET /v1/video/keywords` 返回按维度组织的关键词，供视频创作页"视频关键词建议"展示（中英双语 + 维度标签）。
- 提示文字示例："视频提示词已优化（镜头：特写｜运镜：推镜｜光影：金色时刻）"。

## 6. 验收标准

| # | 验收项 | 判定 |
|---|---|---|
| A1 | 独立服务 8020 /health | ok；8013 不受影响 |
| A2 | 源码无 import prompt_engine | 静态断言通过 |
| A3 | 12 条单批 | 200、顺序一致、逐条非空 |
| A4 | 空项/error | fail closed |
| A5 | 未知平台 | 回退 generic_video |
| A6 | 关键词库查询 | 返回维度化中英关键词 |
| A7 | Fact-Fidelity | 中文历史事实不被改写 |
| A8 | 图片引擎测试 | 全绿（零回归） |

## 7. 版本历史
- v1.0（2026-08-12）：初版（独立引擎 + 视频关键词库 + 分离边界）。
