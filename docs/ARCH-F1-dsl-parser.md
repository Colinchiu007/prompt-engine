# ARCH-F1: 模板语法 DSL

## 目标

实现类似 sd-dynamic-prompts 的模板语法：`{option1|option2}` 变体 + `__wildcard__` 通配符 + `N$$` 数量限定。

## 语法规格

```
# 变体: {option1|option2|option3}
A {cat|dog|bird} sitting on a {mat|chair}

# 通配符: __filename__
__colors__ __animals__

# 数量限定: N$$options (随机选 N 个)
{2$$artist1|artist2|artist3|artist4}

# 嵌套: 支持变体内嵌套变体
{__color__|{red|blue|green}} {__animal__}

# 字面量: 转义 \{ 和 \}
This is \{not a variant\}
```

## 文件

```
prompt_engine/dsl_parser.py
├── class VariantCommand
├── class WildcardCommand  
├── class LiteralCommand
├── class SequenceCommand
├── def parse(template: str) -> Command
```

## 设计

基于 Python 标准库 `ast` / 手写递归下降解析器（避免引入 pyparsing 依赖）。对于 prompt-engine 的模板规模，手写解析器足够。
