"""视频提示词质量评估 — 保真/六要素/镜头字段/长度（用于多候选择优与反馈评分）。"""
from __future__ import annotations

import re
import threading
from difflib import SequenceMatcher

from video_prompt_engine.refined_blocks import clean_blocks, rendered_block_names
from prompt_engine_core.knowledge import load_element_keywords

# P0-P2 round2：评估器版本指纹（rest.py meta 复用，消除双处硬编码漂移）
_EVALUATOR_VERSION = "v0.11-deterministic"
_ASSET_FP_CACHE: dict | None = None


def _asset_fingerprint() -> dict[str, str]:
    """评估相关资产 sha256（element_keywords/refined_blocks/golden_set），模块级缓存。"""
    global _ASSET_FP_CACHE
    cached = _ASSET_FP_CACHE
    if cached is not None:
        return cached
    import hashlib
    from pathlib import Path
    engine_base = Path(__file__).resolve().parent / "knowledge"
    core_base = Path(__file__).resolve().parent.parent / "prompt_engine_core" / "knowledge"
    local: dict[str, str] = {}
    for name in ("element_keywords", "refined_blocks", "golden_set"):
        candidate = (core_base / f"{name}.json") if name == "element_keywords" else (engine_base / f"{name}.json")
        try:
            local[name] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            local[name] = "missing"
    # 评审 Major-2：先构建局部 dict 再原子赋值，避免并发首波读到半填充缓存
    _ASSET_FP_CACHE = local
    return local


def _WORD_BOUNDARY_RE(token: str) -> re.Pattern:
    """拉丁词边界正则单一来源（合并 _contains_word 与 _token_occurrences 双处实现）。"""
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )


def _CYRILLIC_BOUNDARY_RE(token: str) -> re.Pattern:
    """西里尔词左侧边界（评审 Minor：фон 不得命中 телефон/микрофон）。

    只做左侧严格边界，右侧不设限以容忍俄语变格——词形表已显式收录
    полицейский/полицейских、мужчина/мужчины 等复数/属格形态，
    右侧加界会把真实命中打成假阴性。фонтан 类前缀词残留为已知限制（与旧子串行为一致）。
    """
    return re.compile(
        r"(?<![A-Za-z0-9\u0400-\u04ff])" + re.escape(token),
        flags=re.IGNORECASE,
    )


# Round3 Batch C：lock-gated 规则资产缓存（refined_blocks.json，缺失/损坏回退空表 → 规则不启用零误报）
_GATED_RULES_CACHE: dict = {}
_GATED_RULES_LOADED = False
_GATED_RULES_LOCK = threading.Lock()  # 评审 Minor：模块级直建，消除惰性创建的理论竞态


def count_words(text: str) -> int:
    return len(str(text or "").split())


def _contains_word(text: str, token: str) -> bool:
    """整名/词边界匹配：空 token 与单字符拒绝（中文"关"会误击"关键"）；英文按字母数字边界。"""
    token = str(token or "").strip()
    if not token or len(token) < 2:
        return False
    return _WORD_BOUNDARY_RE(token).search(str(text or "")) is not None


# P0-2：CJK 名字后随字白名单（保守启发——宁漏勿误）。
# 中文无空格，「林晓雨」里「林晓」是更长名字的前缀；当命中位置的后随字为 CJK 且
# 不属于常见动词/助词/介词/方位等后随字时，视为未登记的长名前缀而跳过命中。
# 泛词路径（posture/lock-gated）不经过此表，维持子串语义。
_CJK_NAME_FOLLOW_OK = frozenset(
    # 动词（站坐走跑看说拿握持举……）
    "站坐躺趴跪蹲走跑跳奔飞骑乘坐爬滑跌倒摔翻滚转回退进出上下起停立"
    "望看瞧盯注视瞥扫观察寻找见遇碰撞迎追赶逃避躲藏挡拦护扶挽拉拖拽"
    "推搬抬扛举提拎拿握抓捏抱搂拥搀携带佩挂背负挑担顶触摸抚拍击打敲"
    "砸砍劈刺戳捅射击中炸轰扔抛投掷洒泼倒灌浇注流淌涌喷滴落降升浮沉"
    "漂荡摇晃摆颤抖震惊吓哭笑喊叫吼嚷唱说讲问答道述谈聊议论商量请求"
    "邀请谢拒绝答应允诺承认辩解解释劝阻止制防抗抵反击攻打战斗拼搏挣扎"
    "杀屠灭歼俘擒绑捆锁铐押送带领引导指挥命令派遣任命选择挑选拣拾收"
    "藏存放摆放置搁丢弃传递交付给予送汇报知通知宣布广播播放演奏弹跳"
    "舞跃翱翔盘旋俯冲掠过越过穿越跨登攀潜游划驾驶操控掌握运用使用借"
    "助依靠信任相信怀疑质疑猜测推测判断决定规划计划筹谋设计构思准备"
    "安排部署调配调度领导管理统治支配主宰掌管负责承担肩负履行执行实"
    "施落实完成达成实现赢得获得取得争取抢夺掠夺劫持绑架威胁恐吓欺骗"
    "哄骗隐瞒掩饰伪装装扮化妆变身转化蜕变进化升级强化增强削弱减退抵"
    "御进攻突袭袭击偷袭伏击围攻包围困封锁禁囚押拘留逮捕抓捕搜捕追捕"
    "审讯审判处决执行枪决斩首杀害谋杀暗杀刺杀行刺遇袭受伤负伤中弹流"
    "血受困陷入困境求救援救抢救医治治疗包扎敷药服药喝水吃饭进食用餐"
    "品尝嗅闻听倾听聆听谛听凝视端详打量审视环顾眺望遥望仰望俯瞰观赏"
    "欣赏赞叹感慨感叹惊叹惊讶愣住呆住怔住恍惚清醒苏醒觉醒复苏恢复痊"
    "愈好转恶化减轻缓解消除根除铲除肃清清理打扫收拾整理归置陈列展示"
    "呈现显露露出浮现涌现出现闪现消失隐没隐藏潜藏藏匿潜伏埋伏遁逃溜"
    "走逃走潜逃逃窜逃亡出逃叛变倒戈反水背叛出卖泄密告密检举揭发举报"
    "起诉控告指控指责责怪埋怨抱怨诉苦申冤鸣冤喊冤伸冤平反昭雪报仇复"
    "仇雪恨解恨泄愤出气撒气消气息怒安抚劝慰宽慰慰藉安慰抚慰温暖温馨"
    "感动触动打动震撼冲击影响感染熏陶陶冶培养造就塑造铸造锻炼磨练锤"
    "炼洗礼考验磨难历练成长进步提高提升增长上升飙升暴涨猛增激增递减"
    "下降减少缩减削减压缩扩大扩张拓展延伸延长拉长缩短加快减速加速放"
    "缓缓慢渐渐慢慢快速飞快急速高速徐徐悠悠轻轻悄悄静静默默"
    # 助词/介词/连词/副词/数词
    "着了过在到向从对和与或是为被把将就才也都又还再便已正于之而但却"
    "则虽若当随沿朝往冲穿越及跟同并且因所以然后自至由经通凭借按照依"
    "据根据关于对于至于除了除非假如如果只要只有无论不管尽管虽然但是"
    "可是不过然而反而相反另外此外同时紧接着随后接着之后以前以后最后"
    "首先最终结果于是因此故而由此由于鉴于考虑到针对面向朝向通向走向"
    "驶向飞向冲向奔向指向面对直面迎面侧面背面后面前面上面下面里面外"
    "面旁边左边右边前方后方上方下方内部外部中间中央四周周围附近远处"
    "深处高处低处顶端底部末端尽头边缘角落墙角路边树下门口窗前床边桌"
    "旁边岸脚顶腰谷"
    # 方位/位置单字尾随
    "身背面前后左右上下里外中旁近远深高底顶角墙路树门窗床桌"
    # 独立副词/数词首字
    "一三四五六七八九十两半独突终开继缓轻悄静默慢渐逐悠快迅立马转回"
    "低抬扭侧眯眨瞪闭睁张嘴抿咬舔咽吞吐呼吸喘叹松屏闷哼呢嘀嘟嚷"
    "仍依刚忽猛骤顿径直单独仅只唯恰正好现将欲拟备算决意图企试尝怒悲"
    "喜惊恐惧忧伤痛苦累困倦饿渴冷热凉寒安宁寂沉"
)


