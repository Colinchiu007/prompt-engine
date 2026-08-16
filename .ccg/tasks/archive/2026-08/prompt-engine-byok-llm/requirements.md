# 交接备注：MiniMax 换 Key 后 optimize 仍报额度（2026-08-16，来自 fix-minimax-quota-stale-key）

> 外部诊断会话 2026-08-16 核验真实用户数据后追加，供 BYOK 实现/验证对照；不是本 change 的需求文件。

## 现象
桌面「模型设置」10:49 更新 minimax-multimodal 新套餐 Key，流水线 optimize（提示词优化）仍报 402 insufficient_balance_error（Token Plan 用量上限）→ 前端 story2video.quota_exceeded。

## 根因（与 BYOK 直接相关）
8013 的 LLM Key 来自引擎侧 config.yaml/.env（MINIMAX_API_KEY）兜底，与桌面 model_providers 是两套独立凭据；桌面改 Key 不影响引擎兜底 → BYOK 之前会一直复用陈旧/过期 Key。

## 硬证据时间线（profile: D:\tmp\Multi-Publish-debug-profile）
- 2026-08-16 10:49:19 minimax-multimodal updated_at（新 Key 已入库，api_key_enc 存在）
- 10:58 listVoices success / 11:47:38 testConnection success / 11:50:47 generateImage success（桌面 manager 侧新 Key 可用）
- 11:43 / 11:46 / 11:48 三次运行全部失败在 stage=optimize (3/7)：
  Error code: 402 - {'type': 'error', 'error': {'type': 'insufficient_balance_error', 'message': '当前已达到 Token Plan 用量上限…', 'http_code': '402'}, 'request_id': '06d0…'}
- D:\Data\projects\prompt-engine\.env mtime=2026-07-19（LLM_PROVIDER=minimax / MiniMax-M3），未随桌面设置更新

## 对 BYOK 实现的验证建议
- 断言：桌面携带 llm 对象后 /v1/optimize 的 LLM 调用必须使用请求内 key（request_id 应对上桌面设置账号），而非 config 兜底；key_source 应为 caller 来源。
- 422 fail-closed 生效后，未带 llm 的调用会被引擎直接拦截；与桌面侧 change 需成对发布，避免中间态回归。
- 旧 Key 时引擎曾返回 402 insufficient_balance_error（type/error/message/http_code/request_id 形状），可与 BYOK 后成功/失败形状对照。
