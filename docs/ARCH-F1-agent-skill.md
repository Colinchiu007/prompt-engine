# ARCH-F1: Agent Skill 分发方案

## 目标

为 prompt-engine 导出 **可安装的 Agent Skill**，使其在 Claude Code / Cursor / Hermes 等 AI 编码工具中可直接被发现和调用。完全对标 awesome-gpt-image-2 的 `agents/skills/gpt-image-2-style-library/` 模式。

## 目录结构

```
prompt-engine/agents/skills/prompt-engine/
├── SKILL.md                  # 主技能文件（Agent 入口）
├── bin/
│   └── install.mjs           # 安装脚本（复制到目标 Agent 目录）
├── references/
│   ├── api-reference.md      # API 端点参考
│   ├── style-library.md      # 25 维风格分类参考
│   └── cli-commands.md       # CLI 命令参考
└── package.json              # NPM 发布（可选）
```

## SKILL.md 设计

核心工作流：
```
1. detect user intent (classify / optimize / recommend / feedback)
2. match to prompt-engine API/CLI
3. execute and return result
```

参考 awesome-gpt-image-2 的 `agents/skills/gpt-image-2-style-library/SKILL.md` 模式。

## 安装方式

```bash
# 方式 1: 本地链接
npm run install:skill

# 方式 2: 手动复制
cp -r agents/skills/prompt-engine ~/.hermes/skills/
```
