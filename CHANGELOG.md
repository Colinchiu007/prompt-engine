# Changelog

本项目更新日志。

## [Unreleased]

-

## [v0.3.1] — 2026-06-12

### 变更

**全面重写 7 个策略文件** — 从 [Nano Banana Pro Prompt 库](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts)（14,292 条社区高质量 prompt）提取各平台最佳写作模式。

### 数据来源

| 源 | 说明 |
|---|---|
| `README.md` (英文) | 14,292 条 prompt，42 个 Use Case 分类 + 17 种 Style 分类 + 15 种 Subject 分类 |
| `README_zh.md` (中文) | 社区中文 prompt 样本，覆盖通义/文心/即梦等国内平台 |
| 分析维度 | 高频术语（光照/镜头/颜色/纹理/构图）、结构模式（主体→动作→环境→光照→风格）、质量修饰词、负面提示词 |

### 各策略文件变更

#### `midjourney.py`（32 → 247 行）

| 新增规则 | 来源 |
|---------|------|
| 风格→画幅映射表 | 摄影=4:3、人像=3:4、风景/动漫=16:9（社区高频组合） |
| `--v 6.1` 默认版本 | 社区当前推荐版本 |
| 风格→`--style raw/expressive` 映射 | 写实/摄影用 raw（少美化），动漫/奇幻用 expressive（多创意） |
| 风格→`--s` 值 | creative_level × 50（50-500 范围） |
| 镜头参数库（8 种） | 85mm f/1.8、50mm f/2.8、35mm f/2.0、Macro、135mm... |
| 光照描述库（10 种） | soft diffused / dramatic side / golden hour / cinematic chiaroscuro / volumetric... |
| 构图描述库（8 种） | rule of thirds / centered / leading lines / golden ratio / bird's eye... |
| 质量修饰词 10 级梯度 | creative_level 1→10 对应从 "simple style" 到 "trending on artstation, HDR, 8k" |

**关键发现**：NBP 库中 85mm 相关 prompt 占比 ~12%，f/1.8 约 8%，golden hour 约 6%。

#### `stable_diffusion.py`（35 → 148 行）

| 新增规则 | 来源 |
|---------|------|
| 12 种风格的 `(quality:1.2)` 前缀词 | 社区 prompt 开头几乎都有 masterpiece/best quality 标签 |
| 13 种风格的负面提示词 | 摄影风格不想要 3D 渲染、动漫不想要写实... |
| 光照权重标签（10 种） | `(natural lighting:1.2)`, `(cinematic lighting:1.3)` 等 |
| 质量前缀词库 | 每个风格一个专用前缀短语 |

**关键发现**：NBP 库中约 70% 的 SD 相关 prompt 使用 `(word:1.2)` 权重语法，SD 对权重语法极其敏感。

#### `dalle.py`（29 → 143 行）

| 新增规则 | 来源 |
|---------|------|
| 14 种风格的详细自然语言描述 | DALL·E 偏好段落式而非标签式 |
| 创意度 1-10 细节链 | 从"简单描述"到"主体全维度+分层场景+多光源+精确配色+材质对比+构图法则" |
| 结构模板（6 步） | SUBJECT → ACTION → ENVIRONMENT → COLOR → LIGHTING → STYLE |

**关键发现**：NBP 库中 DALL·E 类 prompt 几乎不使用 `--ar` 等特殊语法，完全是自然语言。

#### `tongyi.py`（28 → 122 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的中文风格描述 | "可见笔触"、"颜色晕染"、"霓虹灯光" 等精确中文术语 |
| 创意度 1-10 细节级别 | 从"仅主体+动作"到"主体全维度+多层场景+主光/辅光/轮廓光+精确配色+多种材质+构图法则" |
| 社区写作技巧 | 精确颜色（藏蓝/薄荷绿/暖琥珀色）、表情细节、材质词 |

**关键发现**：NBP 社区 prompt 中中文 prompt 质量与英文相当，关键在于精确度而非语言。

#### `yizhang.py`（28 → 86 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的关键词标签 | 文心一格偏好"简洁+明确+具象" |
| 2 个完整写作示例 | 从社区 prompt 提取并改写 |
| 写作技巧（4 类） | "形容词+名词"、具体场景词、氛围词、程度词 |

**关键发现**：文心一格的最佳 prompt 是"关键词+逗号分隔+短句"，不是长段落。

#### `jimeng.py`（28 → 122 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的视觉风格描述 | 即梦偏好"视觉冲击力" |
| 创意度 1-10 冲击力描述 | 4 个档位：简洁 → 视觉冲击 → 光影戏剧化 → 极具视觉震撼力 |
| 4 类社区技巧词库 | 动词（投下/划过/穿透）、色彩（烈焰红/霓虹紫）、光影（逆光/轮廓光）、构图（低角度/仰视/框架式） |

**关键发现**：即梦（字节系）社区 prompt 强调动词的力量感和色彩的饱和度。

#### `generic.py`（28 → 54 行）

| 新增规则 | 来源 |
|---------|------|
| 通用 prompt 结构模板 | 6 步：Subject → Action → Environment → Color → Lighting → Composition |
| 社区高频质量模式 | 颜色精度、光照精度、镜头引用、表情细节、纹理细节 |

### 影响

- **不破坏现有 API** — `build_system_prompt()` 签名不变
- **优化质量预期提升** — 策略指导更精确，LLM 输出更贴近社区最佳实践
- **新增 PORTRAIT / LANDSCAPE 风格** — `models.py` 新增枚举

### 待办

- [ ] 将 NBP prompt 库作为 RAG 知识库，提供 few-shot 增强（Phase 2）
- [ ] 基于 NBP 社区分类数据构建风格模板库 `templates/styles.yaml`
