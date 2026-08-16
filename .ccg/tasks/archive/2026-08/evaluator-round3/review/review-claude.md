[codeagent-wrapper]
  Backend: claude
  Command: claude -p --dangerously-skip-permissions --setting-sources  --output-format stream-json --verbose -
  PID: 31580
  Log: D:\Temp\codeagent-wrapper-31580.log
  Web UI: http://localhost:58027
  Session-ID: 768f0060-02fd-4c6e-ab4d-4394e537aec5
All verification complete. I've cleaned up my probe files. Let me compile the review.

---

# 评审报告：评估器 round3（`codex/evaluator-round3` @ 71bfaa7）

**评审方法**：读取完整 diff（1443 行）→ 逐文件核对实现 → 实跑验证（round3 测试 33 passed、定向回归 297 passed、全量 947 passed；258 哨兵复现 `mean=91.0 ge90=216 ge80=225 lt60=20 missing_audio=20`；golden 复现 `MAE=14.85 RMSE=17.92 r=0.92`，与设计文档声称值逐一吻合）→ 构造边界探针验证推理。

总体：**实现质量高、校准数字可复现、测试覆盖认真**。未发现分数正确性的致命 bug。但有 **1 个 Critical（CI 超时结构失效）**、6 个 Warning（多为 instrumentation / 集成边界）、若干 Info。

---

## Critical 🔴

### C1. `.github/workflows/test.yml:13,38-42` — 哨兵 step 的 10 分钟超时被 job 级 5 分钟超时罩死，CI 很可能被打爆
- **描述**：`test` job 级 `timeout-minutes: 5`（第 13 行），新增的 "Corpus 258 sentinel gate" step 带 `timeout-minutes: 10`（第 42 行）。GitHub Actions 中 **step 超时上限被 job 超时截断**——整个 job 5 分钟被杀，step 的 10 分钟形同虚设。本机实测：全量 pytest **288s（4:48）**、哨兵 **51s**，两者相加已 339s，还不算 checkout/setup/pip install（`git+shared-models` + `-e .[all]`）。设计文档自己写「进 5 分钟 pytest job 会顶爆超时」——但最终实现恰恰把它放进了同一个 5 分钟 job。
- **修复建议**：把哨兵拆成独立 job（`needs: test`，自带 `timeout-minutes: 10`），或将 job 级超时提到 15 分钟；二选一，注释同步更正。这是本轮唯一会直接造成 CI 门禁误杀（而非漏杀）的缺陷。

---

## Warning 🟡

### W1. `video_prompt_engine/evaluator.py:115-119` — 分型否定「任一否定即整体抑制」，混合语境下漏报整个类型
- **描述**：`_type_token_negated` 对拉丁词走 `_TYPE_NEGATION_RE(token).search(text)`，只要文本**任意一处**出现 `no/without/never + token` 就抑制该类型。实测 `"tracking shot, but no tracking in the second half"` → `shot_types=[]`、`motion_types=[]`，尽管前半句有正向 `tracking shot`。这与既有 `_negated`（evaluator.py:456-461）的「**所有**出现均被否定才算否定」语义不一致（同一文本 `_negated("tracking")==False`）。当前零分数影响，但 round4 若用它驱动分档，混合语料会系统性少计。
- **修复建议**：要么按分句限定否定作用域（复用 `_occurrence_is_negated` 的分句切分），要么改为与 `_negated` 一致的全出现语义；至少在 docstring 注明该粗粒度限制。

### W2. `prompt_engine_core/knowledge/element_keywords.json` + `knowledge.py:169-202` — zh action 常见形态召回相对 v2 回退
- **描述**：设计原则「动词多形态必须齐收（走出/走近/走过/飞过）」，但 v3 实际只收原型。v2 单字（走/跑/挥/望/坐/追…）能被子串捕获的 **走着/跑来/挥手/望着/坐着/看着** 等在 v3 全部落空（实测 `"将军走着"` → action `False`、`"小孩跑来"` → `False`）。对「站着」无影响（v2 也没有「站」），但走/跑/挥/望/坐系确属回退。elements_score 只依赖命中数，动作形态漏收会拉低 258 中动作型样本的要素分。
- **修复建议**：补 `走着/走起/走来/跑去/跑来/挥手/望着/坐着/看着/站定/站立(已有)` 等高频形态；或接受该召回损失并写进 design 的「已知损失」清单（当前文档声称已齐收，与实际不符）。

