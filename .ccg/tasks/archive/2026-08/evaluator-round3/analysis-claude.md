# 评估器 Round3 分析 — Claude（含实测核验）

> 分析对象：video-prompt-engine 确定性评分器 `evaluator.py` 六项优化（zh/ru 长度兜底、CJK 单字词表、258 哨兵入库、正则缓存、镜头梯度、无 source 封顶拆解）。
> 方法：Claude 独立分析 + 在 258 语料 / golden 12 条上实跑模拟（`D:\Temp\probe_round3_*.py`），非纯推理。
> 基线：258 语料 mean 92.3 / ≥90:213 / ≥80:221 / <60:20 / missing_audio:25；golden MAE 15.77 / RMSE 18.52 / r 0.915。
> 关键结构性事实：golden MAE 中 58% 来自 5 条短卡/俄语样本偏低（Δ=-20~-32），仅 42% 来自封顶样本偏高（Δ=+5.8~+18.6）——任何动 fidelity 20 分的方案同时影响两端，这是第 6 项的核心约束。

---

## 1. zh/ru 字符刻度长度兜底（detect_tier）

**推荐方案：联动 batch 上界 2000，阈值 = `len(prompt) > 2000` → refined。**

- `detect_tier`（evaluator.py:583）增 `language: str = "en"` 参数（仅 evaluate 一处生产调用 + 测试，向后兼容默认）；en 词数兜底拆为双语：
  ```python
  if language in ("zh", "ru"):
      if len(str(prompt)) > 2000: return "refined"
  elif count_words(prompt) > _batch_hi(max_length): return "refined"
  ```
- 阈值必须联动、不可独立：zh/ru batch 带上界就是 2000（evaluator.py:686）。独立取值必然产生「batch 带内却判 refined」或「超 batch 上界却判 batch → 长度双亏」的重叠/缺口（重蹈 P1-2 消除的 500-833 双亏区）。
- 三处同步并入：`length_fallback`（evaluator.py:653-662）、`checks["tier_auto"]="length"`、**`trailer_waiver`**（否则 3000 字中文无 trailer → 转 refined 后 `missing_trailer=-10` 误伤，净效应为负）。
- **必须耦合修**：refined 层 `missing_audio` 检查（evaluator.py:797 计分、:788 附近判定）只认拉丁 sfx/sound/audio/music/score，无 zh/ru 音频意图词。5 条 zh 语料转 refined 后，真正的「音效/环境声/雨声」无法满足 has_audio → 恒 -5。补 zh 音频词 + ru 音频词（звук/музыка/речь/голос/диалог）并入 refined 分支。

**实测影响**：5 条 zh 样本（2743-5713 字）当前全判 batch、长度 0 分；修复后仅 1 条（2743）进 refined 带得 20 分（+7.9），其余 4 条仍超 refined 上界 5000 → 维持 0 分。golden 零影响（唯一 ru 样本显式 asset）。net mean 变化 ≈ +0.1。

**风险**：(1) 不改 refined missing_audio → 中文精修音频判定失效；(2) language 参数与正文语言不一致时仍走词数兜底（写入 docstring 约束）；(3) refined hi 固定 `max_length or 5000`，5200+ 字中文转 refined 后长度仍 0 分——残余边界记录。

**验收**：`detect_tier("…"*2500, {}, language="zh")=="refined"`；1900 字仍 batch；`tier_auto=="length"`；无 missing_trailer；中文精修带「音效/环境声」→ 无 missing_audio；258 复测 mean 漂移 ∈ [-1,+1]（预期 +0.1）、missing_audio 不增。

---

## 2. CJK 单字关键词误击修复

**推荐方案 A（词表扩充 + 移除单字），仅保留 subject 的 `人`（刻意例外）。**

实跑证伪「方案 B 单字上下文启发」：要素评分有 3 命中封顶（`min(1, hits/3)`，evaluator.py:905/931 附近），合成词 2-3 个就顶满；B 需为每个单字建邻字白名单，成本高且不可穷举，与代码库「显式词表而非启发」的既定哲学相悖。

实测 5 条 zh 语料单字命中真伪分布——大量单字命中是纯误击：

| 单字 | 真实命中 | 误击（本轮剔除） |
|---|---|---|
| 战 | — | 战术（战术挎包） |
| 立 | 站立 | 外立面/立体/独立 |
| 望 | 回望/眺望 | 绝望 |
| 持 | 手持 | 持续/保持 |
| 金 | 金色/铂金 | 金属 |
| 景 | 背景/前景 | 中景/远景（景别词） |
| 光 | 主光/光源/光线 | 曝光/时光 |
| 色 | 红色/配色 | 角色 |

