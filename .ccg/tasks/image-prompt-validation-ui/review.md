# 双模型审查记录（2026-08-11）

## 审查方式
- Claude（codeagent-wrapper，reviewer role）：完成，输出 Critical×2 / Warning×3 / Info×9
- Antigravity：后端不可用（exit 1，第二次确认），按机制硬化规则降级为单模型 + 主代理自析补充

## Claude 发现与修复状态

| 级别 | 发现 | 修复 |
|------|------|------|
| Critical | hasKey 死代码：window.__PE 无 hasEnvKey + shared 过期捕获 → env key fallback 时 UI 禁用 | 新增 GET /v1/compare/status（has_env_key）；前端 onMounted 查询；hasKey 运行时计算 |
| Critical | 三端点 async def 内同步 httpx/OpenAI 阻塞事件循环（复现 61ad3b2 Bridge 重启缺陷） | 三处改为 asyncio.to_thread 包裹同步调用 |
| Warning | minimax_client.py data 形状未防御 → 异常形状 500 | isinstance(dict) 防御 |
| Warning | base_url "SSRF 缓解" 名不副实（回环/私网/明文放行） | 加强校验：拒绝回环/私网/链路本地/云 metadata；非回环强制 https |
| Warning | 错误映射测试覆盖不足 | 参数化 7 种 error_type 映射 + base_url 拒绝 9 例 + status + truncated + 枚举校验，共 +22 例（39 全过） |
| Info | localStorage 与"不落盘"措辞矛盾 | PRD 措辞统一为"不落服务端盘/日志"（见文档修订） |
| Info | compare 忽略 MINIMAX_BASE_URL | DEFAULT_LLM_BASE_URL = env MINIMAX_BASE_URL |
| Info | 提示词 >2000 截断无提示 | PromptResult.truncated + 前端"已截断"标签 |
| Info | split language/mode 无枚举 | Literal 校验 |
| Info | split 错误 detail 未清洗 | 清洗换行/控制字符 |
| Info | n 无控件可改（死配置） | 高级设置加 el-input-number（1-4） |
| Info | shared.copyText 名存实亡 | 运行时解析 window.__PE |
| Info | preview 上限 3 vs compare 上限 4 | 统一 MAX_IMAGE_COUNT |
| Info | pydantic 422 detail 数组渲染 | 未改（可达性低，现有 api.parse 行为保持） |
| Info | XSS 核查 | 通过（Vue 默认转义；dangerouslyUseHTMLString 仅拼接数字） |

## 结论
修复后重跑：39 例对比测试全过；端到端 383 字 → 8 句 → 8 提示词 → 16 图（1024×1024，133-310KB）成功。
