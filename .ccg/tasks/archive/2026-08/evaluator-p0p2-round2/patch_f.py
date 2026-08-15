import io, json

p = 'prompt_engine_core/knowledge/element_keywords.json'
data = json.loads(io.open(p, encoding='utf-8').read())
els = data['elements']

add = {
    'subject': ['полицейский', 'полицейских', 'мужчина', 'мужчины', 'женщина', 'женщины', 'группа'],
    'color': ['серый', 'серой', 'сером', 'однотонный', 'однотонном'],
    'environment': ['фон', 'фоне'],
}
for elem, words in add.items():
    cur = els[elem]['ru']
    for w in words:
        if w not in cur:
            cur.append(w)
data['version'] = 2
data['description'] = '六要素关键词资产（视频/图片评估器共享；任一语言命中即算要素命中）。v2：RU 补齐（golden ru 样本缺词 полицейский/серый/фон 等，2026-08-16）'
out = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
io.open(p, 'w', encoding='utf-8', newline='').write(out)
print('element_keywords.json v2 OK; subject.ru=', len(els['subject']['ru']), 'color.ru=', len(els['color']['ru']), 'environment.ru=', len(els['environment']['ru']))