**zh 词表 v2.1 条目**（5 条语料模拟：elements_score 0.778→0.722，max -1.4 分，损失全是误击剔除）：
- subject：保留 `人`（四人/每人/有人 真实主体，误击率低）+ 增 `人物/男人/女人/男子/少年/青年/老人`
- action：去全部单字（飞奔战走跑追舞骑立坐望持挥攻），增 `飞翔/飞行/飞奔/奔跑/战斗/作战/行走/走出/走近/走进/跑步/追逐/追赶/追捕/追上/舞蹈/跳舞/骑马/站立/站起/坐下/凝视/注视/遥望/眺望/手持/挥舞/挥动/攻击/进攻/飞溅/飞过`；**不放** `追踪/追拍`（镜头运动语义）
- environment：去 `室/城/景`，增 `室内/室外/城市/城堡/背景/前景/场景/景色/景观/夜景`（不放 中景/近景/远景）
- lighting：去 `光`，增 `光线/光源/灯光/阳光/月光/日光/烛光/火光/主光/暖光/冷光/白光/红光/蓝光/绿光/荧光/微光/亮光/发光/闪光/辉光/逆光/霓虹/光晕/光束`
- color：去 `色/灰/红/蓝/绿/金/黑/白`，增 `色彩/色调/颜色/配色/色温/灰色/灰白/银灰/红色/绯红/鲜红/暗红/血红/橙红/蓝色/湛蓝/深蓝/淡蓝/蔚蓝/绿色/翠绿/深绿/橄榄绿/金色/金黄/铂金/黑色/漆黑/墨黑/乌黑/白色/纯白/雪白/苍白/黑白`
- style：无单字，不动
- `"version": 2` → `3`（`_asset_fingerprint` 自动感知）

**风险**：合成词漏收 → 召回损失（动词多形态必须齐收：走出/走近/走过/飞过）；`load_element_keywords`（knowledge.py:373）强制 en/zh/ru 三语非空，去单字后 zh 列表非空即通过；round2 测试 `test_zh_words_keep_substring`（"室内灯光下，将军站着"）文本含 `室内`/`灯光`，v2.1 覆盖 → 不破（语义从「单字子串」变「合成词」）。

**验收**：反例测试 `角色/曝光/时光/金属/绝望` 不再命中 color/lighting/color/color/action；5 条 zh 语料逐条复测每要素命中为合成词；elements_score 回落 ≤0.06。**顺带可选小步**：en 短卡词表补 `demon/painting/illustration/orb/hellscape`（golden 短卡地板关键缺口，与第 6 项联动）。

---

## 3. 258 哨兵脚本入库

**推荐方案：`scripts/eval_corpus_258.py`（固定路径读 `video_prompt_engine/knowledge/seed_higgsfield_prompts.json`）+ 独立 CI step。**

- 读固定路径，不读 corpus_index.json（258 语料是种子文件、无 tier 字段、含 ru 样本；corpus_index.json 目前只有 2 条 demo，人口完全不同——「基线所测即所守」）。
- 与 retest_258.py 关键差异——**三路语言判定**（CJK→zh / Cyrillic→ru / else en）：现脚本只判 zh/en，3 条 ru 被当 en 按词数刻度评分（已知缺陷）；落地后同一脚本重测一次基线（预计 ≈92.3，聚合差 <0.1）。
- 指标：n / mean / median / ≥90 / ≥80 / <60 / missing_audio；`--json`；退出码 0=通过 / 1=门禁失败 / 2=输入错误。
- **门禁阈值先宽后紧**：round3 落地后重定基再收紧。首版落库带宽：`mean≥88.0`（基 92.3）、`ge90≥190`（基 213）、`lt60≤30`（基 20）、`missing_audio≤40`（基 25）。round3 的缩放封顶会合法地把 mean 拉到 ~90.5、ge90 ~205——必须先落库→复测→重定基→再收紧，否则门禁挡住自己的合法改动。
- CI：`.github/workflows/test.yml` 独立 step（`timeout-minutes: 10`），**不进现有 pytest 命令**（现有 job timeout 5 分钟，258×evaluate ≈2-4 分钟会顶爆超时）。

**风险**：语料文件被误改 → 基线漂移（门禁脚本硬断言 `total items==258`）；阈值带宽过窄干扰合法重构 / 过宽守不住回归；CI 平台差异（`Path(__file__).resolve().parent.parent` 定位根目录，禁相对路径）。

