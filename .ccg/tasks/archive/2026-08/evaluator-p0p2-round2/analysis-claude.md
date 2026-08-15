[codeagent-wrapper]
  Backend: claude
  Command: claude -p --dangerously-skip-permissions --setting-sources  --output-format stream-json --verbose -
  PID: 28244
  Log: D:\Temp\codeagent-wrapper-28244.log
  Web UI: http://localhost:63530
  Session-ID: 21e4f1d8-fc06-4a48-b2d4-9582b3710741
分析完成。我通读了 `evaluator.py`（852 行）、`golden_set.json`、`element_keywords.json`、`knowledge.py`，并实测核验了所有待评估方案的核心断言（中文子串误击、跨语言 fidelity=0、red/cat 子串误击、500-833 双亏区、空输入、golden 12 条逐条分数构成）。以下是完整分析。

---

# 评估器 P0-P2 深水区优化方案分析

## 结论先行（按 ROI×风险排序）

| 批次 | 方案 | 判定 | 一句话理由 |
|---|---|---|---|
| **A 立即做**（不改变分数分布） | P0-2 中文词边界 | 高可行/高价值 | 实测 `林晓` 命中 `林晓雨站在门口` 并误扣 -10，修正不改变正常分数 |
| | P0-3 违规量化 | 高可行/中价值 | 以**并行 `violations_detail`** 落地，`violations` 保持 `dict[str,int]`，否则 ≈40 处测试断言全炸 |
| | P1-3 版本指纹 | 高可行/低风险 | 纯增量字段，rest.py:181 已有 `v0.10-deterministic` 先例 |
| | P1-4 select_best_detailed | 高可行/低风险 | 纯增量，候选信息已在 evaluate() 内计算 |
| | P2-1（advice 排序 + 空输入契约） | 高可行/低风险 | 空输入实测返回 16.7 分，无显式契约 |
| **B 校准性改动**（改变分数分布，需 258+golden 双复测） | P0-1 跨语言保真 | 中可行/中价值 | 解决 coverage 缺口而非校准缺口；golden 无 zh→en 样本 |
| | P1-2 阈值单一来源 | 中可行/需联动 | 实测 600 词改判 refined 后 **score 反而更低**（56.3→53.0），必须与 trailer 豁免联动 |
| | P2-1 元素 TF-IDF 扩表 | 中可行/高价值 | RU 缺口正是 golden ru 样本 -38.7 的根因，但需人工审校防稀释 |
| | P1-1 六要素词边界 | **低可行/高风险** | 全面词边界会误杀中文单字词与 man/human 类后缀，建议手术式去噪 |
| **C 暂缓** | P0-4 权重校准 | 中可行/被阻塞 | 7/12 golden 样本封顶在 100，网格搜索只对 5 条非封顶样本生效 → 12 条上过拟合 |
| | P1-5 性能 | 中可行/需先 profile | regex→集合只对英文词边界有效；gated 否定感知仍需 regex |

---

## 第一部分：逐方案分析

### P0-2 中文词边界 — 高可行，建议立即做（A 批）

**可行性：高**（但实现必须区别于英文词边界，见下）

**问题定位**：`_contains_word`（evaluator.py:18-30）的边界正则 `(?<![A-Za-z0-9])...(?![A-Za-z0-9])` 只对拉丁字符有效。实测：excluded 角色 `"林晓"` 命中正文 `"林晓雨站在门口"` → `excluded_hits: ['林晓']` + `excluded_present: -10` 误扣。涉及路径：excluded（435）、swap（449）、continuity 角色名（230/239）、gated 规则（314/317）。

**关键陷阱（为什么不能照抄英文边界）**：中文无空格，名字后紧跟汉字是常态（"林晓**走**进房间"）。若给 CJK 也加 `(?![\u4e00-\u9fff])` 右边界，正常用法全部假阴性，且会连带打崩 `_CONTINUITY_ZH_POSTURE` 白名单（"他**站起**来"——"站起"前是汉字"他"）。

