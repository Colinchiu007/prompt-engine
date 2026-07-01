# ARCH-F1: 模板驱动优化方案

## 目标

借鉴 prompt-optimizer 的模板驱动模式，将策略代码 `build_system_prompt()` 中的 LLM 指令抽取为独立模板文件（YAML），EN/ZH 双语。使得优化策略可独立于代码修改和扩展。

## 当前状态

```python
# strategies/midjourney.py — 当前 hardcoded
@classmethod
def build_system_prompt(cls, style=None, creative_level=5, max_length=500):
    return f"""你是一位 Midjourney 提示词专家...
规则: --ar 16:9, --v 6.1, --style raw...
..."""
```

## 新架构

```
prompt_engine/templates/prompts/
├── midjourney/
│   ├── en.yaml          # 英文模板
│   └── zh.yaml          # 中文模板
├── stable_diffusion/
│   ├── en.yaml
│   └── zh.yaml
├── dalle/
│   ├── en.yaml
│   └── zh.yaml
└── ...

# 模板加载器 (已有 templates/__init__.py 扩展)
templates/__init__.py → 新增 load_prompt_template(name, lang)
```

## YAML 模板格式

```yaml
# templates/prompts/midjourney/en.yaml
name: midjourney
language: en
description: "Midjourney prompt optimization strategy"
system_prompt: |
  你是一位 Midjourney 提示词专家...

rules:
  aspect_ratio:
    photography: "4:3"
    portrait: "3:4"
    landscape: "16:9"
    anime: "16:9"
  version: "6.1"
  style_mapping:
    realistic: "raw"
    photography: "raw"
    anime: "expressive"
    fantasy: "expressive"
```

## 与现有架构集成

```python
# 现状
from prompt_engine.templates import load_prompt_template
tmpl = load_prompt_template("midjourney", lang="en")
system_prompt = tmpl["system_prompt"].format(style=style, ...)

# 策略文件只需引用模板，不再硬编码
```

## 测试

- 测试模板加载 (中/英文)
- 测试模板变量填充
- 测试回退 (英文不存在时用中文)