**验收**：注入回归（临时 elements 恒 0）→ exit 1，恢复 → exit 0；`--json` 风格与 golden 脚本一致；CI 冒烟记录 wall-time。

---

## 4. 正则缓存

**推荐方案：`functools.lru_cache(maxsize=2048)` 包 `_WORD_BOUNDARY_RE`（evaluator.py:38）与 `_CYRILLIC_BOUNDARY_RE`（evaluator.py:46）两个工厂函数。**

- 缓存键只有 `token`（str）——hashable、线程安全（lru_cache 内部有锁）；**不要**把 flags 做成参数（两函数固定 IGNORECASE，调用点统一）。
- **maxsize 必须设上限**：token 空间 = element_keywords（~200 固定）+ gated lock 词（固定）+ 跨镜承接/角色名（**动态，来自源文本，服务长驻时无界**）。2048 LRU 淘汰防内存膨胀；淘汰后重编译，正确性不变。
- 返回值 `re.Pattern` 只被 `.search/.finditer` 调用、无 mutation，缓存安全。
- 热路径收益：`_contains_word` + `_token_occurrences` + 元素循环 + 跨镜保真共用同一缓存，一次 evaluate 减少数百次 `re.compile`（当前 258 复测 ~2 分钟主因之一）。

**风险**：零分数影响；唯一注意 `@lru_cache` 不要加在带非 str 参数的函数上。

**验收**：预热后 `_WORD_BOUNDARY_RE.cache_info().hits > 0`；两次 evaluate 后 `currsize` 不无限增长；258 复测四指标逐一相等（bit-identical）。

---

## 5. 镜头梯度（has_shot 分档）

**推荐方案：本轮只落 `checks.shot_types/camera_types/motion_types` 输出（零分数影响）；分数梯度缓行，若必须落地用「缺失惩罚 0/20/20」而非 0/10/20。**

实测（258 语料，已隔离 fidelity）：shot 0/1/2+ 型 = 23/11/224；cam = 21/14/223；mot = 34/24/200；**5 条样本 `has_shot=True` 但 0 个景别型**（只写 `CUT 1/CUT 2/[SHOT` 结构标记，无 wide/close-up）。

**0/10/20 全梯度 → golden MAE 明确变差**（15.77→16.46）：`hg-assets-003`（human 82, engine 82.0，校准正中的唯一样本）只有 1 个景别型（"Shot on Arri"/static）→ 20 被砍到 10 → Δ 0→-8.4。golden 太小，1 条样本翻转就是 -0.7 MAE；258 无人工标签无法证伪梯度「更准」，只能看到重分布。

**推荐映射**：
- 本轮：`checks["shot_types"]=[distinct 景别型]` + `checks["shot_type_count"]`；`has_shot` 计分不变。
- 若坚持改分：`0/20/20`（0 型且有 shot 结构词 → 10；≥1 型 → 20）——只惩罚「说 shot 但说不出景别」的 5 条，golden 零影响，258 mean 仅 -0.16。
- 判定词表（保守、避泛词）：wide（wide/establishing/panoramic/aerial/全景/远景）、medium（medium/mid/中景）、closeup（close-up/macro/insert/特写/近景/微距）、overhead（overhead/top-down/aerial/俯拍/航拍）、lowangle（low-angle/worm's eye/仰拍/低机位）、tracking（tracking/dolly/follow/跟拍/推移）、static（static shot/locked-off/固定机位/静止镜头）。**禁用裸 `still`/`wide`/`extreme`/`摇`**（still 命中 "still alive"、extreme 命中 "extreme wide"、摇 命中 摇晃）。**运镜型归 has_motion 不归 has_shot**（pan/tilt/tracking/zoom/crane/handheld/slomo/rotate/drift 进 MOT_CATS），消除现行 has_shot 混入运镜词的语义重叠。

**has_camera/has_motion 分档**：本轮同样只出 instrumentation——数据上 cam/mot 梯度 258 影响小（-0.29/-0.48），但 golden `hg-credits-016`（"no rotation" 否定句）说明分档必须**否定感知**，否则 `no rotate` 假计一档。

**风险**：词表歧义（still/wide/extreme）是最大回归面；分档必须与 video meta（`video.shot/camera/motion_intensity`）结构化字段合并判定，否则精修生产路径（meta 有值）与纯文本评测路径（meta 空）分档结果不一致；**golden 复测是硬约束：任何分档方案 golden MAE 不得高于 15.77**。