**具体实现建议**（到函数级）：
1. 新增 `_contains_name(text, token, known_names)`：在 `_contains_word` 匹配到 CJK token 的位置，检查该位置是否被**更长的已知名字**覆盖（`known_names` 是 excluded + swap + character_list 的并集，按长度降序）。若 text[i:i+len] 是某个更长名字的前缀 → 跳过（这是"林晓"⊂"林晓雨"场景）。普通"林晓走进"不受影响。
2. 调用侧区分两种语义：**角色名匹配**（excluded/swap/continuity names）走 `_contains_name`；**泛词匹配**（continuity posture 词、gated locks/forbidden）维持现状 `_contains_word`（英文边界 + CJK 子串）。不要对泛词加任何 CJK 边界。
3. 顺带把 `_token_occurrences`（139-148）的 pattern 构建抽成 `_WORD_BOUNDARY_RE(token)` 单一来源，避免 18-30/139-148 两处正则漂移。

**风险**：残留边界——不在任何名单里的更长名字（"林晓雨"未登记）仍会误击，属可接受残差；守卫过严会引入 continuity 假阴性。方向性风险：该改动会**减少**误扣 → 部分中文样本分数上行。

**测试策略**：`tests/test_evaluator_p0p2.py` 新增用例：excluded `"林晓"` vs 正文 `"林晓雨..."` → 不命中；正文 `"林晓走进..."` → 命中；excluded `"林晓"` + character_list 含 `"林晓雨"` → 不命中；中文 posture 词"他站起"仍命中（泛词路径不受影响）。

---

### P0-3 违规分级量化 — 高可行，但必须"并行结构"落地（A 批）

**可行性：高**，但有一个硬约束。

**兼容性核验**：`violations` 当前是 `dict[str, int]`，被下列位置消费：
- 测试断言值类型：`test_higgsfield_p0.py:246-248`、`test_cross_scene.py:96/114/159`、`test_refined_blocks.py:295/330/371`、`test_audio_layers.py:88/109`、`test_eval_fixes.py:14/38`、`test_video_evaluator_deterministic.py:39/70/97/122-124`、`test_image_higgsfield_alignment.py:118/151/158` 等 ≈40 处 `.get(key) == -N`；
- `score += sum(violations.values())`（evaluator.py:622）；
- rest.py:124-125 `sum((...).values())`、rest.py:163 直出 JSON；
- optimizer.py:340、select_best:715 `len(violations)`。

**若把 value 直接改成 dict，上述全部破坏。** 因此 P0-3 的正确形态是：

**具体实现建议**：
1. `violations: dict[str, int]` **保持不变**（计分与兼容面）。
2. 新增 `checks["violations_detail"]: dict[str, {"penalty": int, "count": int, "detail": ...}]`。计分仍走 `sum(violations.values())`，detail 只做观测。
3. `timing_break`：目前只记录"是否存在"（529 行 `violations["timing_break"] = -5`，且只记最大 diff 于 checks）。把循环（505-530）改为累计 `beat_count` 与 `max_diff`，写入 detail。
4. `block_coverage`：ratio 已在 checks（557），搬入 detail 即可。
5. `select_best`/optimizer 的 tie-break 由 `len(violations)`（违规类型数）升级为 `sum(abs(v) for v in violations.values())`（总惩罚量）。这是**行为变更**（同分决胜语义更合理：1 个 -10 比 2 个 -5 更差），但仅在真同分时触发，生产影响面极小。

**风险**：tie-break 语义变更可能翻转个别候选选择（score 相同场景）；API 响应新增嵌套字段（rest.py:163 直出，schema 向后兼容加键）。

**测试策略**：`test_violations_detail_shape`（含 timing_break count/max_diff、block_coverage ratio）；tie-break 用例：同分候选 A={excluded:-10} vs B={missing_audio:-5, timing_break:-5} → 新语义 B 胜（10 vs 10 平，按先出现），A={-10} vs B={-5,-5,-5}=15 → A 胜。断言 violations 顶层值仍为 int。

