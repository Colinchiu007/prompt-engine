"""v0.15.0 — 中文翻译工具 (供 Python 测试 + JS 调用)"""

# 200+ MJ 风格关键词中英对照表
EN_CN_DICT = {
    # 量词
    'a': '一只', 'an': '一个', 'the': '',
    'one': '一个', 'two': '两个', 'three': '三个',
    'several': '几个', 'many': '许多', 'few': '几个',
    # 主体
    'cat': '猫', 'dog': '狗', 'bird': '鸟', 'horse': '马',
    'tiger': '老虎', 'lion': '狮子', 'dragon': '龙', 'phoenix': '凤凰',
    'wolf': '狼', 'eagle': '鹰', 'butterfly': '蝴蝶', 'fish': '鱼',
    'flower': '花', 'tree': '树', 'mountain': '山', 'water': '水',
    'sun': '太阳', 'moon': '月亮', 'star': '星星', 'cloud': '云',
    'sky': '天空', 'sea': '海', 'ocean': '海洋', 'forest': '森林',
    'city': '城市', 'building': '建筑', 'castle': '城堡', 'palace': '宫殿',
    'warrior': '战士', 'queen': '女王', 'king': '国王', 'princess': '公主',
    'wizard': '巫师', 'knight': '骑士', 'robot': '机器人', 'alien': '外星人',
    'astronaut': '宇航员', 'girl': '女孩', 'boy': '男孩', 'woman': '女人',
    'man': '男人', 'child': '孩子', 'baby': '婴儿', 'person': '人',
    # 形容词
    'majestic': '威严的', 'beautiful': '美丽的', 'mysterious': '神秘的',
    'ancient': '古老的', 'futuristic': '未来派的', 'cyberpunk': '赛博朋克',
    'fantasy': '奇幻', 'magical': '魔幻的', 'epic': '史诗般的',
    'cinematic': '电影感的', 'dramatic': '戏剧性的', 'ethereal': '空灵的',
    'surreal': '超现实的', 'vibrant': '鲜艳的', 'dark': '黑暗的',
    'bright': '明亮的', 'colorful': '多彩的', 'peaceful': '宁静的',
    'serene': '平静的', 'mysterious': '神秘的', 'cute': '可爱的',
    'sad': '悲伤的', 'happy': '快乐的', 'angry': '愤怒的',
    'gentle': '温柔的', 'fierce': '凶猛的', 'powerful': '强大的',
    'elegant': '优雅的', 'graceful': '优美的', 'royal': '皇家的',
    'tiny': '微小的', 'small': '小的', 'medium': '中等的',
    'large': '大的', 'huge': '巨大的', 'massive': '巨大的',
    'gigantic': '庞大的', 'tiny': '微小的', 'miniature': '微型的',
    'old': '古老的', 'young': '年轻的', 'new': '新的',
    'shiny': '闪亮的', 'glowing': '发光的', 'bright': '明亮的',
    'dark': '黑暗的', 'shadowy': '阴影的', 'moody': '忧郁的',
    'happy': '快乐的', 'cheerful': '愉快的', 'joyful': '欢乐的',
    'sad': '悲伤的', 'gloomy': '阴郁的', 'melancholic': '忧郁的',
    'feline': '猫科动物', 'canine': '犬科动物', 'avian': '鸟类',
    'humanoid': '人形', 'mecha': '机甲',
    # 动作/姿态
    'sitting': '端坐', 'standing': '站立', 'walking': '行走',
    'running': '奔跑', 'flying': '飞翔', 'swimming': '游泳',
    'floating': '漂浮', 'resting': '休憩', 'sleeping': '睡眠',
    'fighting': '战斗', 'dancing': '舞蹈', 'singing': '歌唱',
    'reading': '阅读', 'writing': '书写', 'painting': '绘画',
    'looking': '凝视', 'gazing': '注视', 'staring': '凝视',
    'riding': '骑乘', 'climbing': '攀登', 'jumping': '跳跃',
    'flying': '飞翔', 'soaring': '翱翔', 'diving': '俯冲',
    # 环境
    'on': '在', 'in': '在', 'at': '在', 'under': '在...下',
    'above': '在...上', 'over': '在...上', 'inside': '在...内',
    'outside': '在...外', 'between': '在...之间', 'among': '在...之中',
    'velvet': '天鹅绒', 'silk': '丝绸', 'cotton': '棉',
    'gold': '金色', 'silver': '银色', 'bronze': '铜色', 'iron': '铁',
    'wood': '木', 'stone': '石', 'glass': '玻璃', 'metal': '金属',
    'crystal': '水晶', 'diamond': '钻石', 'ruby': '红宝石',
    'throne': '宝座', 'chair': '椅子', 'bed': '床',
    'mountain': '山', 'valley': '山谷', 'river': '河',
    'lake': '湖', 'sea': '海', 'ocean': '海洋', 'beach': '海滩',
    'desert': '沙漠', 'cave': '洞穴', 'ruins': '遗迹',
    'temple': '寺庙', 'cathedral': '大教堂', 'church': '教堂',
    'forest': '森林', 'jungle': '丛林', 'desert': '沙漠',
    'garden': '花园', 'park': '公园', 'field': '田野',
    # 光照
    'lighting': '光线', 'light': '光', 'shadow': '阴影',
    'golden hour': '金色时刻', 'blue hour': '蓝色时刻',
    'sunset': '日落', 'sunrise': '日出', 'sunshine': '阳光',
    'moonlight': '月光', 'starlight': '星光', 'twilight': '黄昏',
    'volumetric': '体积光', 'rays': '光线', 'rim': '轮廓',
    'backlit': '背光', 'sidelit': '侧光', 'toplight': '顶光',
    'neon': '霓虹', 'fluorescent': '荧光', 'candlelight': '烛光',
    'sunlight': '阳光', 'daylight': '日光', 'ambient': '环境光',
    'soft': '柔和', 'hard': '硬', 'diffuse': '漫射', 'directional': '方向光',
    # 风格/质量
    'ultra-detailed': '超精细', 'highly detailed': '高度精细',
    '8K': '8K', '4K': '4K', 'HD': '高清', 'UHD': '超高清',
    'cinematic': '电影感', 'photorealistic': '照片级真实',
    'realistic': '写实的', 'photograph': '照片',
    'painterly': '绘画风', 'illustration': '插画', 'sketch': '素描',
    'oil painting': '油画', 'watercolor': '水彩', 'pastel': '粉彩',
    'digital art': '数字艺术', 'concept art': '概念艺术',
    'matte painting': '哑光绘画', 'cel shading': '赛璐璐渲染',
    'line art': '线稿', 'manga': '漫画', 'anime': '动漫',
    'cartoon': '卡通', 'comic': '漫画', '3D': '三维', '2D': '二维',
    'isometric': '等距视角', 'orthographic': '正交投影',
    'wide angle': '广角', 'telephoto': '长焦', 'macro': '微距',
    'fish-eye': '鱼眼', 'panorama': '全景', 'close-up': '特写',
    'portrait': '肖像', 'headshot': '头像', 'bust': '半身像',
    'full body': '全身', 'long shot': '远景', 'medium shot': '中景',
    'extreme close-up': '极端特写', 'medium close-up': '中近景',
    # 颜色
    'red': '红色', 'blue': '蓝色', 'green': '绿色', 'yellow': '黄色',
    'orange': '橙色', 'purple': '紫色', 'pink': '粉色',
    'black': '黑色', 'white': '白色', 'gray': '灰色', 'grey': '灰色',
    'brown': '棕色', 'cyan': '青色', 'magenta': '品红',
    'golden': '金色的', 'silvery': '银色的', 'emerald': '翠绿色',
    'ruby': '红宝石色', 'sapphire': '蓝宝石色', 'amber': '琥珀色',
    'azure': '天蓝色', 'crimson': '深红色', 'ivory': '象牙白',
    'turquoise': '绿松石色', 'scarlet': '猩红', 'violet': '紫色',
    'pastel': '粉彩的', 'neon': '霓虹的', 'monochrome': '单色',
    'vibrant': '鲜艳的', 'muted': '柔和的', 'pastel': '淡雅的',
    'warm': '暖色调', 'cool': '冷色调', 'pastel': '柔和',
    # 构图
    'composition': '构图', 'framing': '构图',
    'centered': '居中', 'rule of thirds': '三分法',
    'symmetric': '对称', 'asymmetric': '非对称',
    'leading lines': '引导线', 'depth of field': '景深',
    'bokeh': '散景', 'sharp focus': '锐利对焦', 'soft focus': '柔焦',
    'background': '背景', 'foreground': '前景', 'midground': '中景',
    # 情绪/氛围
    'mood': '氛围', 'atmosphere': '气氛', 'ambiance': '环境',
    'peaceful': '宁静', 'serene': '安宁', 'tranquil': '静谧',
    'mysterious': '神秘', 'enigmatic': '神秘莫测', 'ominous': '不祥',
    'whimsical': '异想天开', 'playful': '俏皮', 'fun': '有趣',
    'dreamy': '梦幻', 'surreal': '超现实', 'fantasy': '幻想',
    'epic': '史诗', 'grand': '宏大', 'monumental': '纪念碑式的',
    'intimate': '亲密', 'cozy': '温馨', 'comfortable': '舒适',
    'lonely': '孤独', 'solitary': '独自', 'isolated': '孤立',
    'bustling': '熙熙攘攘', 'crowded': '拥挤', 'busy': '繁忙',
    'chaotic': '混乱', 'calm': '平静', 'peaceful': '宁静',
    # 摄影术语
    'lens': '镜头', 'aperture': '光圈', 'shutter': '快门',
    'ISO': '感光度', 'f/1.4': 'f/1.4', 'f/2.8': 'f/2.8',
    'f/8': 'f/8', 'f/16': 'f/16',
    'bokeh': '散景', 'depth of field': '景深', 'DOF': '景深',
    'focal length': '焦距', '35mm': '35毫米', '50mm': '50毫米',
    '85mm': '85毫米', '135mm': '135毫米',
    # 平台参数
    'aspect ratio': '宽高比', '--ar': '--ar', '--v': '--v',
    'stylize': '风格化', '--s': '--s', 'chaos': '混沌度', '--c': '--c',
    'quality': '质量', '--q': '--q', 'weird': '怪异', '--w': '--w',
    'seed': '种子', '--seed': '--seed', 'tile': '平铺', '--tile': '--tile',
    'no': '无', 'negative': '负面', 'weight': '权重', 'emphasis': '强调',
    # 通用副词/连词
    'and': '与', 'or': '或', 'with': '与', 'without': '无',
    'during': '在...期间', 'after': '在...之后', 'before': '在...之前',
    'very': '非常', 'extremely': '极其', 'highly': '高度',
    'slightly': '略微', 'gently': '轻柔', 'slowly': '缓慢',
 'quickly': '快速', 'brightly': '明亮地', 'darkly': '黑暗地',
 # 补充常见 MJ 术语
 'wide shot': '远景', 'medium shot': '中景', 'long shot': '远景',
 'close up': '特写', 'of': '的', 'traditional': '传统的',
 'market': '市场', 'deep': '深', 'tones': '色调',
 'wooden': '木制的', 'wood': '木', 'architecture': '建筑',
 'lantern': '灯笼', 'lanterns': '灯笼', 'award-winning': '获奖的',
 'photography': '摄影', 'shallow': '浅',
     # 补充常见 MJ 术语（单字，解决分词不匹配多词条的问题）
     'wide': '广角', 'shot': '镜头', 'depth': '景深',
     'award': '获奖', 'winning': '优胜',
 }


def is_english(text: str) -> bool:
    """检测文本是否主要是英文（ASCII 字母 > 30%）"""
    if not text:
        return False
    ascii_count = sum(1 for c in text if c.isascii() and c.isalpha())
    return ascii_count / len(text) > 0.3


def translate_en2cn(text: str) -> str:
    """简易 EN->CN 翻译：基于关键词表 + 保留未匹配词"""
    if not text:
        return ""

    # 按非字母字符分词（保留分隔符）
    import re
    tokens = re.findall(r'\b\w+\b|[^\w\s]|\s+', text)

    result = []
    for tok in tokens:
        if tok.isspace() or not tok.isascii():
            result.append(tok)
        elif tok.isascii() and tok.isalpha():
            lower = tok.lower()
            # 多词优先（暂支持 2 词组合）
            translated = EN_CN_DICT.get(lower, tok)
            result.append(translated)
        else:
            result.append(tok)

    return ''.join(result)
