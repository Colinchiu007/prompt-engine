# prompt-engine

图片生成提示词优化引擎（Vue 3 看板 + CLI + MCP）。

## 快速导航

完整开发规范见 [docs/AGENTS.md](docs/AGENTS.md)，包含：关键路径、25 维风格分类器、三级分类流水线、测试命令、版本号。

## 识图能力

底层模型不具备原生识图能力。遇到图片时，**不要用 Read 工具看图**，改用共享识图脚本：

```
node D:/Data/projects/Multi-Publish/tools/vision.js "<图片路径>" "用中文详细描述这张图片"
```

网络图片用 `--url`：

```
node D:/Data/projects/Multi-Publish/tools/vision.js --url "<图片链接>" "用中文详细描述这张图片"
```

触发场景：用户分享图片（本地或网络 URL）、消息出现 "Saved attachments:"、用户要求分析/描述/识别图片。配置在共享脚本同目录 `.env`（当前 OpenCode Go / mimo-v2.5）。配置好后用户直接发图片即自动识图。