**验收**：`"wide close-up of a man"` → shot_types==["wide","closeup"]、count 2；`"a shot of a cat"` → count 0 但 has_shot=True（结构词）；`"no rotation"` → mot_types 不含 rotate；instrumentation 版 golden MAE==15.77。

---

## 6. 封顶拆解（无 source 时 fidelity 白送 20 分）

**推荐方案：方案 B 收敛版——无 source 时 ceiling = `90 + 7*elements_score`（≤97）；有 source 时 ceiling 仍 100。**

```python
score = (length_points + elements_score*30 + shot + cam + mot + fidelity*20) / 1.2 + sum(violations.values())
if not source_prompt:                       # 无源：保真不可验证，封顶随要素覆盖度缩放
    score = min(score, 90 + 7 * checks["elements_score"])
return {"score": round(max(0, min(100, score)), 1), ...}
```

**为什么不是 A/C**（全部实测）：把 fidelity 20 转为「信息丰富度」（A1=elements_score、A2=0.5elem+0.5shot）或重分配到镜头/要素（C）都**破坏短卡地板**——短卡正是靠免费 20 分才没跌到 20 分档。三案 golden MAE 分别恶化到 **18.78 / 20.43 / 19.83**。只有「压缩天花板」能不动地板：纯 cap 97 → MAE 15.08（258 mean 92.2→90.8）；缩放 cap → **MAE ≈14.85**，且 7 条封顶样本恢复区分（95.8 / 96.2 / 96.2 / 96.6 / 96.6 / 96.6 / 97）——纯 cap 97 会把 6 条全压到 97，反而不区分。

语义立论：`100` 保留给「source 保真已验证」的独占空间；无 source 最高 97，越接近 97 越需要要素全覆盖。

**258 影响**（实测，含 items1+2+5 全梯度上限即最坏情形）：mean 92.3→89.6、ge90 213→207、lt60 20→25、missing_audio 25→25。推荐组合（item5 只
instrumentation 实际回落更小（mean ~90.5、ge90 ~210）。

**风险**：(1) 258 哨兵落地后需重定基（mean 基线下移 ~1.5-2.7 是设计意图，非回归）；(2) `elements_score` 双重使用（主公式 + ceiling 缩放）——若未来 elements 权重调整 ceiling 自动跟随，语义自洽但需 docstring 注明；(3) 短卡地板（Δ=-20~-32 的 5 条）**本项不解决**——需要 en 词表扩充（第 2 项顺带）与 asset/variant 层镜头权重的 tier-aware 化，作为 round4 主题记录。

**验收**：硬门禁 MAE ≤ 15.77（现基）；7 条封顶样本 engine 分**两两不等**；4 条短卡分数**不低于现值**（地板不塌）；快照断言 `hg-scene_74-020`（human 86, elem 1.0）→ ≤97、`hg-scene_74-011`（human 90, elem 0.833）→ ≤95.8；带 source 保真 1.0 样本 → 仍可到 100。

---

## 实施顺序建议

```
批次 A（零分数影响，可并行，互不依赖）：
  ├─ item 4  正则缓存          —— 先做，提速后续所有复测（258 复测 ~2min→数十秒）
  ├─ item 3  哨兵脚本入库       —— 落当前基线 92.3/213/20/25（宽带宽），作为回退锚点
  └─ item 5  仅 instrumentation —— checks.shot_types 输出，不改分

批次 B（分数微调，依赖 258/golden 复测，可并行）：
  ├─ item 2  zh v2.1 词表       —— 258 影响 -0.03，golden 零影响
  └─ item 1  zh/ru 长度兜底     —— 与 refined missing_audio 中文词修正耦合；golden 零影响

批次 C（分数调整，依赖批次 B 后的 golden 复测 + 哨兵重定基）：
  └─ item 6  无 source 缩放封顶 —— golden MAE 15.77→~14.85；落地后重定基哨兵
```

**依赖关系**：item 1/2 相互独立但都改变 258 分数 → 同在批次 B；item 6 依赖 item 3 基线捕获（否则无法区分「设计改动」与「回归」）；item 5 分数梯度依赖一个更大的带人工标签样本集——golden 12 条不足以证伪（1 条样本翻转即 -0.7 MAE），本轮不做分数切换，仅留 instrumentation 供 round4 数据驱动决策。

**跨项总验收口径**：全部落地后 258 四指标（重定基后）与 golden（MAE ≤ 15.77 且封顶样本两两可分）双绿；`evaluator_version` 由 v0.11-deterministic 升 v0.12，词表变更随 `_asset_fingerprint` 自动反映。
