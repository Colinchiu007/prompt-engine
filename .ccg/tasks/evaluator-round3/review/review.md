# 评估器 round3 评审（2026-08-16）

## 评审方式
- 双模型并行评审（CCG M+ 要求）：antigravity + Claude。
- **antigravity 降级记录**：真实任务执行失败（`not currently available in your location`，AGY_EXIT=1，与历史地区/账号限制一致）；本轮以 Claude 单模型评审为准。
- Claude 评审方法：读取完整 diff（1443 行）→ 逐文件核对 → 实跑验证（round3 33 项 + 定向回归 297 项 + 全量 947 项 + 258 哨兵 + golden 全部复现）→ 4 个边界探针脚本（probe_corpus/probe_neg/probe_edge/probe_audio，评审后已清理）。

## 结论
**条件通过（conditional approve）**：未发现分数正确性致命 bug；关键校准数字逐一复现。1 Critical + 6 Warning + 9 Info。

## Critical（已修复）
- C1 `test.yml` job 级 `timeout-minutes:5` 罩死哨兵 step 的 10 分钟上限 → job 超时提到 15 分钟，注释同步。

## Warning（已修复 6/6）
- W1 `_type_token_negated` 任一否定即整体抑制 → 删除 `_TYPE_NEGATION_RE`，复用 `_occurrence_is_negated` 分句全出现语义（与 `_negated` 一致）。
- W2 zh action 高频形态召回回退（走着/跑来/挥手/望着/坐着/看着）→ 词表 v3→v4 补 11 词（JSON + knowledge.py fallback 同步）。
- W3 refined 音频意图词漏 en dialogue/voiceover/narration/vocal → refined/batch 统一 `_AUDIO_INTENT_WORDS` 单表（补 zh 环境声/雨声/风声/枪声 + ru 词）。
- W4 `/v1/video/evaluate` 默认 language=en 使 zh 兜底成死代码 → `VideoEvaluateRequest.language` 默认 None，逐条 `detect_lang` 自动判定（共享 util，与哨兵同口径）。
- W5 `language.startswith("zh")` 大小写/变体分裂 → `evaluate()`/`detect_tier()` 入口归一化 `str(language or "en").lower()[:2]`，docstring 修正。
- W6 zh/ru 阈值「联动」实为两个独立 2000 → `_CHAR_BATCH_HI=2000` 常量，detect_tier/length_fallback/batch 分带三处共用。

## Info（已处理 9/9）
- I1 哨兵输入损坏补 `ValueError` 捕获返回 2；I2 封顶测试改真实绑定断言（elements_score=5/6 → score==cap=95.8）；I3 短卡地板改 4 条 golden 快照断言（43.1/44.4/55.6/39.7，按样本声明 tier）；I4 cam_position 去裸 view；I5/I6 文档措辞同步（裸 wide/aerial 保留、tracking/dolly 双属特例）；I7 proposal Impact 补图片引擎共享词表影响；I8 否定覆盖范围 docstring 注明（由分句化取代）；I9 JSON 末尾换行补齐。

## 回归证据（修复后）
- 全量 pytest：**954 passed**（947 基线 + 7 新增评审回归用例，FULL_EXIT=0）。
- golden：MAE **14.85** / RMSE 17.92 / Pearson r **0.920**（与重定基一致，零回归）。
- 258 哨兵：n=258 mean=91.0 ge90=216 ge80=225 lt60=20 missing_audio=20（与重定基一致，零回归）。
