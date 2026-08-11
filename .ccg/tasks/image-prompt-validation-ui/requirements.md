# 需求增强：文案分句 → 提示词 → 生图对比验证前端

## 1. 目标
做一个 Web 前端界面（挂在 prompt-engine 现有 /web/ 控制台内，新增页签），核心目的是**验证图片提示词实际生成图片的效果**：
1. 输入一篇文案（≤6000 字）
2. 调用分句模型（smart-sentence-splitter，POST /v1/split）分句，**展示具体分句结果**
3. 每个分句经 MiniMax 多模态模型（文字推理）生成图片提示词
4. 同一提示词每次生成 **2 张图片** 并排对比

## 2. 外部契约（来自 Multi-Publish 运营后台/既有适配器，直接复用）
### 2.1 MiniMax 文字推理（LLM）
- POST `{base_url}/chat/completions`（OpenAI 兼容），base_url 默认 `https://api.minimaxi.com/v1`
- Headers: `Authorization: Bearer {api_key}`
- Body: `{ model: "MiniMax-M3" | "MiniMax-M2.7", messages: [...], temperature?, max_tokens? }`
- 响应: `data.choices[0].message.content`，需剥离 `<think>...</think>` 推理块（MiniMax 推理模型会输出思考过程）

### 2.2 MiniMax 生图
- POST `{base_url}/image_generation`（同步接口）
- Body: `{ model: "image-01", prompt, response_format: "url", n: 2, aspect_ratio: "1:1" }`
- 响应: `data.data.image_urls[]`（URL 数组）
- 注意：HTTP 200 但 image_urls 为空时须显式报错（内容安全策略/瞬时故障）

### 2.3 分句服务（smart-sentence-splitter，端口 8002，可配置）
- POST `/v1/split`，Body: `{ text, language: "auto", mode: "balanced" }`
- 响应: `sentences[]`（含 index/text/language/tier/confidence/char_count）+ scenes[]

### 2.4 API Key
- 前端"模型设置"区域输入 MiniMax API Key（仅输入 API Key 即可，base_url/model 用默认值，可高级展开覆盖）
- 验证时从 Multi-Publish 已登录 profile（`%APPDATA%/@multi-publish/desktop/multi-publish.db` 中 minimax-image provider 的 safeStorage 加密 key，经 Electron 运行时解密）注入，绝不落盘到提交物

## 3. 功能规格
### 3.1 输入区
- 多行文本框，maxlength=6000，实时字数统计
- 按钮：开始分句；清空
- 提示文字：分句上限、字数超限拦截

### 3.2 分句结果区
- 表格/卡片列表展示每个分句：序号、文本、字数、置信度、tier
- 支持折叠超长分句、复制单个分句
- 可编辑分句文本（允许手工修正后重新生成提示词）

### 3.3 提示词生成区
- 每个分句调用 MiniMax LLM 生成生图提示词（中文文案 → 英文视觉描述，含风格/构图/光影）
- 生成中 loading、失败重试、单句独立状态
- 展示生成的提示词（可复制、可编辑）

### 3.4 生图对比区
- 每个提示词生成 2 张图（n=2），并排展示，标注"图1/图2"
- 支持重新生成（重跑该句 2 张）、放大查看
- 图片 URL 可复制；生成失败显示错误原因

### 3.5 设置区
- MiniMax API Key 输入（必填，password 型输入框，遮罩显示）
- 高级：base_url、LLM model、图片尺寸/aspect_ratio、生成数量（默认 2）
- 可测试连接（调用 LLM 轻量探测）
- API Key 只存浏览器内存/可选 localStorage（本地单机工具，不落服务端；如需服务端存储则用 MINIMAX_API_KEY 环境变量）

## 4. 数据校验
- 文案：非空、≤6000 字（按字符数）、去首尾空白
- 分句数：>0；超过 30 句提示分批处理（生图成本提示）
- 提示词：非空、≤2000 字符（MiniMax image-01 prompt 限制）
- API Key：非空；格式提示（MiniMax key 形如 eyJ... 或 32+ 位）

## 5. 交互逻辑
- 串行流水线：输入 → 分句 → （逐句）LLM 提示词 → 生图
- 每句独立状态机：idle → splitting → prompting → generating → done/error
- 断点续做：失败句可单独重试；全部完成显示汇总（成功/失败数）
- 生图耗时较长（10-60s/张），需 loading + 提示

## 6. 显示项与提示文字（详见 PRD 补充章节）
- 所有空态/加载态/错误态均有明确中文提示
- 错误分级：可重试（超时/网络）vs 不可重试（鉴权 401/内容安全）

## 7. 不做什么（Non-goals）
- 不做账号体系/多用户
- 不做批量队列后台任务（前端顺序执行即可）
- 不改 smart-sentence-splitter / Multi-Publish 代码
- 不引入数据库存储生成历史（单次会话内展示）