def _contains_name(text: str, token: str, known_names: list[str]) -> bool:
    """角色名匹配（P0-2）：拉丁 token 词边界；CJK token 检查是否被更长已知名字覆盖。

    中文无空格，名字后紧跟汉字是常态（「林晓走进」），不能加 CJK 边界；
    但 excluded 角色「林晓」不得命中「林晓雨」——命中位置是某更长已知名字的
    前缀时跳过（known_names = excluded + swap + character_list 并集）；
    未登记的长名靠后随字白名单兜底（后随字为非常见动词/助词等时按长名前缀跳过）。
    泛词路径（posture/gated locks）不经过此函数，维持子串语义。
    """
    token = str(token or "").strip()
    text_value = str(text or "")
    if not token or len(token) < 2:
        return False
    if not re.search(r"[\u4e00-\u9fff]", token):
        return _contains_word(text_value, token)
    longer = sorted(
        (str(n).strip() for n in (known_names or []) if len(str(n or "").strip()) > len(token) and token in str(n)),
        key=len,
        reverse=True,
    )
    for match in re.finditer(re.escape(token), text_value):
        start = match.start()
        covered = any(
            text_value[start:start + len(name)] == name
            or (start - 1 >= 0 and text_value[start - 1:start - 1 + len(name)] == name)
            for name in longer
        )
        if not covered:
            # 2 字 token 才是「更长名字前缀」的主要形态（林晓⊂林晓雨）；
            # ≥3 字（贾克斯）已是完整名，后随汉字多为动词/副词，不做后随字过滤
            after = text_value[start + len(token):start + len(token) + 1]
            if len(token) == 2 and after and re.match(r"[\u4e00-\u9fff]", after) and after not in _CJK_NAME_FOLLOW_OK:
                continue  # 疑似未登记更长名字前缀，宁漏勿误
            return True
    return False


def _detect_translation_mode(source: str, prompt: str) -> bool:
    """翻译模式（P0-1）：source 含 CJK 且 prompt 不含（或反之），且双方非空。"""
    src, dst = str(source or ""), str(prompt or "")
    if not src or not dst:
        return False
    src_zh = bool(re.search(r"[\u4e00-\u9fff]", src))
    dst_zh = bool(re.search(r"[\u4e00-\u9fff]", dst))
    return src_zh != dst_zh


def _cross_lingual_fidelity(source: str, prompt: str) -> float:
    """翻译模式保真：0.5 要素跨语言守恒 + 0.3 镜头结构保留 + 0.2 长度比。

    仅 _detect_translation_mode 为真时启用（门控新路径，en→en/zh→zh 零触碰）。
    局限（声明）：要素为 6 维粗粒度类别，测的是「类别保留」而非逐实体语义保真。
    """
    element_keywords, _ = load_element_keywords()
    src_lower = str(source or "").lower()
    dst_lower = str(prompt or "").lower()

    def _en_hits(text_value: str, words: list) -> bool:
        return any(
            _contains_word(text_value, str(w))
            or _contains_word(text_value, str(w) + "s")
            or _contains_word(text_value, str(w) + "es")
            for w in words
        )

    # 评审 Major-1：双向配对——zh→en 与 en→zh 任一方向要素守恒均计分。
    # 旧实现只查「src 中文 vs dst 英文」，en→zh 方向 conserved/kept 恒≈0，只剩长度比。
    conserved = 0.0
    for _elem, _langs in element_keywords.items():
        zh_src = any(str(w) in src_lower for w in _langs.get("zh", []))
        en_src = _en_hits(src_lower, _langs.get("en", []))
        zh_dst = any(str(w) in dst_lower for w in _langs.get("zh", []))
        en_dst = _en_hits(dst_lower, _langs.get("en", []))
        if (zh_src and en_dst) or (en_src and zh_dst):
            conserved += 1.0
    conserved /= max(1, len(element_keywords))

    dims = (
        (("镜头", "景别", "特写", "全景", "俯拍", "跟拍", "推移", "推近", "近景", "中景", "远景", "仰拍", "航拍"),
         ("shot", "cut", "close-up", "closeup", "close up", "wide", "overhead", "tracking", "dolly",
          "push-in", "push in", "establishing", "aerial", "crane")),
        (("机位", "视角", "广角", "长焦", "镜头"),
         ("camera", "lens", "angle", "perspective", "viewpoint", "wide-angle", "telephoto", "close-up", "closeup")),
        (("运镜", "摇镜", "推镜", "拉镜", "旋转", "慢动作", "推近", "拉远", "环绕", "晃动", "抖动"),
         ("slow-motion", "slow motion", "pan", "tilt", "tracking", "dolly", "zoom", "crane", "handheld",
          "push-in", "push in", "drift", "whip", "orbit", "rotate", "shaky")),
    )
    kept = 0.0
    for zh_toks, en_toks in dims:
        src_zh_has = any(t in src_lower for t in zh_toks)
        src_en_has = any(_contains_word(src_lower, t) for t in en_toks)
        dst_zh_has = any(t in dst_lower for t in zh_toks)
        dst_en_has = any(_contains_word(dst_lower, t) for t in en_toks)
        if (src_zh_has and dst_en_has) or (src_en_has and dst_zh_has):
            kept += 1.0
    kept /= len(dims)

    # 长度比：CJK 无空格，split() 会坍缩为 1 词 → 用汉字数；拉丁按词数。
    if re.search(r"[\u4e00-\u9fff]", str(source or "")):
        src_len = max(1, len(re.findall(r"[\u4e00-\u9fff]", str(source or ""))))
    else:
        src_len = max(1, len(str(source or "").split()))
    if re.search(r"[\u4e00-\u9fff]", str(prompt or "")):
        dst_len = max(1, len(re.findall(r"[\u4e00-\u9fff]", str(prompt or ""))))
    else:
        dst_len = max(1, len(str(prompt or "").split()))
    ratio = min(src_len / dst_len, dst_len / src_len)
    return round(0.5 * conserved + 0.3 * kept + 0.2 * ratio, 3)


_ZH_STOP_CHARS = frozenset("了着在的与及或是有一把被从向对到里个这那之也又都")


def _zh_fidelity_grams(text: str) -> set[str]:
    """中文保真 2-gram（P2-5）：去高频虚字/标点/空白后滑动取二元组集合，容忍语序与虚字差异。"""
    cleaned = "".join(
        ch for ch in str(text or "")
        if ch not in _ZH_STOP_CHARS and not ch.isspace() and ch not in "，。！？；、,.!?;：:"
    )
    if len(cleaned) < 2:
        return set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def _strip_reference_markers(text: str, reference_names: list[str] | None = None) -> str:
    """剥离引用协议标记区段（[ABSENT] <name> / <<<...>>>），避免合规标记自罚分。

    契约侧 _assertReferenceProtocol 要求声明禁止项时正文嵌入标记；标记本身含角色名，
    计入 excluded/swap 命中会把引擎自己的合规输出判为违规。仅剥离标记 token 本身（+紧跟一个名字 token），
    标记后的同句真实出现仍会命中（评审 C1：过度剥离会隐藏真实违规）。
    """
    import re
    stripped = str(text or "")
    # 闭合 <<<...>>> 整段；未闭合前缀只按已知引用名精确剥离，避免中文无空格正文被 \S+ 吞掉。
    stripped = re.sub(r"<<<.*?>>>", "", stripped, flags=re.DOTALL)
    names = sorted(
        {str(name).strip() for name in (reference_names or []) if str(name or "").strip()},
        key=len,
        reverse=True,
    )
    for name in names:
        suffix = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", name) else ""
        stripped = re.sub(r"<<<\s*" + re.escape(name) + suffix, "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(
            r"\[ABSENT\]\s*" + re.escape(name) + suffix,
            "",
            stripped,
            flags=re.IGNORECASE,
        )
    stripped = re.sub(r"<<<", "", stripped)
    stripped = re.sub(r"\[ABSENT\]", "", stripped, flags=re.IGNORECASE)
    return stripped.strip()


