"""DSL 模板语法解析器 — 借鉴 sd-dynamic-prompts 的模板语法。

支持:
  {option1|option2|option3}  - 变体（随机选一个）
  __wildcard__               - 通配符（从注册池读取）
  {N$$opt1|opt2}             - 数量限定（随机选 N 个）
"""
import random
import re
from typing import Optional


# 通配符池: {name: [values]}
_wildcard_pools: dict[str, list[str]] = {}


def register_wildcard_pool(name: str, values: list[str]):
    """注册通配符池。"""
    _wildcard_pools[name] = values


def _get_wildcard_values(name: str) -> list[str]:
    """获取通配符池的值，不存在返回空列表。"""
    return _wildcard_pools.get(name, [])


def parse(template: str) -> str:
    """解析模板（当前返回规范化后的字符串）。"""
    # 验证括号匹配
    depth = 0
    for ch in template:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth < 0:
            raise ValueError("Unmatched closing brace")
    if depth != 0:
        raise ValueError("Unmatched opening brace")
    return template


def render(template: str) -> str:
    """渲染模板，返回一个随机结果。"""
    if not template:
        return template

    result = []
    i = 0
    while i < len(template):
        # 转义: \{ → {
        if template[i:i+2] == "\\{":
            result.append("{")
            i += 2
            continue
        if template[i:i+2] == "\\}":
            result.append("}")
            i += 2
            continue

        # 变体: {a|b|c} 或 {N$$a|b|c}
        if template[i] == "{":
            end = template.index("}", i)
            content = template[i+1:end]
            # 检查是否是数量限定
            if "$$" in content:
                parts = content.split("$$", 1)
                try:
                    n = int(parts[0])
                except ValueError:
                    n = 1
                options = [o.strip() for o in parts[1].split("|")]
                selected = random.sample(options, min(n, len(options)))
                result.append(", ".join(selected))
            else:
                options = [o.strip() for o in content.split("|")]
                result.append(random.choice(options))
            i = end + 1
            continue

        # 通配符: __name__
        if template[i:i+2] == "__":
            end = template.index("__", i + 2)
            name = template[i+2:end]
            values = _get_wildcard_values(name)
            if values:
                result.append(random.choice(values))
            else:
                result.append(f"__{name}__")
            i = end + 2
            continue

        result.append(template[i])
        i += 1

    return "".join(result)


def load_wildcards_from_yaml(path: str) -> int:
    """从 YAML 文件加载通配符池并注册。

    YAML 格式:
        pool_name:
          - value1
          - value2

    Returns:
        注册的池数量
    """
    import yaml
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return 0
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return 0
    count = 0
    for name, values in data.items():
        if isinstance(values, list):
            register_wildcard_pool(name, values)
            count += 1
    return count


def load_default_wildcards() -> int:
    """加载默认通配符文件 (templates/wildcards.yaml)。"""
    from pathlib import Path
    path = Path(__file__).parent / "templates" / "wildcards.yaml"
    return load_wildcards_from_yaml(str(path))