### W3. `video_prompt_engine/evaluator.py:875-885` — refined 音频意图词修复只补了 zh/ru，英文 dialogue/voiceover/narration/vocal 仍漏
- **描述**：round3 重写了 refined 分支的音频词表，新增 zh/ru 词，但拉丁部分仍是 `sfx/sound/audio/music/score` 五词。实测 refined 下 `"A cinematic shot with dialogue"` → `missing_audio=True`（-5）。而 batch 分支的 `_AUDIO_INTENT_WORDS`（861-865 行）含 `dialogue/vocal/voiceover/narration`——同一词在 batch 认、在 refined 不认。这是**前置缺陷**，但 round3 恰好重写了这行却未顺带统一，设计文档「中文长精修不再恒 -5」易让人误以为音频判定已完整。
- **修复建议**：refined 分支直接复用 `_AUDIO_INTENT_WORDS` 并追加 ru 词，消除双表漂移（`_AUDIO_INTENT_WORDS` 本身已含大部分 zh 词，可进一步与 refined zh 词合并去重）。

### W4. `video_prompt_engine/models.py:199` + `evaluator.py:675-679` — `/v1/video/evaluate` 默认 `language="en"`，中文提示词走默认参数时 P0-1 兜底完全不生效
- **描述**：`VideoEvaluateRequest.language` 默认 `"en"`。客户端 POST 中文文本不传 language → `evaluate` 走词数兜底（中文 `count_words≈1`）→ 仍判 batch、长度 0 分。实测 `evaluate("中"*2500, {}, "", "en")` → `tier=batch`。哨兵脚本用 `detect_lang` 自动三路判定，而 API 依赖客户端显式声明，两条评测路径口径不一致，P0-1 的「长中文不再恒判 batch」在默认 API 路径是**死代码**。
- **修复建议**：API 层在 `language` 未显式提供时用与哨兵相同的 `detect_lang` 自动判定（抽共享 util），或将此约束写进 API 文档/模型字段描述，避免「修了但没生效」的假象。

### W5. `video_prompt_engine/evaluator.py:675,746,756,766` — language 匹配大小写敏感且与 advice 口径不一致
- **描述**：`language in ("zh","ru")` 是精确匹配。传入 `"ZH"`/`"zh-CN"`/`"Ru"` 会**静默**走 en 路径（实测 `detect_tier("中"*2500, {}, language="ZH")=="batch"`），而 `_build_advice`（1133 行）用 `.lower().startswith("zh")` 又把它当中文出「长度 X 字」文案——同一请求长度口径与文案口径分裂。`detect_tier` docstring 写的「不一致时回退词数兜底」也**未实现**（zh 分支无条件走字符刻度）。
- **修复建议**：`evaluate` 入口归一化一次 `language = str(language or "en").lower()[:2]`（或映射 `zh-CN→zh`），再供 detect_tier/measure/bands/advice 共用；修正 docstring。

### W6. `video_prompt_engine/evaluator.py:676` vs `:774` — zh/ru 兜底阈值「联动」实际是两个独立硬编码 2000
- **描述**：设计强调「阈值必须联动、不可独立」，en 侧 round2 做了 `_batch_hi` 单一来源（653-655），但 zh/ru 侧 detect_tier 的 `>2000` 与 batch 带上界 `120,2000` 是两个**独立字面量**。当前值巧合一致所以无重叠/缺口；将来任何一处改动即重蹈「batch 带内却判 refined / 超上界却判 batch」双亏区。
- **修复建议**：抽 `_ZH_BATCH_HI = 2000` 常量（或 `_char_batch_hi(language)`），detect_tier、length 分带、length_fallback 三处共用。

---

## Info 🟢

### I1. `scripts/eval_corpus_258.py:96-102` — 输入错误只捕获 `OSError`
`json.JSONDecodeError`（`ValueError` 子类）与 `UnicodeDecodeError` 不在捕获范围 → 语料损坏时未捕获 traceback、退出码 1（门禁失败语义）而非文档承诺的 2（输入错误）。建议 `except (OSError, ValueError, UnicodeDecodeError) → return 2`。