def _parse_time_span(value: str) -> list[float] | None:
    """解析时间区间 "m:ss-m:ss" / "s.s-s.s"，返回 [start, end] 秒；解析失败返回 None。"""
    if not value:
        return None
    parts = str(value).split("-")
    if len(parts) != 2:
        return None

    def _to_seconds(token: str) -> float | None:
        token = token.strip()
        if not token:
            return None
        if ":" in token:
            m, _, sec = token.partition(":")
            try:
                return int(m) * 60 + float(sec)
            except (TypeError, ValueError):
                return None
        try:
            return float(token)
        except (TypeError, ValueError):
            return None

    start = _to_seconds(parts[0])
    end = _to_seconds(parts[1])
    if start is None or end is None:
        return None
    return [start, end]


# Round3 Batch B：承接保真检查词表
# 停用词（功能词）与高频泛词（镜头/环境/画面无关词）分列——泛词残留会稀释命中率，
# 角色/姿势实体被丢仍 ≥60% 假阴性（评审 Warning-3）。
_CONTINUITY_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "of", "in", "on", "at", "to", "for", "with", "by",
    "from", "as", "his", "her", "its", "their", "they", "he", "she", "it",
    "we", "you", "i", "that", "this", "these", "those", "there", "here",
    "not", "no", "all", "each", "both", "into", "onto", "over", "under",
    "between", "toward", "towards", "around", "across", "against", "during",
    "through", "before", "after", "above", "below", "out", "up", "down",
    "off", "away", "near", "far", "also", "very", "then", "than", "when",
    "while", "which", "who", "whom", "what", "where", "how", "why",
    "has", "have", "had", "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "do", "does", "did", "just", "only", "even",
    "still", "yet", "now", "once", "much", "many", "more", "most", "some",
    "any", "such", "same", "other", "another", "one", "two", "three",
    "first", "second", "third", "last", "next", "back",
})
_CONTINUITY_GENERIC = frozenset({
    "camera", "frame", "frames", "screen", "shot", "shots", "scene", "view",
    "angle", "lens", "cut", "cuts", "fade", "focus", "center", "middle",
    "edge", "light", "lighting", "shadow", "shadowing", "background",
    "foreground", "atmosphere", "tone", "palette", "texture", "surface",
    "space", "position", "positioned", "motion", "movement", "style", "look",
    "detail", "details", "slow", "fast", "left", "right", "top", "bottom",
    "front", "rear", "side", "area", "region", "part", "full", "half",
    "wide", "low", "high", "dark", "bright", "soft", "hard", "cold", "warm",
})
# 中文位置/姿势关键词表（白名单判定用；显式词表而非 2-gram——评审 Critical-1）
_CONTINUITY_ZH_POSTURE = (
    "站起", "站立", "坐下", "躺着", "跪着", "趴着", "倒下", "低头", "抬头",
    "转身", "面向", "背对", "闭眼", "睁眼", "流血", "握着", "举起", "抱住",
    "靠着", "昏迷", "死亡", "地上", "雪地", "门口", "角落", "中央", "前景",
    "背景", "远处", "墙边", "窗边", "边缘", "水面", "台阶", "床边", "树下",
)

# 否定感知（评审 Critical-2/C3）：forbidden 命中前查否定前缀，禁令形态不计命中。
# 扩充：out of / away from / free of / devoid of / nobody / no one / do not / don't / absent（评审补充），
# 覆盖三分法/视线约束的自然禁令措辞（"keep the hero OUT of the center of frame"、"nobody is looking at camera"）。
_NEGATION_RE = re.compile(
    r"(?i)(?:\b(?:no|not|without|never|avoid|nobody|no one|do not|don't|out of|away from|free of|devoid of|absent)\b(?:\s+\S+){0,4}\s*"
    r"|(?:无|不|禁止|切勿|避免)[^，。！？；,;.!?\n]{0,16})$"
)


def _token_occurrences(text: str, token: str) -> tuple[str, list[re.Match]]:
    token = str(token or "").strip()
    if not token or len(token) < 2:
        return str(text or ""), []
    text_value = str(text or "")
    pattern = _WORD_BOUNDARY_RE(token)
    return text_value, list(pattern.finditer(text_value))


def _occurrence_is_negated(text_value: str, match: re.Match) -> bool:
    prefix = text_value[max(0, match.start() - 64):match.start()]
    clause_prefix = re.split(r"[，。！？；,;.!?\n]", prefix)[-1]
    return _NEGATION_RE.search(clause_prefix) is not None


def _count_negated_occurrences(text: str, token: str) -> int:
    """Count token occurrences negated in their own clause."""
    text_value, matches = _token_occurrences(text, token)
    return sum(1 for match in matches if _occurrence_is_negated(text_value, match))


def _negated(text: str, token: str) -> bool:
    """仅当 token 的每一次出现都在各自分句内被否定时返回 True。"""
    text_value, matches = _token_occurrences(text, token)
    if not matches:
        return False
    return all(_occurrence_is_negated(text_value, match) for match in matches)


def _extract_continuity_tokens(text: str) -> list[str]:
    """英文实体 token 提取：≥2 字符字母数字（连字符/撇号保留），去停用词与高频泛词，去重保序。"""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'\-]{1,}", str(text or ""))
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        low = t.lower()
        if low in _CONTINUITY_STOPWORDS or low in _CONTINUITY_GENERIC:
            continue
        if low not in seen:
            seen.add(low)
            result.append(low)
    return result