---

### P0-1 跨语言保真 — 中可行，解决 coverage 缺口而非校准缺口（B 批）

**问题核验**：中文 source → 英文 prompt 时 fidelity 恒 0（实测忠实翻译 `fidelity: 0.0`）。根因在 evaluator.py:601-604：中文路径用 `c in str(prompt)` 判 2-gram 块，英文 prompt 不含汉字 → 全 miss。

**可行性：中**。两个候选方案：
- **方案 A（双语实体对齐）**：目前 repo 没有人物/物件的双语词典。`element_keywords.json` 是唯一的 en/zh/ru 映射，且只覆盖 6 个粗粒度要素。用它做**要素级**跨语言保真：source 中文里出现某要素的中文词、prompt 英文里出现对应英文词 → 该要素"跨语言守恒"。优点：零新资产、即插即用。缺点：只有 6 维，且测的是"要素类别保留"而非语义保真——source `"一个人在沙漠"`、prompt `"A robot in the city"` 会因 subject/environment 都命中而判高保真。这是本质局限，需在文档中声明。
- **方案 B（翻译模式检测 + 结构保真）**：当 source 含 CJK 且 prompt 不含（或反之）→ 判定"翻译模式"，fidelity 改为 `0.5×要素跨语言守恒 + 0.3×镜头结构保留（shot/camera/motion 三维是否在 source 出现且在 prompt 出现）+ 0.2×长度比 min(src/prompt, prompt/src)`。结构维度不受双语词典限制，比纯要素更抗"换场景保要素"的欺骗。

**建议**：A+B 组合——A 是骨架，B 补结构。检测函数 `_detect_translation_mode(source, prompt)` 放 evaluator.py 顶部；新增 `_cross_lingual_fidelity(source, prompt)`（598-612 的并行分支）。

**风险**：跨语言 fidelity 计算可能**高估**（要素/结构粗匹配），把"忠实翻译"与"同题材乱写"的区分度做到中等，而非完全解决。**关键兼容性**：必须只在 `_detect_translation_mode` 为真时启用新路径，否则现有 en→en / zh→zh 保真路径被触碰。golden 12 条无 zh→en 样本 → 现有指标零变化。

**测试策略**：忠实翻译对（zh→en，保留全部要素+镜头）≥0.7；换场景对（人/城市→机器人/沙漠）≤0.4；en→en 路径回归不变。

---

### P0-4 权重校准 — 中可行，但被"封顶效应"阻塞（C 批）

**可行性：中**。网格搜索/线性回归本身简单（`length 20 / elements 30 / shot 20 / camera 15 / motion 15 / fidelity 20`，±20% 步进）。

**阻塞点（关键）**：实测 golden 12 条中 **7 条 refined + 1 条 batch = 8 条分数 ≥98.6（其中 7 条=100）**，human 分只有 80-90。这些样本六要素全中、三布尔全 True、无 source 时 fidelity=1.0 → 任何权重组合都把它们算到封顶 100，**对权重梯度不可导**。真正"可移动"的只有 5 条（hg-assets-003/020、hg-credits-013/016、hg-scene_cinema_bomb-003）。在 5 个点上拟合 6 个权重 = 确定性过拟合。

**建议**：
1. 先把"封顶效应"拆掉（见遗漏优化点 #1），让 refined 高分区间出现梯度；
2. 再用 golden（全 12 条）+ 258 语料分布（mean/score≥90 占比）双口径做**小步网格**（±20%），每次改动必须双复测；
3. CI 门禁（r≥0.90 / MAE≤18）**值得固化**——当前 0.913/16.93 已达标，作为回归护栏是对的，但它是"下限保护"不是"优化杠杆"。建议门禁再加 `258 mean` 与 `score≥90 占比` 两个分布哨兵，防校准走偏。

**风险**：任何权重改动都会改变全部 258 条分数分布（mean 90.9 必动）；在 12 条 golden 上优化 r/MAE 极易过拟合到这几个样本。

