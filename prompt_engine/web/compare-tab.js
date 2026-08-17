/**
 * compare-tab.js — 文案分句 → 提示词 → 生图对比验证（CompareTab 组件）
 *
 * 独立于 index.html 的组件文件（A3 方案）：index.html 只负责挂菜单、注册组件、
 * 通过 window.__PE 共享 api/copyText。本文件使用与 index.html 相同的
 * CDN Vue3 + Element Plus 全局（template 字符串 + setup() 模式）。
 *
 * 数据流（每句独立状态机）：
 *   promptState: idle | loading | done | error
 *   imageState:  idle | loading | done | error
 *
 * 端点：
 *   POST /v1/compare/split   分句（代理 smart-sentence-splitter）
 *   POST /v1/compare/prompt  单句 → 调用方 LLM → 英文生图提示词
 *   POST /v1/compare/images  单提示词 → MiniMax image-01 → n 张图（默认 2）
 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const { ElMessage, ElMessageBox } = ElementPlus;

  // 运行时动态取共享对象（compare-tab.js 先于 index.html 内联脚本加载，
  // window.__PE 在页面 mount 前才由内联脚本填充，因此不能在 IIFE 阶段捕获）
  function sharedPE() {
    return window.__PE || {};
  }

  // 运行时动态取共享 API 助手（compare-tab.js 先于 index.html 内联脚本加载，
  // window.__PE 在页面 mount 前才由内联脚本填充，因此不能在 IIFE 阶段捕获）
  function apiReq(path, body, method) {
    const a = (window.__PE && window.__PE.api);
    if (!a) throw new Error('共享 API 助手未初始化（window.__PE.api 缺失）');
    if (method === 'GET') return a.get(path);
    return a.post(path, body);
  }

  const MAX_TEXT = 6000;
  const DEFAULT_LLM_KEY_STORAGE = 'pe_compare_llm_key';
  const DEFAULT_IMAGE_KEY_STORAGE = 'pe_compare_image_key';

  function maskKey(k) {
    if (!k) return '';
    return k.length <= 8 ? '****' : k.slice(0, 4) + '****' + k.slice(-4);
  }

  const CompareTab = {
    name: 'CompareTab',
    template: `
    <div>
      <!-- 1. 文案输入 -->
      <el-card shadow="never" style="margin-bottom:16px">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>文案输入</span>
            <span style="font-size:12px;color:#909399">分句 → 提示词 → 每句 2 张图对比</span>
          </div>
        </template>
        <div class="section-desc">
          输入一篇文案（最多 {{ MAX_TEXT }} 字）。系统调用分句模型分句并展示结果，每个分句经
          MiniMax 生成英文生图提示词，同一提示词生成 <b>2 张图片</b> 并排对比，用于验证提示词实际效果。
        </div>
        <el-input v-model="text" type="textarea" :rows="6" resize="vertical"
          :maxlength="MAX_TEXT" show-word-limit
          placeholder="在此粘贴/输入文案，例如一篇产品介绍、故事或解说词…" />
        <div style="margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <el-button type="primary" @click="runSplit" :loading="splitting" :disabled="!text.trim()">
            开始分句
          </el-button>
          <el-button @click="reset" :disabled="!text && !sentences.length">清空</el-button>
          <el-tag v-if="splitMeta" type="success" size="small">
            {{ sentences.length }} 句 · {{ splitMeta.tier_used }} · {{ splitMeta.duration_ms }}ms
          </el-tag>
        </div>
      </el-card>

      <!-- 2. 设置（文字 LLM 与生图能力独立配置） -->
      <el-card shadow="never" style="margin-bottom:16px">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>模型能力设置</span>
            <span style="font-size:12px;color:#909399">文字推理与图片生成使用独立模型和 Key</span>
          </div>
        </template>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span style="font-size:12px;color:#606266;min-width:70px">文字 LLM</span>
          <el-input v-model="llmApiKey" type="password" show-password autocomplete="off"
            style="flex:1;min-width:240px;max-width:420px"
            placeholder="粘贴文字 LLM API Key"
            @change="persistKeys" />
          <el-tag v-if="llmApiKey" size="small" type="success">{{ maskKey(llmApiKey) }}</el-tag>
          <el-button size="small" @click="testConnection" :loading="testing" :disabled="!hasLlmKey">
            测试连接
          </el-button>
          <el-button size="small" text @click="advanced = !advanced">
            {{ advanced ? '收起高级设置 ▲' : '高级设置 ▼' }}
          </el-button>
        </div>
        <el-alert v-if="testResult" :title="testResult" :type="testOk ? 'success' : 'error'"
          :closable="false" show-icon style="margin-top:8px" />
        <template v-if="advanced">
          <el-divider style="margin:14px 0" />
          <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
            <el-input v-model="llmProvider" style="width:160px" size="small" placeholder="文字 provider（如 minimax）" />
            <el-input v-model="llmBaseUrl" style="width:320px" size="small"
              placeholder="文字 LLM Base URL（可选）" />
            <el-input v-model="llmModel" style="width:200px" size="small" placeholder="文字模型（如 MiniMax-M3）" />
            <span style="font-size:12px;color:#606266;min-width:70px">图片 Key</span>
            <el-input v-model="imageApiKey" type="password" show-password autocomplete="off"
              style="flex:1;min-width:240px;max-width:420px"
              placeholder="粘贴图片生成 API Key（可与文字 Key 不同）"
              @change="persistKeys" />
            <el-tag v-if="imageApiKey" size="small" type="success">{{ maskKey(imageApiKey) }}</el-tag>
            <el-input v-model="imageBaseUrl" style="width:320px" size="small"
              placeholder="图片 Base URL（可选）" />
            <el-select v-model="size" size="small" style="width:180px">
              <el-option label="1:1 (1024x1024)" value="1024x1024" />
              <el-option label="16:9 (1920x1080)" value="1920x1080" />
              <el-option label="9:16 (1080x1920)" value="1080x1920" />
              <el-option label="4:3 (1280x960)" value="1280x960" />
            </el-select>
            <span style="font-size:12px;color:#909399">每提示词生成</span>
            <el-input-number v-model="n" :min="1" :max="4" size="small" style="width:100px" />
            <span style="font-size:12px;color:#909399">张图</span>
          </div>
          <div style="margin-top:8px;font-size:12px;color:#909399">
            两类 Key 仅保存在本机浏览器 localStorage 并随对应请求发送，不写入服务端文件；
            图片能力可额外使用服务端环境变量 <code>MINIMAX_API_KEY</code>，文字推理不会使用该回退。
          </div>
        </template>
      </el-card>

      <!-- 3. 分句结果 + 提示词 + 双图对比 -->
      <el-card v-if="sentences.length" shadow="never">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <span>分句结果与生图对比（{{ sentences.length }} 句）</span>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <el-button size="small" type="primary" :loading="bulkPrompting" :disabled="!hasLlmKey || !pendingPrompts.length"
                @click="genAllPrompts">
                生成全部提示词（{{ pendingPrompts.length }}）
              </el-button>
              <el-button size="small" type="success" :loading="bulkGenerating" :disabled="!hasImageKey || !pendingImages.length"
                @click="genAllImages">
                生成全部图片（{{ pendingImages.length }}）
              </el-button>
            </div>
          </div>
        </template>
        <el-alert v-if="!hasLlmKey" title="请先填写文字 LLM Key；文字推理不会使用服务端图片 Key 回退"
          type="warning" :closable="false" show-icon style="margin-bottom:12px" />
        <el-alert v-if="!hasImageKey" title="图片生成需要图片能力 Key，或服务端配置 MINIMAX_API_KEY"
          type="warning" :closable="false" show-icon style="margin-bottom:12px" />
        <el-alert v-if="sentences.length > 30" type="info" :closable="false" show-icon style="margin-bottom:12px"
          title="文案分句较多，生图将产生较多 API 调用，建议只对需要验证的分句生成图片。" />

        <el-tabs v-model="layerTab" style="margin-bottom:4px">
        <el-tab-pane :label="'句子层（' + sentences.length + '）'" name="sentence">
        <div v-for="(s, idx) in sentences" :key="s.index"
          style="border:1px solid #ebeef5;border-radius:6px;padding:12px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <el-tag size="small" type="info">#{{ s.index }}</el-tag>
              <span style="font-size:12px;color:#909399">{{ s.char_count }}字</span>
              <el-tag v-if="s.tier" size="small" effect="plain">{{ s.tier }}</el-tag>
              <el-tag v-if="s.confidence" size="small" effect="plain" type="warning">
                {{ Math.round(s.confidence * 100) }}%
              </el-tag>
            </div>
            <div style="display:flex;gap:6px">
              <el-button size="small" text @click="copyText(s.text)">复制原文</el-button>
              <el-button size="small" @click="genPrompt(s)" :loading="s.promptState === 'loading'" :disabled="!hasLlmKey">
                {{ s.promptState === 'done' ? '重新生成提示词' : '生成提示词' }}
              </el-button>
              <el-button size="small" type="success" @click="genImages(s)" :loading="s.imageState === 'loading'"
                :disabled="!hasImageKey || !s.prompt.trim()">
                {{ s.imageState === 'done' ? '重新生图' : '生图对比' }}
              </el-button>
            </div>
          </div>

          <div style="margin-top:8px;padding:8px 10px;background:#f5f7fa;border-radius:4px;font-size:13px;line-height:1.6;white-space:pre-wrap">
            {{ s.text }}
          </div>

          <div v-if="s.promptState !== 'idle'" style="margin-top:10px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
              <span style="font-size:12px;color:#909399">英文生图提示词{{ s.promptModel ? ' · ' + s.promptModel : '' }}<el-tag v-if="s.promptTruncated" size="small" type="warning" effect="plain" style="margin-left:6px">已截断</el-tag></span>
              <el-button v-if="s.prompt" size="small" text @click="copyText(s.prompt)">复制提示词</el-button>
            </div>
            <el-input v-if="s.prompt" v-model="s.prompt" type="textarea" :rows="2" resize="vertical"
              style="font-size:12px" placeholder="提示词（可编辑后重新生图）" />
            <div v-if="s.promptState === 'loading'" style="margin-top:6px">
              <el-skeleton :rows="2" animated />
            </div>
            <div v-if="s.promptState === 'error'" style="margin-top:6px">
              <el-alert :title="s.promptError" type="error" :closable="false" show-icon />
            </div>
          </div>

          <div v-if="s.imageState === 'done' && s.images.length" style="margin-top:12px">
            <div style="display:flex;gap:12px;flex-wrap:wrap">
              <div v-for="(img, gi) in s.images" :key="gi" style="flex:1;min-width:220px;max-width:380px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                  <span style="font-size:12px;color:#606266">图 {{ gi + 1 }}</span>
                  <span style="display:flex;gap:4px">
                    <el-button size="small" text @click="copyText(img)">URL</el-button>
                    <el-button size="small" text type="primary" @click="previewImage(img)">放大</el-button>
                  </span>
                </div>
                <img :src="img" alt="生成图" loading="lazy"
                  style="width:100%;border-radius:6px;border:1px solid #ebeef5;cursor:zoom-in;object-fit:contain;background:#fafafa"
                  @click="previewImage(img)" />
              </div>
            </div>
            <div v-if="s.images.length === 1" style="margin-top:4px;font-size:12px;color:#e6a23c">
              ⚠️ 仅返回 1 张图（MiniMax 偶发少图），可点击「重新生图」。
            </div>
            <div style="margin-top:6px;font-size:12px;color:#909399">
              生成耗时 {{ s.imageDurationMs }}ms · 模型 image-01 · 尺寸 {{ size }}
            </div>
          </div>
          <div v-if="s.imageState === 'loading'" style="margin-top:12px">
            <div style="display:flex;gap:12px">
              <el-skeleton style="flex:1" animated>
                <template #template>
                  <el-skeleton-item variant="image" style="width:100%;height:220px" />
                </template>
              </el-skeleton>
              <el-skeleton style="flex:1" animated>
                <template #template>
                  <el-skeleton-item variant="image" style="width:100%;height:220px" />
                </template>
              </el-skeleton>
            </div>
            <div style="margin-top:6px;font-size:12px;color:#909399">图片生成中（通常 10~60 秒/张），请耐心等待…</div>
          </div>
          <div v-if="s.imageState === 'error'" style="margin-top:10px">
            <el-alert :title="s.imageError" type="error" :closable="false" show-icon>
              <template #default>
                <el-button size="small" text type="primary" @click="genImages(s)" style="margin-top:4px">重试</el-button>
              </template>
            </el-alert>
          </div>
        </div>
        </el-tab-pane>

        <el-tab-pane :label="'场景与字幕层（' + scenes.length + '）'" name="scene">
          <div v-if="!scenes.length" style="color:#909399;font-size:13px;padding:8px 0">
            分句服务未返回场景/字幕数据。
          </div>
          <div v-for="(sc, sci) in scenes" :key="sc.segment_id"
            style="border:1px solid #ebeef5;border-radius:6px;padding:12px;margin-bottom:12px">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
              <el-tag size="small" type="info">场景 {{ sc.segment_id }}</el-tag>
              <el-tag v-if="sc.estimated_duration" size="small" effect="plain">
                {{ fmtDuration(sc.estimated_duration) }}
              </el-tag>
              <span style="font-size:12px;color:#909399">
                字幕 {{ sc.subtitle_count || (sc.subtitles || []).length }} 条
              </span>
            </div>
            <div style="padding:8px 10px;background:#f5f7fa;border-radius:4px;font-size:13px;line-height:1.6;white-space:pre-wrap">
              {{ sc.text }}
            </div>
            <el-table v-if="(sc.subtitles || []).length" :data="sc.subtitles" size="small" stripe style="margin-top:8px">
              <el-table-column label="序" width="60">
                <template #default="{row}">{{ row.display_order }}</template>
              </el-table-column>
              <el-table-column prop="text" label="字幕文本" />
              <el-table-column label="时间" width="150">
                <template #default="{row}">{{ fmtTime(row.start_time) }} ~ {{ fmtTime((row.start_time || 0) + (row.duration || 0)) }}</template>
              </el-table-column>
            </el-table>
            <div v-else style="margin-top:8px;font-size:12px;color:#909399">该场景无字幕块。</div>
          </div>
        </el-tab-pane>
        </el-tabs>
      </el-card>

      <el-dialog v-model="previewVisible" width="min(92vw, 900px)" :show-close="true" align-center>
        <img v-if="previewUrl" :src="previewUrl" alt="预览大图"
          style="width:100%;border-radius:6px;object-fit:contain;background:#fafafa" />
      </el-dialog>
    </div>
    `,    setup() {
      const text = ref('');
      const splitting = ref(false);
      const sentences = ref([]);
      const scenes = ref([]);
      const layerTab = ref('sentence');
      const splitMeta = ref(null);

      function fmtTime(t) {
        const v = Number(t) || 0;
        const m = Math.floor(v / 60);
        const s = (v - m * 60).toFixed(1);
        return m > 0 ? m + '分' + s + '秒' : s + '秒';
      }
      function fmtDuration(d) {
        const v = Number(d) || 0;
        return v.toFixed(1) + 's';
      }

      const llmApiKey = ref(localStorage.getItem(DEFAULT_LLM_KEY_STORAGE) || '');
      const imageApiKey = ref(localStorage.getItem(DEFAULT_IMAGE_KEY_STORAGE) || '');
      const advanced = ref(false);
      const llmProvider = ref('minimax');
      const llmBaseUrl = ref('');
      const imageBaseUrl = ref('');
      const llmModel = ref('MiniMax-M3');
      const size = ref('1024x1024');
      const n = ref(2);
      const testing = ref(false);
      const testResult = ref('');
      const testOk = ref(false);

      const bulkPrompting = ref(false);
      const bulkGenerating = ref(false);

      const previewVisible = ref(false);
      const previewUrl = ref('');

      const imageEnvKeyAvailable = ref(false);
      const hasLlmKey = computed(() => !!llmApiKey.value.trim());
      const hasImageKey = computed(() => !!imageApiKey.value.trim() || imageEnvKeyAvailable.value);
      const width = computed(() => parseInt(size.value.split('x')[0], 10));
      const height = computed(() => parseInt(size.value.split('x')[1], 10));
      const pendingPrompts = computed(() => sentences.value.filter(s => s.promptState !== 'done'));
      const pendingImages = computed(() => sentences.value.filter(s => s.imageState !== 'done' && s.prompt.trim()));

      function persistKeys() {
        try {
          if (llmApiKey.value.trim()) localStorage.setItem(DEFAULT_LLM_KEY_STORAGE, llmApiKey.value.trim());
          else localStorage.removeItem(DEFAULT_LLM_KEY_STORAGE);
          if (imageApiKey.value.trim()) localStorage.setItem(DEFAULT_IMAGE_KEY_STORAGE, imageApiKey.value.trim());
          else localStorage.removeItem(DEFAULT_IMAGE_KEY_STORAGE);
        } catch (e) { /* localStorage 不可用时静默 */ }
      }

      function llmBody() {
        return {
          llm: {
            provider: llmProvider.value.trim() || 'minimax',
            model: llmModel.value.trim() || 'MiniMax-M3',
            api_key: llmApiKey.value.trim(),
            base_url: llmBaseUrl.value.trim() || undefined,
          },
        };
      }

      function imageBody() {
        return {
          api_key: imageApiKey.value.trim() || undefined,
          base_url: imageBaseUrl.value.trim() || undefined,
        };
      }

      function copyText(t) {
        const pe = sharedPE();
        if (pe.copyText) { pe.copyText(t); return; }
        try {
          if (navigator.clipboard) { navigator.clipboard.writeText(t); return; }
        } catch (e) { /* ignore */ }
        const ta = document.createElement('textarea');
        ta.value = t; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); ta.remove();
      }

      async function runSplit() {
        const t = text.value.trim();
        if (!t) { ElMessage.warning('请输入文案'); return; }
        if (t.length > MAX_TEXT) { ElMessage.error('文案超过 ' + MAX_TEXT + ' 字上限'); return; }
        splitting.value = true;
        try {
          const d = await apiReq('/v1/compare/split', { text: t });
          if (!d.sentences || !d.sentences.length) { ElMessage.warning('分句结果为空'); return; }
          sentences.value = d.sentences.map(s => ({
            index: s.index,
            text: s.text,
            language: s.language,
            tier: s.tier,
            confidence: s.confidence,
            char_count: s.char_count,
            prompt: '',
            promptModel: '',
            promptState: 'idle',
            promptError: '',
            promptTruncated: false,
            images: [],
            imageState: 'idle',
            imageError: '',
            imageDurationMs: 0,
          }));
          splitMeta.value = {
            tier_used: d.tier_used || d.splitter || '-',
            duration_ms: d.duration_ms || 0,
          };
          // 场景层与字幕层（smart-sentence-splitter 返回，/v1/compare/split 原样透传）
          scenes.value = (d.scenes || []).map(sc => ({ ...sc, subtitles: sc.subtitles || [] }));
          ElMessage.success('分句完成：' + sentences.value.length + ' 句 · ' + scenes.value.length + ' 场景');
        } catch (e) {
          ElMessage.error(e.message || '分句失败');
        } finally {
          splitting.value = false;
        }
      }

      async function genPrompt(s) {
        if (!s.text.trim()) return;
        s.promptState = 'loading';
        s.promptError = '';
        try {
          const d = await apiReq('/v1/compare/prompt', {
            text: s.text,
            ...llmBody(),
          });
          s.prompt = d.prompt;
          s.promptModel = d.model;
          s.promptTruncated = !!d.truncated;
          s.promptState = 'done';
        } catch (e) {
          s.promptState = 'error';
          s.promptError = e.message || '提示词生成失败';
        }
      }

      async function genImages(s) {
        if (!s.prompt.trim()) {
          ElMessage.warning('请先生成提示词（第 ' + s.index + ' 句）');
          return;
        }
        s.imageState = 'loading';
        s.imageError = '';
        s.images = [];
        try {
          const d = await apiReq('/v1/compare/images', {
            prompt: s.prompt,
            ...imageBody(),
            n: n.value,
            width: width.value,
            height: height.value,
          });
          s.images = d.urls || [];
          s.imageState = 'done';
          s.imageDurationMs = d.duration_ms || 0;
          if (s.images.length < 2) ElMessage.info('第 ' + s.index + ' 句仅返回 ' + s.images.length + ' 张图');
        } catch (e) {
          s.imageState = 'error';
          s.imageError = e.message || '生图失败';
        }
      }

      async function genAllPrompts() {
        const targets = sentences.value.filter(s => s.promptState !== 'done');
        if (!targets.length) return;
        if (targets.length > 30) {
          try {
            await ElMessageBox.confirm(
              '共 ' + targets.length + ' 句需要生成提示词，将发起 ' + targets.length + ' 次 LLM 调用。继续？',
              '确认批量生成提示词', { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' });
          } catch (e) { return; }
        }
        bulkPrompting.value = true;
        for (const s of targets) { await genPrompt(s); }
        bulkPrompting.value = false;
        const ok = sentences.value.filter(s => s.promptState === 'done').length;
        ElMessage.success('提示词生成完成：' + ok + '/' + sentences.value.length);
      }

      async function genAllImages() {
        const targets = sentences.value.filter(s => s.imageState !== 'done' && s.prompt.trim());
        if (!targets.length) {
          if (sentences.value.some(s => !s.prompt.trim())) ElMessage.warning('请先为分句生成提示词');
          return;
        }
        const cost = targets.length * n.value;
        try {
          await ElMessageBox.confirm(
            '将生成 ' + targets.length + ' 个提示词 x 每张 ' + n.value + ' 图 = <b>' + cost + ' 张图片</b>，' +
            '会消耗 MiniMax API 额度。继续？',
            '确认批量生图', {
              type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消',
              dangerouslyUseHTMLString: true,
            });
        } catch (e) { return; }
        bulkGenerating.value = true;
        for (const s of targets) { await genImages(s); }
        bulkGenerating.value = false;
        const ok = sentences.value.filter(s => s.imageState === 'done').length;
        ElMessage.success('生图完成：' + ok + '/' + sentences.value.length + ' 句');
      }

      async function testConnection() {
        testing.value = true;
        testResult.value = '';
        try {
          await apiReq('/v1/compare/prompt', {
            text: '一朵盛开的红色玫瑰',
            ...llmBody(),
          });
          testOk.value = true;
          testResult.value = '连接成功：MiniMax 文字推理可用（API Key 有效）';
        } catch (e) {
          testOk.value = false;
          testResult.value = '连接失败：' + (e.message || '未知错误');
        } finally {
          testing.value = false;
        }
      }

      function previewImage(url) {
        previewUrl.value = url;
        previewVisible.value = true;
      }

      function reset() {
        text.value = '';
        sentences.value = [];
        scenes.value = [];
        layerTab.value = 'sentence';
        splitMeta.value = null;
        previewUrl.value = '';
        previewVisible.value = false;
      }

      // 挂载时只查询图片能力环境 Key；文字 LLM 永远要求调用方显式填写绑定。
      onMounted(async () => {
        try {
          const st = await apiReq('/v1/compare/status', null, 'GET');
          imageEnvKeyAvailable.value = !!st.has_image_env_key;
        } catch (e) { /* 查询失败保持 false，用户可手动输入 Key */ }
      });

      return {
        MAX_TEXT, text, splitting, sentences, scenes, layerTab, splitMeta,
        llmApiKey, imageApiKey, advanced, llmProvider, llmBaseUrl, imageBaseUrl, llmModel, size, n,
        testing, testResult, testOk, hasLlmKey, hasImageKey, imageEnvKeyAvailable,
        bulkPrompting, bulkGenerating,
        previewVisible, previewUrl,
        width, height, pendingPrompts, pendingImages,
        maskKey, copyText, fmtTime, fmtDuration,
        runSplit, genPrompt, genImages, genAllPrompts, genAllImages,
        testConnection, previewImage, reset, persistKeys,
      };
    },
  };

  window.CompareTab = CompareTab;
})();
