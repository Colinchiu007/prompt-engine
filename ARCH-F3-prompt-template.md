# ARCH-F3: Prompt-as-Code 模板系统方案

## 目标

引入结构化 prompt 模板系统，将 prompt 拆解为可组合的原子块（主体/光影/材质/排版/构图），替代当前的"一次性 LLM 生成"模式。灵感来自 awesome-gpt-image-2 的 Prompt-as-Code 哲学。

## 核心概念

```
传统模式:
  prompt → LLM("写一个prompt") → 散文式输出
  ❌ 不可控制 → 每次都不一样
  ❌ 不能缓存 → 每次都调用 LLM
  ❌ 不能组合 → 没有模块化

Prompt-as-Code:
  prompt → [主体块] + [光影块] + [材质块] + [构图块]
         → 各块独立模板 + 参数填充
         → 组合成完整 prompt
  ✅ 可预测 → 模板确定结构
  ✅ 可缓存 → 模板可预编译
  ✅ 可组合 → 参数化拼接
```

## 数据结构

```python
@dataclass
class PromptBlock:
    """一个可组合的 prompt 块"""
    name: str                    # "subject", "lighting", "materials", ...
    template: str                # "A {adjective} {subject} {action}"
    params: dict[str, list]      # {adjective: ["majestic", "serene"], subject: ["cat", "mountain"]}
    weight: float = 1.0          # 在 prompt 中的相对重要性

    def render(self, **kwargs) -> str:
        """填充参数渲染出文本"""
        return self.template.format(**kwargs)


class PromptTemplate:
    """完整的 prompt 模板 = 多个 PromptBlock 的组合"""
    name: str
    platform: PlatformType
    blocks: list[PromptBlock]
    separator: str = ", "        # 块之间的连接符
    style_categories: list[str]  # 关联的 StyleCategory

    def render(self, creative_level: int) -> str:
        """根据创意等级渲染：低级用简单参数，高级用复杂参数"""
```

## 与现有架构集成

```
optimizer.optimize()
  └── strategy.build_system_prompt()  →  (现有)
  └── strategy.post_process()         →  (现有 + keyword injection)
  └── template_engine.render()        →  (新增, 替换部分 LLM 工作)
```

template_engine 作为 LLM 的补充而非替代：
- 低创意等级（1-3）→ 纯模板渲染，不调 LLM
- 中等创意等级（4-7）→ 模板+LLM 混合
- 高创意等级（8-10）→ 全 LLM 生成，模板仅作参考

## 文件结构

```
prompt_engine/
├── template_engine.py     # 模板引擎核心
├── templates/
│   ├── __init__.py         # 模板加载器（已有）
│   ├── styles.yaml         # 风格模板（已有，已对接 StyleCategory）
│   ├── blocks/             # 原子化 prompt 块
│   │   ├── subject.yaml
│   │   ├── lighting.yaml
│   │   ├── materials.yaml
│   │   ├── composition.yaml
│   │   └── quality.yaml
│   └── presets/            # 预定义场景模板
│       ├── portrait.yaml
│       ├── landscape.yaml
│       └── product.yaml
```

## 测试

- 测试 PromptBlock.render()
- 测试 PromptTemplate.render() 不同创意等级
- 测试模板加载和缓存
- 测试与 optimize 的集成（低等级走模板）