**测试策略**：权重参数化后，`eval_golden_set.py` 与 258 复测脚本（§8.5 口径）做成同一 CI 命令；golden 增补非封顶样本。

---

### P1-1 六要素词边界 — 低可行/高风险，改手术式（B 批降级）

**可行性：低（全面版）**。当前元素命中是 `t in lower` 子串（evaluator.py:577）。实测误击：`"hundreds of soldiers"` → 命中 color `red`；`"the sacred temple"` → `red`；`"required by the director"` → `red`；`"category of subjects"` → subject `cat`。但**全面词边界会引入两类假阴性**：
- 中文单字词表（`光/色/人/灰/金/白` 等）就是靠子串语义设计的，词边界后 `"光"` 几乎永远跟在汉字后 → 全 miss；
- 英文后缀词：`man` 现在能命中 `woman/human/snowman/german`；`dark` 命中 `darkness/darker`；词边界后这些全丢，**elements_score 全面下行**，258 语料 mean 90.9 大概率下降，golden refined 封顶样本可能被拉下（方向反而改善 MAE，但 batch/variant 更糟）。

**建议（手术式）**：
1. 只对**英文多字符歧义词**做词边界：构造一个 `_ELEMENT_BOUNDARY_ONLY` 集合（如 `red/cat/pan/cut/sea/space/light/dark` 中经 258 语料统计误击率高的），匹配时 `_contains_word` 而非 `in lower`；
2. 中文单字词维持子串；
3. 多词短语（`golden hour/rim light`）已是完整 token，词边界天然安全。

**风险**：边界词表选错会让部分英文 prompt 掉要素分。**测试**：先跑 258 语料，统计每个候选词在语料中的子串命中 vs 词边界命中差异，选差异最大的 5-10 个词进集合，双复测确认 mean 不降。

---

### P1-2 detect_tier 阈值单一来源 — 中可行，必须与 trailer 豁免联动（B 批）

**问题核验**：实测 450/600/800/850 词无标记文本 →
```
450词 → batch  lenpts=16.6
600词 → batch  lenpts=6.6
800词 → batch  lenpts=0.0
850词 → refined lenpts=20.0   # 833 处断崖
```
`detect_tier`（evaluator.py:336）用常量 833；batch 上界 `min(max(400, max_length//6), 833)`（399-401）默认 max_length=1800 时是 **400**。400-833 区间 → batch 判定 + 长度带外扣分，即"双亏区"。

**陷阱（实测数据）**：把 600 词改判 refined 并不解决问题——它触发 refined 专属违规：
```
tier=None     score=56.3  lenpts=5.9    viol=[]
tier=refined  score=53.0  lenpts=20.0   viol=['missing_trailer','missing_audio']
```
即"修了长度分、丢了 trailer/audio 分"，净效应更差。**结论**：P1-2 不能单独做，必须与"长度推断 refined 的 trailer/audio 豁免"联动（例如：`detect_tier` 通过长度兜底推断 refined 时，在 checks 记 `tier_inferred_by_length=True`，`missing_trailer`/`missing_audio` 规则对该标记豁免，或对无 `[SHOT`/控制段标记的推断精修按"batch 上界扩展"处理）。

**具体实现建议**：
1. 抽 `_batch_hi(max_length) -> int`（399-401 逻辑），`detect_tier` 接收 `max_length` 参数（签名扩为 `(prompt, video, explicit_tier, max_length=None)`，向后兼容默认），改 `> _batch_hi(max_length)` 判定；
2. 或者更简单：统一把"未标记文本的 refined 兜底阈值"定义为 `batch_hi` 的上确界（即默认 400），400-833 区间明确归 refined 并配套豁免。**注意**：这会把一批 500-800 词 batch 长 prompt 误判 refined → 必须豁免 trailer/audio，否则误伤。

**风险**：高——tier 是长度带、trailer、audio、block_coverage、gated 规则的**总开关**，改判会级联。**测试**：600/700/833/834/850 词五档快照，断言 tier 与 violations 组合符合预期；258 语料中 400-833 区间的样本逐条 diff。

