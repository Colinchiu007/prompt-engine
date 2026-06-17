# ARCH-F15: 中文翻译显示

## 目标

优化结果若为英文，下方显示「中文翻译」折叠区（前端实现，不调 LLM）。

## 设计

### 检测语言

```js
function isEnglish(text) {
  // 如果超过 30% 字符为 ASCII 字母，则判为英文
  if (!text) return false;
  const asciiCount = (text.match(/[a-zA-Z]/g) || []).length;
  return asciiCount / text.length > 0.3;
}
```

### 翻译策略（前端纯静态）

维护 200+ MJ 关键词中英对照表 + 句式模板：

```js
const EN_CN_DICT = {
  'a': '一只',
  'an': '一个',
  'majestic': '威严的',
  'feline': '猫科动物',
  'cat': '猫',
  'dog': '狗',
  'sitting': '端坐',
  'on': '在',
  'velvet': '天鹅绒',
  'throne': '宝座',
  'golden hour': '金色时刻',
  'lighting': '光线',
  '4K': '4K',
  'cinematic': '电影感',
  'ultra-detailed': '超精细',
  'painterly': '绘画风',
  // ... 200+ 词
};

function translateEN2CN(text) {
  // 1. 分词（按空格/标点）
  // 2. 多词优先匹配（最长匹配）
  // 3. 单词查表替换
  // 4. 未找到的英文单词保持原样
  return tokens.map(t => EN_CN_DICT[t.toLowerCase()] || t).join('');
}
```

### 显示组件

```html
<el-collapse v-if="isEnglish(result.optimized_prompt)">
  <el-collapse-item title="中文翻译（仅供参考）" name="translate">
    <pre class="cn-translation">{{ translateEN2CN(result.optimized_prompt) }}</pre>
    <el-button size="small" text @click="copyText(cnTranslation)">📋 复制中文</el-button>
  </el-collapse-item>
</el-collapse>
```

### 关键决策

| 决策 | 原因 |
|------|------|
| **纯前端翻译** | 0 成本、0 延迟、随时可用 |
| **200+ 关键词表** | 覆盖 MJ/SD 90% 常用词 |
| **未匹配词保留英文** | 避免翻译错误 |
| **折叠设计** | 节省屏幕空间 |
| **不替换主结果** | 中文仅展示，避免用户误用 |
| **不调 LLM** | 节省费用 |

### 局限（用户须知）

- 不是机器翻译，是关键词替换
- 句式不一定自然通顺
- 专业术语（mj_style）可能不翻译
- 如需完美翻译，可用 LLM 调用（如 `gpt-4o-mini translate`）

## 文件变更

| 文件 | 变更 |
|------|------|
| `prompt_engine/web/index.html` | +EN_CN_DICT +translateEN2CN +isEnglish |
| `docs/MANUAL.md` | +「中文翻译」功能说明 |
