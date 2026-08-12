# Tasks — video-prompt-engine（独立视频提示词优化引擎）

## 1. 独立包骨架
- [ ] 1.1 创建 `video_prompt_engine/` 包（models.py/config.py/__init__.py），模型含 VideoPlatformType/OptimizeRequest/OptimizeResult/VideoPromptResult/context 白名单
- [ ] 1.2 独立配置 `config_video.yaml`（port 8020、knowledge.persist_dir=video_prompts_db、LLM provider）
- [ ] 1.3 断言无 `import prompt_engine` 引用（测试）

## 2. 策略注册表
- [ ] 2.1 `strategies/base.py`：BaseVideoStrategy（build_system_prompt/post_process_video/extract_video_meta/render）+ @register/get_strategy
- [ ] 2.2 `strategies/generic_video.py`：六要素 + Fact-Fidelity + 镜头语言（复刻并独立实现）
- [ ] 2.3 `strategies/seedance.py`：@引用语法 + 多模态约束（来自 seedance2-skill）
- [ ] 2.4 未知平台回退 generic_video

## 3. 视频知识库（7 仓库）
- [ ] 3.1 从 img-prompt 提取视频维度关键词 → `knowledge/keywords_video.json`（镜头/运镜/光影/色彩/风格/场景/动作，中英）
- [ ] 3.2 从 awesome-video-prompts 提取 50 个结构化提示词 → `knowledge/seed_video_prompts.json`（few-shot 种子）
- [ ] 3.3 从 awesome-seedance/awesome-seedance-2-prompts/drama-skills 补充商用/短剧种子与模板
- [ ] 3.4 `knowledge/build.py` + `knowledge/vector_store.py`（TF-IDF，独立 video_prompts_db）
- [ ] 3.5 `rag_retriever.py`：platform 过滤 few-shot 检索
- [ ] 3.6 `GET /v1/video/keywords` 接口

## 4. 编排器与 API
- [ ] 4.1 `optimizer.py`：缓存（内存）→ 策略 → system prompt → context 注入 → RAG few-shot → LLM 调用 → 结构化后处理
- [ ] 4.2 `prompt_builder.py`：build_system_prompt + build_context_section
- [ ] 4.3 `llm/`：base + minimax/openai_compat（复用 config provider 机制，独立实现）
- [ ] 4.4 `api/rest.py`：/v1/video/optimize、/v1/video/optimize/batch（≤20、Semaphore(8)）、/v1/video/platforms、/v1/video/keywords、/health
- [ ] 4.5 `cli.py` + `python -m video_prompt_engine` 入口

## 5. 测试
- [ ] 5.1 模型/契约测试（platform 枚举、context 白名单、敏感键拦截）
- [ ] 5.2 策略测试（generic_video 结构化输出、Fact-Fidelity 指令、seedance 指令、未知平台回退）
- [ ] 5.3 知识库测试（关键词词典加载、few-shot 检索、平台过滤）
- [ ] 5.4 API 测试（单条/批量 200、12 条单批、空项 fail closed、并发有界）
- [ ] 5.5 独立断言：无 import prompt_engine；图片引擎测试全绿（零回归）

## 6. 文档
- [ ] 6.1 `01-docs/PRD-video-prompt-engine.md`（详细：数据校验/流程/功能逻辑/交互/显示项/提示文字/验收）
- [ ] 6.2 `01-docs/ARCH-video-prompt-engine.md`（模块/数据流/JSON schema/错误码/部署）
- [ ] 6.3 `01-docs/IMPLEMENTATION-ANALYSIS-video-prompt-engine.md`（实现级分析）
- [ ] 6.4 CHANGELOG + README（独立引擎入口）

## 7. 交付
- [ ] 7.1 推送 codex/video-prompt-engine → PR → CI → 合并
- [ ] 7.2 Multi-Publish 文档标注独立引擎落点（PRD-video-creation 相关章节）
- [ ] 7.3 openspec apply + 三同步归档
- [ ] 7.4 更新记忆