---

### P1-3 版本指纹 — 高可行（A 批）

**建议**：evaluate() 返回增补 `"evaluator_version": "v0.11-..."` + `"assets": {"element_keywords": sha256, "refined_blocks": sha256}`。实现：`video_prompt_engine/evaluator.py` 顶部加 `_EVALUATOR_VERSION` 常量与 `_asset_fingerprint()`（对 `Path(__file__).parent/knowledge/*.json` 做 sha256，可放模块级缓存）。rest.py:181 的 `"evaluator": "v0.10-deterministic"` 改为从 evaluator 导入版本常量（消除双处硬编码漂移）。**风险：零**（增量字段）。**测试**：改资产文件后 hash 变化；版本常量与 rest meta 一致。

---

### P1-4 select_best_detailed — 高可行（A 批）

**建议**：新增 `select_best_detailed(...)`（或给 `select_best` 加 `detail: bool=False` 参数，True 时返回 4 元组 `(prompt, meta, score, {candidate, info}[])`）。候选的 `checks/violations/advice` 已在循环内 compute（708-713），只需保留。**兼容**：`select_best` 现有签名/返回不动，`optimizer.py:332-343` 内联排序可后续接入。**风险：零**（纯增量）。**测试**：返回明细含违规与 advice；与 select_best 选出的 winner 一致。

---

### P1-5 性能 — 中可行，先 profile（C 批）

**现状**：`_contains_word` 每次调用对全文编译+扫描 regex（18-30），被元素/continuity/gated/excluded 大量调用；`_strip_reference_markers` 在**一次 evaluate() 内被调 3 次**（433 主路径、227 continuity、305 gated），每次多次 `re.sub` 全量扫。

**建议（按收益排序）**：
1. **去重 `_strip_reference_markers`**：evaluate() 顶部算一次 `body_text`（433 已算），把 reference_names 传进 `_check_continuity`（227）与 `_apply_gated_rules`（305），删掉内部重复调用。这同时修一个**正确性**问题（见遗漏 #4）。低风险。
2. **英文集合索引**：`_build_token_index(body)` → `(set(re.findall(r"[a-z0-9'\-]+", body.lower())), zh_2grams)`；`_contains_word` 对拉丁 token 改集合查 O(1)。**只对非否定路径生效**——gated 的 `_negated`（163-168）需要 match 位置，仍走 regex。元素匹配（577）可切到集合查。
3. 模块级 `re.compile` 缓存 pattern（`re.search` 虽内置 512 缓存，但显式 compile 更可控）。

**风险**：集合构建口径与 regex 边界必须逐字一致（连字符/撇号/大小写），否则漂移改变命中 → **score 分布变化**。测试：对 258 语料跑"改造前后逐条 score 全等"断言（这是唯一允许"分数不变"的强测试）。

---

### P2-1 次要项 — 拆分处理

| 子项 | 判定 | 建议 |
|---|---|---|
| advice 按严重度排序 | 高可行/低风险（A） | `_build_advice`（658-692）先排 violations（按 penalty 绝对值降序）再排缺失要素，最后镜头。测试：断言顺序。 |
| 元素 TF-IDF 扩表 | 中可行/高价值（B） | **golden ru 样本 -38.7 的根因**：`полицейских/серый/фон/однотонном` 全不在 RU 词表。TF-IDF 从 258 语料按要素聚类**产出候选**，**人工审校后进资产**（防"自动扩表稀释精度"：一个泛词误入会让该要素假命中暴增）。建议首轮手工补 RU：subject+полицейский/группа、color+серый/однотонный、environment+фон/пейзаж。 |
| `_GATED_RULES_CACHE` 加锁 | 高可行/低价值（A） | `_gated_rules()`（273-293）`if not _GATED_RULES_CACHE` 并发下双写 idempotent，GIL 下实际无破坏；但用 `functools.lru_cache` 或 `_GATED_RULES_LOADED` 哨兵更干净。 |
| 空输入显式契约 | 高可行/低风险（A） | 实测 `evaluate("")` → score 16.7（fidelity 白送 20）。API 层已 422（rest.py），但 evaluate() 内部无契约。建议：空/纯空白 → 返回 `{"score": 0, "checks": {"empty": True}, ...}`，或显式 `checks["empty"]=True` 让上游决策。 |