def _stem_en(token: str) -> str:
    """轻量英文词干（仅保真命中用，保守优先：只做低风险归并，防不同词根撞干）。

    复数 -s/-es（es 仅 sibilant 词尾）、双写辅音的 -ing/-ed 归并；
    e-dropping（stare→stared）、不规则词与长度 ≤3 词不归并——宁可假阴性，
    不做 stares→star / hated→hat 类撞干（评审复验 W3-新）。
    """
    t = str(token or "").lower()
    if len(t) <= 3:
        return t
    if t.endswith(("sses", "shes", "ches", "xes", "zes")):
        t = t[:-2]
    elif t.endswith("s") and not t.endswith("ss") and not t.endswith("us"):
        t = t[:-1]
    for suffix in ("ing", "ed"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 4:
            stem = t[:-len(suffix)]
            if len(stem) >= 4 and stem[-1] == stem[-2]:
                t = stem[:-1]
            break
    return t


def _en_stems(text: str) -> set[str]:
    """文本全部英文 token 的词干集合（保真词形归一命中用）。"""
    return {_stem_en(t) for t in re.findall(r"[a-z][a-z0-9'\-]{1,}", str(text or "").lower())}


def _check_continuity(body: str, prev_final_frame: str, character_list: list, absent_names: list[str] | None = None) -> tuple[bool, dict]:
    """跨镜承接保真（Round3 Batch B，评审修订版）。

    英文：实体 token 命中率 ≥40%，且终态帧中实际出现的角色名必中（硬判据，评审 W1 收窄——
    全量场景 roster 不要求全部出镜，只约束上一镜终态确实在场的主体）。
    中文：弃 2-gram——显式白名单（角色名 + 终态中出现的姿势/位置词）命中 ≥60%；
          无白名单时终态文本在 body 中的最长匹配覆盖率（find_longest_match 块长 / 终态长）≥0.5
          （评审 Critical-1：旧 SequenceMatcher 整句 ratio 在生产长度下数学不可达——500+ 字符 body
          逐字重述 50 字符终态也只有 ~0.18；覆盖率口径下完整重述 ≈1.0 可判定）。
    返回 (通过?, checks)。无 prev_final_frame 时通过且 ratio=None（零回归）。
    """
    if not prev_final_frame:
        return True, {"continuity_hits": 0, "continuity_total": 0, "continuity_ratio": None, "continuity_method": None}
    body = str(body or "")
    roster = [str(n).strip() for n in (character_list or []) if str(n or "").strip()]
    # 评审 W1：硬判据只针对"终态帧中实际出现的角色"，未入终态的副角色不要求出镜
    # P0-P2 round2：[ABSENT] 声明角色从硬判据豁免（有意缺席不判断裂）
    names = [n for n in roster if _contains_name(prev_final_frame, n, roster) and n not in (absent_names or [])]
    names_set = set(names)
    is_zh = bool(re.search(r"[\u4e00-\u9fff]", str(prev_final_frame)))
    if is_zh:
        keywords = [w for w in _CONTINUITY_ZH_POSTURE if w in prev_final_frame]
        whitelist = names + keywords
        if whitelist:
            hits = []
            for w in whitelist:
                # 评审 Minor：len<2 分支为死代码（_contains_word/_contains_name 均拒绝单字符），
                # 移除后单字符名走宁漏勿误路径，不产生无边界子串误击
                if w in names_set:
                    if _contains_name(body, w, roster):
                        hits.append(w)
                elif _contains_word(body, w):
                    hits.append(w)
            ratio = len(hits) / len(whitelist)
            ok = ratio >= 0.6
            return ok, {
                "continuity_hits": len(hits), "continuity_total": len(whitelist),
                "continuity_ratio": round(ratio, 3), "continuity_method": "whitelist",
            }
        sm = SequenceMatcher(None, prev_final_frame, body)
        match = sm.find_longest_match(0, len(prev_final_frame), 0, len(body))
        ratio = (match.size / len(prev_final_frame)) if prev_final_frame else 1.0
        ok = ratio >= 0.5
        return ok, {
            "continuity_hits": round(ratio, 3), "continuity_total": 1,
            "continuity_ratio": round(ratio, 3), "continuity_method": "ratio",
        }
    tokens = _extract_continuity_tokens(prev_final_frame)
    hits = [t for t in tokens if _contains_word(body, t)]
    ratio = len(hits) / len(tokens) if tokens else 1.0
    checks = {
        "continuity_hits": len(hits), "continuity_total": len(tokens),
        "continuity_ratio": round(ratio, 3), "continuity_method": "wordlist",
    }
    ok = ratio >= 0.4
    if names:
        missing = [n for n in names if not _contains_name(body, n, roster)]
        if missing:
            ok = False
            checks["continuity_missing"] = missing
    return ok, checks


def _extract_absent_names(text: str, names: list[str]) -> list[str]:
    """提取 [ABSENT] 标记声明的名字（P1-5 豁免语义用）。

    评审 Critical：names 需含 excluded + swap + character_list 并集——[ABSENT] 对
    跨镜承接 roster 角色的豁免同样生效（旧实现漏 character_list，<<<[ABSENT] Roko>>> 整段
    剥离后角色名不在正文 → continuity_break 误判）。拉丁名加后随边界（[ABSENT] Rokosh
    不得判 Roko 缺席）；同一位置被更长名字覆盖时短名不重复判缺席（[ABSENT] 王芳雨 只判王芳雨）。
    """
    text_value = str(text or "")
    matched_ranges: list[tuple[int, int]] = []
    found: list[str] = []
    for name in sorted(
        {str(n).strip() for n in (names or []) if str(n or "").strip()},
        key=len,
        reverse=True,
    ):
        suffix = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", name) else ""
        pattern = re.compile(r"\[\s*ABSENT\s*\]\s*" + re.escape(name) + suffix, flags=re.IGNORECASE)
        for match in pattern.finditer(text_value):
            if any(match.start() < end and start < match.end() for start, end in matched_ranges):
                continue
            matched_ranges.append((match.start(), match.end()))
            found.append(name)
    return found


def _gated_rules() -> dict:
    """加载 refined_blocks.json lock_triggers/enabled_rules（哨兵+锁缓存；缺失/损坏回退空表 → 规则不启用）。"""
    global _GATED_RULES_LOADED
    if _GATED_RULES_LOADED:
        return _GATED_RULES_CACHE
    with _GATED_RULES_LOCK:
        if _GATED_RULES_LOADED:
            return _GATED_RULES_CACHE
        try:
            from pathlib import Path
            import json
            p = Path(__file__).resolve().parent / "knowledge" / "refined_blocks.json"
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                _GATED_RULES_CACHE["triggers"] = data.get("lock_triggers") or {}
                _GATED_RULES_CACHE["enabled"] = set(data.get("enabled_rules") or [])
                _GATED_RULES_CACHE["coverage"] = data.get("coverage") or {}
            else:
                _GATED_RULES_CACHE["triggers"] = {}
                _GATED_RULES_CACHE["enabled"] = set()
                _GATED_RULES_CACHE["coverage"] = {}
        except Exception:
            _GATED_RULES_CACHE["triggers"] = {}
            _GATED_RULES_CACHE["enabled"] = set()
            _GATED_RULES_CACHE["coverage"] = {}
        _GATED_RULES_LOADED = True
    return _GATED_RULES_CACHE


def _apply_gated_rules(body: str, tier: str, violations: dict, checks: dict) -> None:
    """lock-gated 启发式（Round3 Batch C）：refined 专属；enabled_rules 控制启用；
    仅声明 lock 词时检测 forbidden（否定感知），命中 -5 advisory。body 为已剥离引用标记的正文。"""
    if tier != "refined":
        checks["gated_hits"] = []
        return
    rules = _gated_rules()
    triggers = rules.get("triggers") or {}
    enabled = rules.get("enabled") or set()
    body = str(body or "")
    hits: list[str] = []
    for name, rule in triggers.items():
        if name not in enabled:
            continue
        locks = rule.get("locks") or []
        forbidden = rule.get("forbidden") or []
        if not locks or not forbidden:
            continue
        if not any(_contains_word(body, l) and not _negated(body, l) for l in locks):
            continue
        for f in forbidden:
            if _contains_word(body, f) and not _negated(body, f):
                violations[name] = -5
                hits.append(name)
                break
    checks["gated_hits"] = hits


def _batch_hi(max_length: int | None) -> int:
    """batch 长度上界单一来源（P1-2）：batch 上界与 refined 长度兜底阈值共用，消除 500-833 双亏区。"""
    return min(max(400, (max_length or 1800) // 6), 833)


def detect_tier(prompt: str, video: dict | None, explicit_tier: str | None = None, max_length: int | None = None) -> str:
    """tier 判定：explicit（optimizer 按 creative_level≥7 传入 refined，否则 batch）优先；无 explicit 时 auto-detect 兜底。

    自动判据：shots 非空 / prompt 含 NON-IP 或 FINAL FRAME（refined 输出特征）；
    P1-2 长度兜底：无引擎标记且 > _batch_hi(max_length) 词 → refined（阈值与 batch 上界单一来源联动）。
    语言限制（W11）：count_words 按空格切分，无空格中文不走长度兜底（中文精修通常带标记或显式 tier）。
    """
    if explicit_tier in ("refined", "batch", "asset", "variant"):
        return explicit_tier
    upper = str(prompt or "").upper()
    if (video and video.get("shots")) or "NON-IP" in upper or "FINAL FRAME" in upper:
        return "refined"
    if count_words(prompt) > _batch_hi(max_length):
        return "refined"
    return "batch"


def evaluate(
    prompt: str,
    video: dict | None,
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
    prev_final_frame: str | None = None,
    character_list: list | None = None,
    length_strict: bool = True,
    enable_advice: bool = True,
) -> dict:
    """返回 {score: 0-100, checks: {...}, tier, violations}。

    tier 层级（Higgsfield P0）：
    - batch：en 100-400 词 / zh 120-2000 字符
    - refined：en 下界自适应（≤min(500, budget//6)）~ 5000 词（DEEP P0-1 词数刻度；max_length 是字符裁剪预算不参与上界判据）/ zh 500 字符至 max_length
    violations：缺席角色 -10 / swap 被替换 -10 / refined 缺尾行 -10 / 缺 Audio 块 -5 /
    continuity_break -5（跨镜承接，评审修订版实体级算法）/ block_coverage -5（refined 块覆盖，自渲染口径）/
    lock-gated 规则 -5（否定感知，默认 3 条启用）。
    """
    # P2-3 空输入契约：空/纯空白 → 显式 0 分 + empty 标记（API 层已 422，引擎内部不产生白送分假分数）。
    # 评审 Minor：checks 形状与正常路径对齐（form/elements/fidelity/violations_detail/tier_auto 等键齐全），
    # advice 按 language 输出而非硬编码中文。
    if not str(prompt or "").strip():
        _empty_lang = str(language or "").lower()
        _empty_advice = (
            "空提示词，无法评估" if _empty_lang.startswith("zh") else "empty prompt, cannot evaluate"
        )
        return {
            "score": 0.0,
            "checks": {
                "empty": True, "tier": "batch", "tier_auto": None, "form": "asset",
                "length": False, "words": 0, "length_band": [0, 0], "length_points": 0.0,
                "elements": {}, "elements_detail": {}, "elements_score": 0.0,
                "has_shot": False, "has_camera": False, "has_motion": False,
                "fidelity": 1.0, "fidelity_method": "none",
                "violations": {}, "violations_detail": {},
                "block_coverage": None, "timeline_hits": None, "timing_diff": None,
                "continuity_hits": 0, "continuity_total": 0,
                "continuity_ratio": None, "continuity_method": None,
            },
            "tier": "batch",
            "violations": {},
            "advice": [_empty_advice] if enable_advice else [],
            "evaluator_version": _EVALUATOR_VERSION,
            "assets": _asset_fingerprint(),
        }

    checks = {}
    requested_tier = tier
    tier = detect_tier(prompt, video, explicit_tier=requested_tier, max_length=max_length)
    checks["tier"] = tier
    # P1-2：tier 推断来源（marker/length/none）+ 长度兜底进 refined 时豁免 missing_trailer
    _upper0 = str(prompt or "").upper()
    marker_based = bool(video and video.get("shots")) or "NON-IP" in _upper0 or "FINAL FRAME" in _upper0
    length_fallback = (
        tier == "refined"
        and requested_tier is None
        and not marker_based
        and count_words(prompt) > _batch_hi(max_length)
    )
    checks["tier_auto"] = "length" if length_fallback else ("marker" if marker_based and requested_tier is None else None)
    trailer_waiver = length_fallback

    # 1) 长度层级（batch/refined/asset/variant 分带；P2-1 asset/variant 语料形态层）
    words = count_words(prompt)
    # P2-2：RU 与 zh 同样按字符刻度（短卡形态常见，词数下界过严），其余语言按词数
    measure = len(str(prompt)) if language in ("zh", "ru") else words
    # form 形态标签：显式 tier=asset/variant，或短卡（<100 词/字）推断为 asset；其余 regular
    # （评审复验 W1-新：中文无空格 count_words≈1，必须用 measure（zh=字符数）判定，否则整语言误判 asset）
    if tier in ("asset", "variant"):
        form = tier
    elif measure < 100:
        form = "asset"
    else:
        form = "regular"
    checks["form"] = form
    if language in ("zh", "ru"):
        if tier == "refined":
            lo, hi = 500, (max_length or 5000)
        elif tier == "asset":
            lo, hi = 40, 1900
        elif tier == "variant":
            lo, hi = 80, 2000
        else:
            lo, hi = 120, 2000
    else:
        if tier == "refined":
            # DEEP P0-1：精修层 500-5,000 词（词数刻度）。max_length 为字符裁剪预算（optimizer 先裁后评），
            # 不参与 refined 上界判据。下界保持自适应（评审 C1）：min(500, max(150, budget//6)) 防区间坍缩
            lo = min(500, max(150, (max_length or 5000) // 6))
            hi = 5000
        elif tier == "asset":
            lo, hi = 20, 950
        elif tier == "variant":
            hi = _batch_hi(max_length)  # 评审 Minor：复用单一来源，消除内联复制漂移
            lo, hi = 50, hi
        else:
            # W4：batch 上界与 max_length 联动（默认 1800 → 400 零回归）；W3 封顶 833
            hi = min(max(400, (max_length or 1800) // 6), 833)
            lo, hi = 100, hi
    length_ok = lo <= measure <= hi
    checks["length"] = length_ok
    checks["words"] = words
    checks["length_band"] = [lo, hi]
    # P1-2 长度梯度：length_strict=False（评测口径）按接近度 0-20；True（引擎候选口径）0/20 二值
    if length_strict:
        length_points = 20 if length_ok else 0
    else:
        bandwidth = max(1, hi - lo)
        if length_ok:
            length_points = 20.0
        else:
            dist = min(abs(measure - lo), abs(measure - hi))
            length_points = round(20.0 * max(0.0, 1.0 - dist / bandwidth), 1)
    checks["length_points"] = length_points

    # 5) Higgsfield violations（词边界/整名匹配，字段为空时 N/A 不误扣；[ABSENT]/<<<>>> 标记区段先剥离防自罚分）
    text = str(prompt)
    upper_text = text.upper()
    violations: dict[str, int] = {}
    excluded = (video or {}).get("excluded_characters") or []
    pairs = (video or {}).get("no_swap_pairs") or []
    reference_names = [str(item).strip() for item in excluded if str(item or "").strip()]
    for pair in pairs:
        if isinstance(pair, dict):
            pair_names = (pair.get("from"), pair.get("to"))
        elif isinstance(pair, (list, tuple)) and len(pair) == 2:
            pair_names = pair
        else:
            continue
        reference_names.extend(str(item).strip() for item in pair_names if str(item or "").strip())
    _known = list(reference_names) + [
        str(c).strip() for c in (character_list or []) if str(c or "").strip()
    ]
    # excluded + swap + character_list 并集（_contains_name 长名覆盖守卫 + [ABSENT] 豁免判定共用；
    # 评审 Critical：[ABSENT] 对 roster 角色的豁免必须能剥离/识别，故剥离集也使用并集）
    known_names = list(dict.fromkeys(_known))
    body_text = _strip_reference_markers(text, known_names)
    if excluded:
        hit = [e for e in excluded if _contains_name(body_text, e, known_names)]
        if hit:
            violations["excluded_present"] = -10
            checks["excluded_hits"] = hit
    if pairs:
        # 双形态兼容：契约规范形态二元组 [from, to] 与引擎对象形态 {from,to} 均读 from 侧；非法形态跳过防 AttributeError
        hit = []
        for p in pairs:
            if isinstance(p, dict):
                from_name = p.get("from")
            elif isinstance(p, (list, tuple)) and len(p) == 2:
                from_name = p[0]
            else:
                continue
            if _contains_name(body_text, from_name, known_names):
                hit.append(p)
        if hit:
            violations["swap_source_present"] = -10
            checks["swap_hits"] = hit
    if tier == "refined" and "NON-IP" not in upper_text and not trailer_waiver:
        # 质量评估 P1-2：真实精修语料以控制段（Duration/Aspect/连续长镜头/分镜标记/终态块）等价表达 trailer
        # 预期，识别控制段形态即视为有 trailer 预期，不强制 NON-IP 字面量（引擎自产尾行仍为 NON-IP，不受影响）
        _TRAILER_EQUIV = (
            "DURATION:", "ASPECT RATIO", "ASPECT:", "ONE CONTINUOUS SHOT",
            "CUT 1", "CUT 2", "[SHOT", "FINAL FRAME", "STILLNESS LOCK", "SCENE NOTE",
        )
        if not any(k in upper_text for k in _TRAILER_EQUIV):
            violations["missing_trailer"] = -10
    lower_text = text.lower()
    # 缺 Audio 块：refined 尾行自带 `{audio} only.`（meta.audio 非空即满足）；batch 层改为「显式音频需求」判定——
    # 仅当正文含音频意图词或 meta 显式声明音频时才要求音频词；纯视觉/静态形态默认 N/A 不扣分（质量评估 P1-1 修复）
    _SILENCE_WORDS = ("silent", "no sound", "无声", "静音", "无音效")
    _AUDIO_INTENT_WORDS = (
        "sfx", "sound effects", "sound design", "soundscape", "ambient audio",
        "audio cue", "diegetic", "music", "score", "dialogue", "vocal",
        "voiceover", "narration", "音效", "配乐", "声音", "对话", "旁白", "音轨", "音频",
    )
    audio_field = str((video or {}).get("audio") or "").strip()
    audio_layers = (video or {}).get("audio_layers")
    if tier == "refined" and isinstance(audio_layers, dict):
        # REQ-3.4 判定表仅 refined 生效（Audio 段真实渲染进尾行）；batch 无尾行，走正文音频词检查，
        # 否则 batch 带 audio_layers 而正文无音频词会假阴性（评审 W1）
        has_audio = any(
            bool(str(audio_layers.get(key) or "").strip())
            for key in ("environment", "sfx", "dialogue")
        )
    elif tier == "refined":
        has_audio = bool(audio_field) or any(k in lower_text for k in ("sfx", "sound", "audio", "music", "score"))
    else:
        if any(k in lower_text for k in _SILENCE_WORDS):
            has_audio = False
        elif audio_field or any(k in lower_text for k in _AUDIO_INTENT_WORDS):
            has_audio = True
        else:
            has_audio = None  # 纯视觉/静态形态：无显式音频需求，N/A 不扣分
    if has_audio is False:
        violations["missing_audio"] = -5

    # 6) Round3 Batch A T2 — 确定性 FAIL CHECK（纯结构/数学判定，无 LLM）：
    # timeline_missing：shots≥2 时正文（标记区剥离后）缺 [SHOT N]/[HARD CUT] 切分标记 → -5
    # timing_break：shots≥2 时 beats[].time 区间端点最大值超出 shot.duration+2s 容差 → -5
    shots = (video or {}).get("shots") or []
    timing_count = 0
    timing_total = 0.0
    if isinstance(shots, list) and len(shots) >= 2:
        # 引用协议标记区已剥离（<<<...>>>/[ABSENT] 内嵌的 [SHOT 不计数，评审 I1）；真实切分标记保留
        body_upper = body_text.upper()
        timeline_hits = ("[SHOT" in body_upper) or ("[HARD CUT" in body_upper)
        checks["timeline_hits"] = timeline_hits
        if not timeline_hits:
            violations["timeline_missing"] = -5

        timing_diff = None
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            duration = shot.get("duration")
            beats = shot.get("beats") or []
            if not isinstance(beats, list):
                continue
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                time_span = str(beat.get("time") or "").strip()
                parsed = _parse_time_span(time_span)
                if parsed is None:
                    continue
                end_seconds = max(parsed)
                try:
                    duration_f = float(duration) if duration is not None and str(duration).strip() != "" else 0.0
                except (TypeError, ValueError):
                    continue
                diff = end_seconds - (duration_f + 2.0)
                if timing_diff is None or diff > timing_diff:
                    timing_diff = diff
                if diff > 0:
                    timing_count += 1
                    timing_total += diff
                    violations["timing_break"] = -5
        checks["timing_diff"] = round(timing_diff, 2) if timing_diff is not None else None
    else:
        checks["timeline_hits"] = None
        checks["timing_diff"] = None

    # 7) Round3 Batch B — 跨镜承接保真（实体级；引用标记剥离后判定；无 prev_final_frame 跳过零回归）
    if prev_final_frame:
        absent_names = _extract_absent_names(text, known_names)
        continuity_ok, continuity_checks = _check_continuity(body_text, prev_final_frame, character_list or [], absent_names)
        checks.update(continuity_checks)
        if not continuity_ok:
            violations["continuity_break"] = -5
    else:
        checks.update({
            "continuity_hits": 0, "continuity_total": 0,
            "continuity_ratio": None, "continuity_method": None,
        })

    # 8) Round3 Batch C — 块覆盖度（refined 专属，引擎自渲染口径）
    # 分母 = meta.blocks 非空块数，分子 = 渲染串中命中块标记数（统一正则，行首标题+冒号）；
    # 与语料分族统计解耦（评审 Critical-2：语料众数 8/12 卡阈值必误报）。
    blocks = clean_blocks((video or {}).get("blocks"))
    block_hits = 0
    block_ratio = 0.0
    if tier == "refined" and blocks:
        non_empty = list(blocks)
        if non_empty:
            rendered_names = rendered_block_names(prompt)
            hits = sum(1 for k in non_empty if k in rendered_names)
            ratio = hits / len(non_empty)
            block_hits, block_ratio = hits, ratio
            checks["block_coverage"] = {"hit": block_hits, "total": len(non_empty), "ratio": round(block_ratio, 3)}
            min_ratio = float((_gated_rules().get("coverage") or {}).get("min_ratio", 0.8))
            if block_ratio < min_ratio:
                violations["block_coverage"] = -5
        else:
            checks["block_coverage"] = None
    else:
        checks["block_coverage"] = None

    # 9) Round3 Batch C — lock-gated 启发式（否定感知；enabled_rules 默认 3 条；batch 不启用）
    _apply_gated_rules(body_text, tier, violations, checks)
    checks["violations"] = violations
    # P0-3 违规分级量化：violations_detail 并行结构（顶层 violations 保持 dict[str,int] 计分兼容）
    violations_detail: dict = {}
    for _key, _val in violations.items():
        violations_detail[_key] = {"penalty": _val, "count": 1, "detail": None}
    if "timing_break" in violations:
        violations_detail["timing_break"] = {
            "penalty": -5,
            "count": timing_count,
            "detail": {
                "max_diff": round(timing_diff, 2) if timing_diff is not None else None,
                "total_diff": round(timing_total, 2),
            },
        }
    if "block_coverage" in violations:
        violations_detail["block_coverage"] = {
            "penalty": -5,
            "count": 1,
            "detail": {"hit": block_hits, "total": len(non_empty) if tier == "refined" and blocks else 0, "ratio": round(block_ratio, 3)},
        }
    checks["violations_detail"] = violations_detail

    # 2) 六要素（关键词资产 prompt_engine_core/knowledge/element_keywords.json，P1-4 外置；
    #    en/zh/ru 任一语言命中即算——P2-2 多语种；部分命中 score=min(1, 命中词数/3)——P1-1 区分度）
    lower = str(prompt).lower()
    elements_detail: dict = {}
    element_keywords, _kw_from_asset = load_element_keywords()
    for _elem, _langs in element_keywords.items():
        _hits: list[str] = []
        for _lang, _words in _langs.items():
            for _w in _words:
                _w = str(_w or "").strip()
                if not _w or _w in _hits:
                    continue
                if re.search(r"[\u0400-\u04ff]", _w):
                    # 西里尔词左侧边界（评审 Minor：фон 不得命中 телефон/микрофон；
                    # 词形表已收录变格形态，右侧不设限）
                    if _CYRILLIC_BOUNDARY_RE(_w).search(lower):
                        _hits.append(_w)
                elif re.search(r"[\u4e00-\u9fff]", _w):
                    if _w in lower:
                        _hits.append(_w)
                elif (
                    _contains_word(lower, _w)
                    or _contains_word(lower, _w + "s")
                    or _contains_word(lower, _w + "es")
                ):
                    _hits.append(_w)
        elements_detail[_elem] = {
            "hit": bool(_hits), "words": _hits[:8], "score": round(min(1.0, len(_hits) / 3.0), 3),
        }
    elements = {k: v["hit"] for k, v in elements_detail.items()}
    checks["elements"] = elements
    checks["elements_detail"] = elements_detail
    checks["elements_score"] = round(sum(v["score"] for v in elements_detail.values()) / len(elements_detail), 3)

    # 3) 镜头字段（结构化 video；缺失时文本级兜底——质量评估 P0-1：纯文本评测不再被 58.3 硬顶）
    _TXT_SHOT = ("shot", "cut", "establishing", "close-up", "closeup", "wide", "overhead",
                 "tracking", "dolly", "zoom", "pan", "tilt", "slow-motion", "特写", "全景", "俯拍", "跟拍", "推移")
    _TXT_CAMERA = ("camera", "lens", "angle", "perspective", "viewpoint", "镜头", "机位", "视角", "广角", "长焦")
    # P0-4：运镜词表只保留镜头运动词（主体运动 walking/running/moving 不再计运镜）
    _TXT_MOTION = ("slow-motion", "pan", "tilt", "tracking", "dolly", "zoom", "crane", "handheld",
                   "drift", "swirl", "whip", "运镜", "摇镜", "推镜", "拉镜", "跟拍", "推移", "旋转", "慢动作")
    _has_txt = lambda toks: any(_contains_word(text, t) for t in toks)  # W4：词边界，子串兜底会误击 pandemic/companion(pan)
    checks["has_shot"] = bool(video and video.get("shot")) or _has_txt(_TXT_SHOT)
    checks["has_camera"] = bool(video and video.get("camera")) or _has_txt(_TXT_CAMERA)
    checks["has_motion"] = bool(video and video.get("motion_intensity")) or _has_txt(_TXT_MOTION)

    # 4) 保真三路径（P0-1/P2-5）：跨语言翻译模式（门控）/ 中文 2-gram 归一 / 英文实体词干命中
    fidelity = 1.0
    checks["fidelity_method"] = "none"
    if source_prompt:
        if _detect_translation_mode(source_prompt, prompt):
            fidelity = _cross_lingual_fidelity(source_prompt, prompt)
            checks["fidelity_method"] = "cross_lingual"
        else:
            zh_chars = re.findall(r"[\u4e00-\u9fff]{2,}", source_prompt)
            if zh_chars:
                src_grams = _zh_fidelity_grams(source_prompt)
                if src_grams:
                    hit = len(src_grams & _zh_fidelity_grams(prompt))
                    fidelity = round(hit / len(src_grams), 3)
                checks["fidelity_method"] = "zh2gram"
            else:
                tokens = _extract_continuity_tokens(source_prompt)
                if tokens:
                    # W3：词形归一（robot→robots/run→runs）——全词边界对复数/时态假阴性，保真路径轻量容忍
                    prompt_stems = _en_stems(prompt)
                    hits = [t for t in tokens if _contains_word(prompt, t) or _stem_en(t) in prompt_stems]
                    fidelity = round(len(hits) / len(tokens), 3)
                checks["fidelity_method"] = "wordlist"
    checks["fidelity"] = fidelity

    score = (
        length_points
        + (checks["elements_score"] * 30)
        + (20 if checks["has_shot"] else 0)
        + (15 if checks["has_camera"] else 0)
        + (15 if checks["has_motion"] else 0)
        + (fidelity * 20)
    ) / 1.2
    score += sum(violations.values())
    return {
        "score": round(max(0, min(100, score)), 1),
        "checks": checks,
        "tier": tier,
        "violations": violations,
        "advice": _build_advice(prompt, checks, violations, language) if enable_advice else [],
        "evaluator_version": _EVALUATOR_VERSION,
        "assets": _asset_fingerprint(),
    }


# P2-3：可解释建议（纯规则，中英双语按 language；enable_advice=False 关闭）——违规键 → (zh, en) 文案
_ADVICE_VIOLATION_TEXT = {
    "excluded_present": ("正文出现了禁止角色", "excluded character appears in body"),
    "swap_source_present": ("检测到需替换的角色源名", "swap source character name detected"),
    "missing_trailer": ("精修层缺少尾行/控制段（NON-IP 或 Duration/Cut 标记）", "refined prompt missing trailer/control block (NON-IP or Duration/Cut marker)"),
    "missing_audio": ("缺少音频描述（silent/无音效或显式音频意图）", "missing audio description (silent or explicit audio intent)"),
    "timeline_missing": ("多镜头未使用 [SHOT N]/[HARD CUT] 切分标记", "multi-shot prompt missing [SHOT N]/[HARD CUT] markers"),
    "timing_break": ("beats 时间超出 shot 时长容差", "beat timing exceeds shot duration tolerance"),
    "continuity_break": ("跨镜承接实体丢失", "continuity entities lost from previous frame"),
    "block_coverage": ("精修块覆盖不足", "refined block coverage below threshold"),
    "exposure_break": ("曝光一致性被破坏", "exposure consistency broken"),
    "silhouette_break": ("剪影一致性被破坏", "silhouette consistency broken"),
    "dead_center": ("主体被居中构图", "dead-center composition"),
    "warm_light_leak": ("出现暖光漏光", "warm light leak detected"),
    "style_contamination": ("风格污染", "style contamination"),
    "skin_guard": ("面部/皮肤细节失守", "face/skin detail guard failed"),
    "eye_line": ("视线未对镜头", "gaze not toward camera"),
}

# P2-3 补充：六要素中文标签（zh advice 可读性）
_ELEMENT_ZH_LABELS = {
    "subject": "主体", "action": "动作", "environment": "环境",
    "lighting": "光线", "color": "色彩", "style": "风格",
}


def _build_advice(prompt: str, checks: dict, violations: dict, language: str) -> list[str]:
    """纯规则建议生成：长度带外 + 缺失要素 + 镜头维度 + 违规逐条映射（zh 按 language 参数）。"""
    lang = str(language or "").lower()
    zh = lang.startswith("zh")
    ru = lang.startswith("ru")
    advice: list[str] = []

    if not checks.get("length"):
        band = checks.get("length_band") or []
        words = checks.get("words") or 0
        # 评审 Minor：RU 与 zh 同按字符刻度（evaluate 长度带口径一致），文案区分字/词
        char_scale = zh or ru
        measure = len(str(prompt)) if char_scale else words
        if len(band) == 2:
            lo, hi = band
            if zh:
                advice.append(f"长度 {measure} 字，建议带 {lo}-{hi}")
            elif ru:
                advice.append(f"length {measure} chars is outside suggested band {lo}-{hi}")
            else:
                advice.append(f"length {measure} words is outside suggested band {lo}-{hi}")

    for elem, detail in (checks.get("elements_detail") or {}).items():
        if not detail.get("score"):
            label = _ELEMENT_ZH_LABELS.get(elem, elem)
            advice.append(f"缺少要素：{label}" if zh else f"missing element: {label}")

    if not checks.get("has_shot"):
        advice.append("未检测到镜头/景别描述" if zh else "no shot/framing description detected")
    if not checks.get("has_camera"):
        advice.append("未检测到机位/视角描述" if zh else "no camera angle/viewpoint description detected")
    if not checks.get("has_motion"):
        advice.append("未检测到运镜描述" if zh else "no camera motion description detected")

    for key, _val in sorted((violations or {}).items(), key=lambda kv: abs(kv[1]), reverse=True):
        text = _ADVICE_VIOLATION_TEXT.get(key)
        if text:
            advice.append(text[0] if zh else text[1])
        else:
            advice.append(f"违反规则：{key}" if zh else f"rule violation: {key}")
    return advice


def select_best(
    candidates: list[tuple[str, dict]],
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
    prev_final_frame: str | None = None,
    character_list: list | None = None,
    length_strict: bool = True,
    detail: bool = False,
) -> tuple[str, dict, float] | tuple[str, dict, float, list[dict]]:
    """多候选择优：返回 (prompt, video_meta, score)，分数最高者优先；
    同分时违规总惩罚量小者胜（P0-3：sum(abs(penalty))；1 个 -10 与 2 个 -5 惩罚量相等并列），
    仍同分取先出现者（稳定排序）。
    detail=True 返回 4 元组 (prompt, meta, score, candidates_info)——每候选
    checks/violations/advice/violations_penalty 明细（按分降序），供运营解释「为什么选它」。"""
    scored: list[tuple[float, int, str, dict, dict]] = []
    for prompt, meta in candidates:
        info = evaluate(
            prompt, meta, source_prompt=source_prompt, language=language, tier=tier,
            max_length=max_length, prev_final_frame=prev_final_frame, character_list=character_list,
            length_strict=length_strict,
        )
        score = float(info["score"])
        penalty = sum(abs(v) for v in (info.get("violations") or {}).values())
        scored.append((score, penalty, prompt, meta, info))
    scored.sort(key=lambda x: (-x[0], x[1]))  # 稳定排序：同分同惩罚保留先出现者
    if not scored:
        return ("", {}, 0.0, []) if detail else ("", {}, 0.0)
    if detail:
        infos = [
            {
                "prompt": p, "meta": m, "score": sc,
                "checks": i.get("checks"), "violations": i.get("violations"),
                "advice": i.get("advice"), "violations_penalty": pen,
            }
            for sc, pen, p, m, i in scored
        ]
        return scored[0][2], scored[0][3], scored[0][0], infos
    return scored[0][2], scored[0][3], scored[0][0]

# video-corpus-expansion 组5：failure_patterns.json pattern → evaluate() violations 键 映射
# （gated rule 仅 refined 层启用，未启用的 rule 对应 tag 标记 covered=False，不污染召回分母）
_TAG_TO_VIOLATION = {
    "exposure_break": "exposure_break",
    "silhouette_break": "silhouette_break",
    "dead_center_composition": "dead_center",
    "warm_light_leak": "warm_light_leak",
    "style_contamination": "style_contamination",
    "face_skin_detail_fail": "skin_guard",
    "gaze_camera_fail": "eye_line",
    "absent_character_appears": "excluded_present",
    "character_swap": "swap_source_present",
    "timeline_missing": "timeline_missing",
    "audio_block_missing": "missing_audio",
    "missing_audio": "missing_audio",
    "missing_trailer": "missing_trailer",
    "timing_break": "timing_break",
    "continuity_break": "continuity_break",
    "block_coverage": "block_coverage",
}


def evaluate_negatives(
    samples: list[dict],
    tag_to_violation: dict | None = None,
    **eval_kwargs,
) -> dict:
    """负样本校验模式（video-corpus-expansion 组5）：按 failure_tags 与 evaluate() 触发违规匹配。

    每条样本：{prompt_text, failure_tags, language?, tier?, meta?, prev_final_frame?, character_list?}。
    输出每类失败模式 {recall, hits, misses, false_positives}：
    - hits：样本预期该 tag 且 evaluate 触发对应违规键
    - misses：样本预期该 tag 但未触发（漏检）
    - false_positives：样本触发了违规键但该样本预期 tags 均不映射它（误报事件，按样本×键去重）
    - covered=False：tag 无违规键映射（如 gated 未启用的规则），recall=None，不进召回分母

    常规评分路径零影响：独立入口，不改 evaluate/select_best 内部行为。
    """
    mapping = dict(tag_to_violation or _TAG_TO_VIOLATION)
    reverse: dict[str, list[str]] = {}
    for tag, vkey in mapping.items():
        reverse.setdefault(vkey, []).append(tag)
    # gated 规则动态覆盖：lock_triggers 中存在但未启用的规则，其 tag 不可判定 → covered=False
    rules = _gated_rules()
    gated_enabled = rules.get("enabled") or set()
    disabled_gated = (set((rules.get("triggers") or {}).keys()) - gated_enabled)
    uncovered_tags = {t for t, v in mapping.items() if v in disabled_gated}

    stats: dict[str, dict] = {}
    details: list[dict] = []
    total_fp = 0
    for sample in samples:
        text = str(sample.get("prompt_text") or "")
        if not text:
            continue
        sid = str(sample.get("id") or "?")
        expected = {str(t) for t in (sample.get("failure_tags") or [])}
        meta = sample.get("meta") if isinstance(sample.get("meta"), dict) else {}
        info = evaluate(
            text,
            meta,
            source_prompt=str(sample.get("source_prompt") or ""),
            language=str(sample.get("language") or "en"),
            tier=sample.get("tier"),
            prev_final_frame=sample.get("prev_final_frame"),
            character_list=sample.get("character_list"),
            **eval_kwargs,
        )
        actual = set(info["violations"].keys())
        expected_vkeys = {mapping[t] for t in expected if t in mapping}
        # 仅统计可判定（covered）的漏检；未启用 gated 规则的 tag 由 uncovered_tags 单独报告
        missed = sorted(
            t for t in expected
            if t in mapping and t not in uncovered_tags and mapping[t] not in actual
        )
        fps = sorted(v for v in actual if v not in expected_vkeys)
        total_fp += len(fps)

        for tag in expected:
            st = stats.setdefault(
                tag, {"hits": 0, "misses": 0, "false_positives": 0, "covered": tag in mapping and tag not in uncovered_tags}
            )
            if tag in mapping and tag not in uncovered_tags:
                if mapping[tag] in actual:
                    st["hits"] += 1
                else:
                    st["misses"] += 1
        # FP 事件归属到映射该违规键的 tag（该 tag 存在即累计；无归属不影响 totals）
        for vkey in fps:
            for tag in reverse.get(vkey, []):
                if tag in stats:
                    stats[tag]["false_positives"] += 1
                    break  # P1-5：样本×违规键只归属一次（多 tag 同键不重复累计；共享键的 tag 间归属为聚合性，totals 可靠）
        details.append({
            "id": sid,
            "tags": sorted(expected),
            "triggered": sorted(actual),
            "missed": missed,
            "false_positives": fps,
        })

    patterns = {}
    for tag, st in sorted(stats.items()):
        denom = st["hits"] + st["misses"]
        patterns[tag] = {
            "recall": round(st["hits"] / denom, 3) if st["covered"] and denom else None,
            "hits": st["hits"],
            "misses": st["misses"],
            "false_positives": st["false_positives"],
            "covered": st["covered"],
            "violation_key": mapping.get(tag),
        }
    covered = [p for p in patterns.values() if p["covered"]]
    uncovered = [tag for tag, p in patterns.items() if not p["covered"]]
    uncovered += sorted(t for t in uncovered_tags if t not in stats)
    return {
        "patterns": patterns,
        "totals": {
            "samples": len(samples),
            "evaluated": len(details),
            "recall": round(
                sum(p["hits"] for p in covered) / max(1, sum(p["hits"] + p["misses"] for p in covered)), 3
            ) if covered else None,
            "hits": sum(p["hits"] for p in covered),
            "misses": sum(p["misses"] for p in covered),
            "false_positives": total_fp,
            "uncovered_tags": uncovered,
        },
        "details": details,
    }
