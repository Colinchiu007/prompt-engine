# 图片/视频提示词引擎重构：瘦共享内核 + 领域分离 + 能力对齐

## 背景
2026-08-12 视频引擎（`video_prompt_engine/`，8020）按用户要求与图片引擎（`prompt_engine/`，8013）完全分离
（独立端口/进程/知识库/缓存/策略/契约）。但分离后两引擎形成复制式分叉，骨架层高度同构：

- `llm/`：视频版 `BaseVideoLLMProvider` 是改进版（超时重试/动态 max_tokens/默认 base_url），图片版多 provider 工厂未回灌
- `feedback.py`：视频版有原子写（tmp + os.replace）+ 进程锁；图片版直接覆盖写
- `strategies/base.py`：@register/get_strategy 注册表两套
- `knowledge/`：build/loader/vector_store 骨架两套（视频版手写 TF-IDF 免 sklearn 依赖，优于图片版）
- 图片引擎残留 `strategies/video/generic.py` 旧遗迹（生产 8013 domain=video 回退路径 + 测试引用）

Higgsfield P1/P2 机制（模板形态切换/导演风格词典/失败模式闭环/角色描述符资产库）需要双引擎落地，
继续复制会放大多倍维护成本。

## 决策（2026-08-14 双模型评审：Claude 支持「瘦核」方案；antigravity 账号不可用降级为主代理分析+Claude 评审）
- **不回退整合**：保持独立进程/端口/部署回滚边界/密钥隔离/种子库隔离（尊重 ARCH v2.0 与用户要求）
- **新建领域无关共享内核 `prompt_engine_core/`**：只放行为一致、领域无关的机械件
- **领域层完全保留双份**：models/classifier/optimizer/strategies/evaluator/cache key 格式/feedback 语义/种子资产
- **能力对齐**：视频版改进（原子写/超时重试/<think> 剥离/JSON_RETRY_HINT）回灌图片版
- **Multi-Publish 契约层不动**（JS 两文件重复率仅 3.3%，不值得合并）
- **旧 `strategies/video/` 保留为 legacy 回退**（8013 domain=video 是生产回退路径），不删除

## 目标
1. 新建 `prompt_engine_core/`：llm（超时重试+动态 max_tokens）、atomic（原子写+锁）、registry（注册器）、
   config（yaml+env+.env 解析）、text（<think> 剥离/JSON 清理/长度工具）、api（FastAPI 工厂/health）、
   knowledge（build/loader 骨架）、vector_store（手写 TF-IDF）
2. 视频引擎迁移 core 机械件（llm/registry/atomic/knowledge），行为零变化
3. 图片引擎能力对齐（feedback 原子写、llm 超时重试、<think> 剥离、registry 复用），行为零回归
4. spec「代码零耦合」条款改为「不得 import 对方领域层，允许依赖 prompt_engine_core」

## 非目标
- 不合并两引擎为单服务、不共享种子库/知识数据资产
- 不改 Multi-Publish 契约层、不删 strategies/video/ 回退路径

## 实施阶段（每阶段全量回归）
- Phase 1：新建 core（纯新增，两引擎零改动）
- Phase 2：视频引擎迁移 core
- Phase 3：图片引擎能力对齐
- Phase 4：文档 + 全量回归 + 双模型审查 + 归档