---

## 第二部分：优先级与取舍

**合并建议**：
- **P1-3 + P1-4 合并实现**：都改 evaluate()/select_best 的返回结构，一次动 schema、一次回归。
- **P0-2 + P1-1 合并思考但分开落地**：共享"词边界正则单一来源"（`_WORD_BOUNDARY_RE` + CJK 长名守卫），但 P0-2 对角色名生效、P1-1 只对英文歧义词生效，**不可混为一个全局开关**。
- **P1-2 + P2-1 的 trailer 豁免**：P1-2 的 refined 推断标记是 trailer/audio 豁免的前置，二者绑定实现。

**砍掉/降级**：
- **P1-1 全面词边界：降级为手术式**（理由见上，全面版会打崩中文单字词与后缀词，动 258 mean 方向未知）。
- **P0-4 权重校准：暂缓到封顶效应拆解之后**，否则在 5 条非封顶样本上过拟合。
- **P1-5：先 profile 再决定深度**；至少做"strip 去重"（低风险+顺带修正确性），集合化视 profile 结果。

**为什么这些取舍**：A 批五项全部是"不改变分数分布或只修明显误判"，可直接落地；B 批四项都改变分数分布，必须配 258+golden 双复测门禁，串行做、逐项 diff；C 批两项被结构性前置条件（封顶效应、profile 数据）阻塞。

---

## 第三部分：清单外遗漏优化点（按优先级）

**1. 封顶效应（最高优先级，P0-4 的前置）**
实测 golden 8/12 样本 ≥98.6、7 条=100，human 80-90。三个叠加根因：无 source → fidelity 恒 1.0（612）；`has_shot/has_camera/has_motion` 三布尔 0/20/15/15（594-596）；六要素全中 → elements_score=1.0。**修复方向**：
- 镜头三维度**分级**：`_count_distinct_shot_terms` 等，按不同景别/运镜类型数给 0-1 梯度（如 ≥3 类满分）；
- 无 source 时 fidelity 的 20 分**重分配**给结构质量（block_coverage ratio、trailer/控制段、细节密度），不再白送；
- 二者都会把 refined 高分区间从"全 100"拉开，直接改善 golden MAE（当前 7 条 refined 贡献 +8.6~+15 的正向 delta）。

**2. RU/短形态公式错配**
- RU：词表缺口（见 P2-1），golden ru 样本 +38.7 可修复；
- variant/asset 短卡：hg-credits-013/016 只有 41-44 分 vs human 70-75。根因是"丰富度公式"（六要素+三镜头布尔）对 38-85 词的单镜广告/转场卡**无分可给**——它们形态完整但要素/镜头稀疏。建议 asset/variant 用**形态专属权重**（提高 length+fidelity 占比、降低 elements 占比），或加"形态完整性"信号（variant：是否含转场/时序描述；asset：是否含主体+背景+风格的最小集）。

**3. `_strip_reference_markers` 三次调用参数不一致（正确性）**
433 用 `reference_names`（excluded+swap）剥离，但 `_check_continuity`（227）与 `_apply_gated_rules`（305）**不带名字**调用 → `[ABSENT] Roko` 中的 `Roko` 在 continuity/gated 路径残留，可能把"声明缺席"的角色计为在场。建议 evaluate() 单次剥离 body 下传（同 P1-5 优化点 1）。

**4. 无 source fidelity 与松散 paraphrase 待遇不一致**
无 source 白送 20 分，忠实但改写的 paraphrase 可能只得 0.2。语义应统一：fidelity 只在有 source 时计分，无 source 时 20 分重分配（见 #1），或至少文档声明"无 source=保真不参与"。