### I2. `tests/test_evaluator_p0p2_round3.py:209-216` — `test_scaled_cap_below_97` 注释与实际不符
注释称 `elements_score=0.833`，但该 prompt 实测约 `0.278`，cap≈91.9 而原始分≈81.9，**断言未真正触达缩放封顶**（只是恒真不等式）。建议改用能达 5/6 要素（0.833）的 prompt，使 `score == cap` 得以验证。

### I3. `tests/test_evaluator_p0p2_round3.py:224-228` — `test_short_card_not_artificially_lowered` 空转
`score >= 0` 与 `score <= cap` 恒真，没有钉住设计声称的地板值（43.1/44.4/55.6/39.7）。「短卡地板不塌」是 P2-1 的核心保证，建议加 4 条快照断言（`assert score == approx(43.1, abs=0.1)`），否则未来权重调整无回归护栏。

### I4. `evaluator.py:91-94` — `cam_position` 收 `view/angle/camera` 泛词
实测 `"a beautiful view of the city"` → `camera_types=["cam_position"]`。与「保守、避泛词」的设计声明相悖（`still/wide/extreme` 都禁了，`view/angle` 反而保留）。instrumentation-only 尚可，round4 用前建议收窄。

### I5. `analysis-claude.md`/`design.md` 与实现矛盾：声称「禁用裸 wide」但 `_SHOT_TYPE_WORDS["wide"]` 含裸 `"wide"`，且测试依赖它
设计文档两处文字与实现不一致（实现保留了 `wide`，也保留 `aerial`）。不是代码 bug，但评审依据文档判实现会误判，建议同步文档措辞。

### I6. `evaluator.py:88` vs `:98` — `tracking/dolly/跟拍/推移` 同时出现在 `shot_types` 与 `motion_types`
spec.md 声称「运镜型归 motion 不归 shot」，实现保留双侧（测试注释已承认是特例）。shot 与 motion 集合因此不互斥，round4 交叉分析时需注意去重。

### I7. 共享资产跨界：`prompt_engine/evaluator.py:282`（图片引擎）同样消费 `element_keywords.json`
zh 词表 v3 去单字会**静默改变图片引擎**的中文要素分（对图片引擎既消误击也损召回）。round3 Impact 只列了视频侧文件，未提图片引擎行为变更。建议在 proposal 的 Impact 补一行，并跑图片侧 golden 复测确认无回归（本轮全量 947 测试已含图片侧，未破，属风险提示而非缺陷）。

### I8. `evaluator.py:68-77` — `_TYPE_NEGATION_RE` 只认 `no/without/never`（CJK 只认 无/不/没有）
`"avoid rotation"`、`"no, rotation"`、`"无需推近"`、`"不要摇镜"` 均不抑制（已实测）。与既有 `_NEGATION_RE`（429-432，含 avoid/nobody/do not/out of…）相比词面偏窄。instrumentation-only 可接受，建议 docstring 注明覆盖范围。

### I9. `prompt_engine_core/knowledge/element_keywords.json` 文件尾丢失换行
diff 显示 `\ No newline at end of file`，纯风格项，顺手补回即可。

---

## 总体结论

**条件通过（conditional approve）——需先处理 C1。**

- **正确性**：未发现会直接算错分数的缺陷；round3 的六项改动行为均与设计文档一致，且关键校准数字（258 四指标、golden MAE/RMSE/r、7 条封顶样本分布 95.8–97.0、短卡地板不塌）经我实跑**逐一复现**。正则缓存（P1-1）确为 bit-identical；instrumentation（P1-2）确认零分数影响。
- **集成风险**：C1（CI job 超时）是唯一可能直接打挂流水线的问题，必须修。W4/W5（API 默认 language、大小写敏感）会让 zh/ru 兜底在部分调用路径静默失效，属「修了但没生效」类问题，建议本轮一并处理。I7（共享词表影响图片引擎）建议在 Impact 中显式声明。
- **测试**：round3 新增 33 条用例覆盖了主路径与反例，质量高；但 I2/I3 两处「封顶/地板」关键保证的测试断言偏弱，建议补快照。
- **文档/实现不一致**：I5（禁用裸 wide）、I6（运镜归 motion）、W6（阈值联动）三处文档与代码存在出入，建议以代码为准修订文档，或在 design 中标注偏离。

按 Critical / Warning / Info 排序，**Critical 1 项、Warning 6 项、Info 9 项**。C1 修复后即可合并。

---
SESSION_ID: 768f0060-02fd-4c6e-ab4d-4394e537aec5
CLAUDE_EXIT=0
