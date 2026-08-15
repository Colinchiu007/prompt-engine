# 评审记录：evaluator-p0p2-round2（Claude 双模型评审 + 修复闭环）

日期：2026-08-16
评审对象：branch codex/evaluator-p0p2-round2（基于已合并 PR #54 0a914ac 的 P0-P2 深水区增量）
评审输入：.ccg/tasks/evaluator-p0p2-round2/claude-review-input.txt + review-diff.txt
评审模型：Claude（antigravity 不可用已记录降级）

## 评审结论：request changes（1 Critical + 4 Major + 6 Minor）

### 🔴 Critical
- **[ABSENT] 豁免对 character_list 角色不生效，原测试假绿**：`_strip_reference_markers`/`_extract_absent_names`
  只用 reference_names（excluded+swap），不含 continuity roster；`<<<[ABSENT] Roko>>>` 整段剥离后角色名不在正文
  → 仍触发 continuity_break；旧测试恰因「标记残留→角色在场」通过，测的是泄漏不是豁免。
  **修复**：known_names 并集（含 character_list）提前构建，剥离与识别共用；拉丁后随边界 + 同位置长名覆盖去重；
  补真测试（`<<<[ABSENT] Roko>>>`+roster 断言无 continuity_break + 对照组无标记仍判 break）。

### 🟡 Major
1. **_cross_lingual_fidelity 单向**：en→zh 方向 conserved/kept 恒≈0 只剩长度比。
   **修复**：要素守恒与镜头结构按 zh→en/en→zh 双向配对计分（(zh_src&en_dst) or (en_src&zh_dst)）。
2. **_ASSET_FP_CACHE 无锁+原地填充**：并发首波可读半空 dict。
   **修复**：先构建局部 dict 再原子赋值（GIL 下发布原子）。
3. **_CJK_NAME_FOLLOW_OK 含常用名字尾字**（山/海/雪/河/湖/水/岸/草/花/天/空/地）：`林晓山` 误判命中。
   **修复**：剔除名字尾字，收窄为纯功能字；「仍」（贾克斯仍）保留，「雪地」走泛词路径不受影响。
4. **_extract_absent_names 无后边界**：前缀名连带判缺席（`[ABSENT] 王芳雨` 把王芳判缺席）。
   **修复**：拉丁名后随边界 + 长名位置覆盖去重（同 Critical 修复一并落地）。

### 🟢 Minor
- RU 子串误击：фон⊂телефон/микрофон → environment 假命中。**修复**：西里尔左侧词边界（右侧容忍变格）。
- _build_advice 长度文案按词数、RU 长度带按字符——口径混用。**修复**：char_scale=zh or ru，RU 输出 chars 文案。
- 空输入契约 checks 形状与正常路径不一致 + advice 硬编码中文。**修复**：形状对齐 + advice 按 language。
- tie-break 注释断言不符（1×-10 与 2×-5 在 sum(abs) 下并列）。**修复**：注释修正。
- variant 长度上界内联复制 _batch_hi 公式。**修复**：复用 _batch_hi。
- _check_continuity 白名单 len(w)<2 分支死代码。**修复**：移除（宁漏勿误）。
- _gated_lock 惰性创建锁理论竞态。**修复**：模块级直建。
- rest.py:180 过期注释 v0.10→v0.11。**修复**：更新（CRLF 字节级保留）。

## 修复后验证
- round2 专用：36 → **42 用例全过**（新增 6：en→zh 保真 / ABSENT 括号豁免 / 3 条提取单测 / RU 词边界）
- 相关套件：test_evaluator_p0p2 / test_evaluator / test_higgsfield_p0 / test_eval_fixes / test_image_higgsfield_alignment = 167 passed
- 全量回归：**938 passed / 3 skipped**（web E2E 5 条需本机 8094 服务，环境问题与改动无关）
- golden 复测：MAE 15.77 / RMSE 18.52 / Pearson r 0.915（门禁 MAE≤18 / r≥0.90 通过）
- 258 语料复测：mean 92.3 / median 98.6 / ≥90 213 / ≥80 221 / missing_audio 25（哨兵通过）
- 结论：评审问题全量修复，与修复前分数分布零漂移