**5. 中文保真 2-gram 过脆**
evaluator.py:601-604 用 `c in str(prompt)` 整块子串匹配，近义改写（"奔跑"→"跑步"、"站起"→"起身"）全不命中。当前无中文保真 golden 样本，属已知盲区；若做 P0-1 的 zh→en，顺手可补 zh→zh 的 2-gram 归一（如去"了/着/在"后再匹配）。

**6. 833 魔数双处硬编码**
detect_tier:336 与 399-401。P1-2 已覆盖，但补充：`count_words` 对中文无意义（`"一位将军…"*20` → words≈1），detect_tier 的 833 长度兜底对中文**永不触发**（docstring W11 已注明）——建议显式把"zh 不走长度兜底"写成测试锚点，防未来误改。

---

## 第四部分：兼容性风险矩阵（对 258 mean 90.9 / golden r 0.913）

| 方案 | 改变分数分布? | 方向预判 | 说明 |
|---|---|---|---|
| P0-2 中文词边界 | **是（局部）** | 混合 | 减少中文 excluded/swap 误扣 → 部分中文样本**上行**；若守卫过严引入 continuity 假阴性 → 局部下行。258 语料以 en 为主，影响面小。golden 无中文样本 → r 不变。 |
| P0-3 违规量化 | **否**（并行结构） | 不变 | 顶层 `violations` 值不变、计分公式不变；仅 tie-break 语义在真同分时变化（select_best/optimizer 输出可能翻动，概率低）。 |
| P0-1 跨语言保真 | **否**（门控新路径） | 不变 | 只影响 `_detect_translation_mode=True` 的输入。258/golden 无 zh→en 对 → 指标不变。 |
| P0-4 权重校准 | **是（全局）** | 未知 | 动公式即动 258 mean 与 golden MAE/r。当前 7/12 golden 封顶 100，权重搜索对它们无效 → 强过拟合风险。 |
| P1-1 六要素词边界 | **是（全局 en）** | 大概率下行 | elements_score 全面降 → 258 mean 90.9 下降；golden refined 封顶样本被拉下（MAE 或改善）但 variant/ru 更糟。**全面版不推荐**。 |
| P1-2 阈值单一来源 | **是（400-833 区间）** | 混合/需联动 | 改判 refined 若不带 trailer/audio 豁免 → 实测 score 反而降低（56.3→53.0）。必须豁免联动，否则 258 mean 续降。 |
| P1-3/P1-4 | **否** | 不变 | 纯增量字段。 |
| P1-5 性能 | **否（若口径全等）** | 不变 | 集合化必须与 regex 边界逐字等价；允许强测试断言"逐条分数全等"。 |
| P2-1 advice 排序 | **否** | 不变 | advice 顺序仅展示层。 |
| P2-1 TF-IDF 扩表 | **是（ru/短卡）** | 上行 | 补 RU 词表 → ru 样本 elements_score 升 → golden ru delta +38.7 修复、258 ru 样本上行。**这是清单里对 golden MAE 最直接的正向杠杆**。 |
| P2-1 空输入契约 | **是（仅空输入）** | 下行 | 空输入从 16.7 → 显式 0/契约分；API 层已 422，影响面≈0。 |

**一句话总结**：真正会动现有指标的是 **P1-1（全面版，方向不利）、P1-2（需联动）、P2-1 扩表（正向）、P0-4（过拟合风险）**；而 golden MAE 的最大修复机会不在清单内，而在**封顶效应拆解 + RU 词表补齐**两件事上。

---

需要的话，我可以把这份分析落盘到 `.ccg/tasks/evaluator-p0p2-round2/` 作为分析产物，或先对"封顶效应拆解"与"RU 词表补齐"做一版带 golden/258 双复测数字的 mini 实验（只读跑分，不写代码）。

---
SESSION_ID: 21e4f1d8-fc06-4a48-b2d4-9582b3710741
