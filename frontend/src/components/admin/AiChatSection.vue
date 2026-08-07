<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, fmtShort } from './useAdminApi'

defineProps<{ visible: boolean }>()

const sysPrompt = ref('')
const temperature = ref(0.7)
const searxngUrl = ref('')
const searxngKey = ref('')
const webSearchEnabled = ref(false)
const searchMaxPages = ref(3)
const searchRewrite = ref(true)
const webFetchMaxChars = ref(6000)
const searchTestStatus = ref('')
const searchTesting = ref(false)
const wfRefreshStatus = ref('')
const wfRefreshLoading = ref(false)
const llms = ref<any[]>([])
const activeLlmId = ref('')
const cfgStatus = ref('')
const cfgLoading = ref(false)

const tokens = ref<any[]>([])
const tLoading = ref(false)
const maxUses = ref(100)
const genStatus = ref('')
const genLoading = ref(false)
const newToken = ref('')

async function loadCfg() {
  try {
    const d = await api('GET', '/api/admin/features/ai-chat/config')
    sysPrompt.value = d.system_prompt || ''
    temperature.value = d.temperature ?? 0.7
    searxngUrl.value = d.searxng_url || ''
    searxngKey.value = d.searxng_key || ''
    webSearchEnabled.value = !!d.web_search_enabled
    searchMaxPages.value = d.web_search_max_pages ?? 3
    searchRewrite.value = !!d.web_search_query_rewrite
    webFetchMaxChars.value = d.web_fetch_max_chars ?? 6000
    llms.value = (d.llms || []).map((l: any) => ({ ...l, editing: false, modelList: [], probing: false, testStatus: '', testing: false }))
    activeLlmId.value = d.active_llm_id || (llms.value[0]?.id || '')
  } catch (e: any) { cfgStatus.value = '加载失败: ' + e.message }
}

function newLlm() {
  llms.value.push({ id: 'llm_' + Date.now().toString(36), name: '', endpoint: '', model: '', api_key: '', max_tokens: 2048, stream: true, editing: true, modelList: [], probing: false, testStatus: '', testing: false })
}

function removeLlm(i: number) {
  const rm = llms.value[i]
  llms.value.splice(i, 1)
  if (activeLlmId.value === rm.id) activeLlmId.value = llms.value[0]?.id || ''
}

async function probeModels(llm: any) {
  if (!llm.endpoint) { llm.testStatus = '请先填写端点'; return }
  llm.probing = true
  llm.testStatus = ''
  llm.modelList = []
  try {
    const d = await api('POST', '/api/admin/features/ai-chat/llm-probe', { endpoint: llm.endpoint, api_key: llm.api_key })
    llm.modelList = d.models || []
    if (llm.modelList.length && !llm.modelList.includes(llm.model)) {
      llm.model = llm.modelList[0]
    }
    llm.testStatus = llm.modelList.length ? `✅ 探测到 ${llm.modelList.length} 个模型` : '❌ 未获取到模型'
  } catch (e: any) {
    llm.testStatus = '❌ 探测失败: ' + (e.message || '未知')
  } finally { llm.probing = false }
}

async function testLlm(llm: any) {
  if (!llm.endpoint) { llm.testStatus = '请先填写端点'; return }
  llm.testing = true
  llm.testStatus = '测试中...'
  try {
    const d = await api('POST', '/api/admin/features/ai-chat/llm-test', { endpoint: llm.endpoint, api_key: llm.api_key, model: llm.model })
    llm.testStatus = '✅ 连接正常: ' + (d.reply || '').slice(0, 60)
  } catch (e: any) {
    llm.testStatus = '❌ 测试失败: ' + (e.message || '未知')
  } finally { llm.testing = false }
}

async function testSearch() {
  searchTesting.value = true
  searchTestStatus.value = '测试中...'
  try {
    const d = await api('POST', '/api/admin/features/ai-chat/search-test', { url: searxngUrl.value.trim(), key: searxngKey.value.trim() })
    searchTestStatus.value = `✅ 连接正常，返回 ${d.results} 条结果` + (d.first_title ? `（首条: ${d.first_title}）` : '')
  } catch (e: any) {
    searchTestStatus.value = '❌ 测试失败: ' + (e.message || '未知')
  } finally { searchTesting.value = false }
}

async function refreshWorkflows() {
  wfRefreshLoading.value = true
  wfRefreshStatus.value = '刷新中...'
  try {
    const d = await api('POST', '/api/admin/features/ai-chat/workflows-refresh')
    wfRefreshStatus.value = `✅ 工作流清单已刷新（${d.count} 条${d.updated ? '，有更新' : ''}）`
  } catch (e: any) {
    wfRefreshStatus.value = '❌ 刷新失败: ' + (e.message || '未知')
  } finally { wfRefreshLoading.value = false }
}

async function saveCfg() {
  cfgLoading.value = true
  cfgStatus.value = ''
  try {
    await api('POST', '/api/admin/features/ai-chat/config', {
      system_prompt: sysPrompt.value,
      temperature: temperature.value,
      searxng_url: searxngUrl.value.trim(),
      searxng_key: searxngKey.value.trim(),
      web_search_enabled: webSearchEnabled.value,
      web_search_max_pages: searchMaxPages.value,
      web_search_query_rewrite: searchRewrite.value,
      web_fetch_max_chars: webFetchMaxChars.value,
      llms: llms.value,
      active_llm_id: activeLlmId.value,
    })
    cfgStatus.value = '✅ 已保存'
    setTimeout(() => { if (cfgStatus.value === '✅ 已保存') cfgStatus.value = '' }, 3000)
  } catch (e: any) { cfgStatus.value = '❌ 保存失败: ' + e.message } finally { cfgLoading.value = false }
}

async function loadTokens() {
  tLoading.value = true
  try {
    const d = await api('GET', '/api/admin/features/ai-chat/tokens')
    tokens.value = d.items || []
  } catch (e: any) { genStatus.value = '加载失败: ' + e.message } finally { tLoading.value = false }
}

async function generate() {
  genLoading.value = true
  genStatus.value = ''
  newToken.value = ''
  try {
    const d = await api('POST', '/api/admin/features/ai-chat/tokens/generate', { max_uses: maxUses.value })
    newToken.value = d.token
    genStatus.value = '✅ 生成成功，请复制保存'
    await loadTokens()
    setTimeout(() => { if (genStatus.value === '✅ 生成成功，请复制保存') genStatus.value = '' }, 5000)
  } catch (e: any) { genStatus.value = '❌ 生成失败: ' + e.message } finally { genLoading.value = false }
}

async function delToken(token: string) {
  if (!confirm('确定删除此额度 Token？')) return
  try {
    await api('POST', '/api/admin/features/ai-chat/tokens/delete', { token })
    tokens.value = tokens.value.filter(x => x.token !== token)
  } catch (e: any) { alert('删除失败: ' + e.message) }
}

async function cleanupTokens() {
  if (!confirm('确定清理所有已用完（失效）的额度 Token？此操作不可恢复。')) return
  tLoading.value = true
  try {
    const d = await api('POST', '/api/admin/features/ai-chat/tokens/cleanup')
    genStatus.value = `✅ 已清理 ${d.removed} 个失效 Token，剩余 ${d.remaining} 个`
    await loadTokens()
    setTimeout(() => { if (genStatus.value?.startsWith('✅ 已清理')) genStatus.value = '' }, 5000)
  } catch (e: any) { genStatus.value = '❌ 清理失败: ' + e.message } finally { tLoading.value = false }
}

async function copyToken() {
  try { await navigator.clipboard.writeText(newToken.value); alert('已复制') } catch { prompt('复制此 Token：', newToken.value) }
}

// ── 补充提示词（可为空）：AI 聊天生图的可选系统提示词前缀 ──
const extraPrompt = ref('')
const extraEnabled = ref(true)
const extraStatus = ref('')
const extraLoading = ref(false)
async function loadExtra() {
  try {
    const d = await api('GET', '/api/admin/features/ai-chat/extra-prompt')
    extraEnabled.value = !!d.enabled
    extraPrompt.value = d.prompt || ''
  } catch { }
}
async function saveExtra() {
  extraLoading.value = true
  try {
    await api('POST', '/api/admin/features/ai-chat/extra-prompt', { enabled: extraEnabled.value, prompt: extraPrompt.value })
    extraStatus.value = '✓ 已保存'
    setTimeout(() => { extraStatus.value = '' }, 2000)
  } catch (e: any) { extraStatus.value = '❌ ' + e.message }
  extraLoading.value = false
}

onMounted(() => { loadCfg(); loadTokens(); loadExtra() })
</script>

<template>
  <div class="space-y-4">

    <!-- LLM 配置（多模型，可启用） -->
    <div class="border border-gray-100 rounded-xl p-3 bg-gray-50/60">
      <div class="flex items-center justify-between mb-2">
        <div class="text-sm font-semibold text-gray-700">👁️ LLM 配置（多模型）</div>
        <button @click="newLlm" class="px-2 py-1 text-[10px] bg-blue-100 text-blue-600 rounded-lg hover:bg-blue-200 cursor-pointer border-0">➕ 添加模型</button>
      </div>
      <div v-if="!llms.length" class="text-xs text-gray-400 mb-3">尚未配置模型，未配置时用户会收到「请联系管理员」提示。</div>
      <div v-if="!llms.length" class="flex items-center justify-center border-2 border-dashed border-gray-200 rounded-xl py-8 mb-3">
        <button @click="newLlm" class="px-4 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0">➕ 新建配置</button>
      </div>
      <div v-for="(llm, i) in llms" :key="llm.id" class="border border-gray-200 bg-white rounded-xl mb-3 overflow-hidden" :class="activeLlmId===llm.id ? 'ring-2 ring-pink-200' : ''">
        <div class="flex items-center gap-2 px-3 py-2.5 bg-gray-50/80 border-b border-gray-100">
          <span v-if="activeLlmId===llm.id" class="text-[10px] bg-pink-500 text-white px-1.5 py-0.5 rounded-full shrink-0">启用</span>
          <span class="text-sm font-semibold text-gray-700 truncate flex-1">{{ llm.name || ('模型 ' + (i+1)) }}</span>
          <span class="text-[10px] text-gray-400 truncate hidden sm:block max-w-[40%]">{{ llm.endpoint || '未填端点' }}</span>
          <button @click="llm.editing=!llm.editing" class="shrink-0 text-[10px] px-2 py-1 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 cursor-pointer border-0">{{ llm.editing ? '收起' : '✏️ 编辑' }}</button>
          <button @click="activeLlmId=llm.id" :disabled="activeLlmId===llm.id" class="shrink-0 text-[10px] px-2 py-1 rounded cursor-pointer border-0" :class="activeLlmId===llm.id?'bg-pink-100 text-pink-400 cursor-not-allowed':'bg-green-100 text-green-700 hover:bg-green-200'">启用</button>
          <button @click="removeLlm(i)" class="shrink-0 text-[10px] px-2 py-1 bg-red-100 text-red-500 rounded hover:bg-red-200 cursor-pointer border-0">删除</button>
        </div>
        <div v-if="llm.editing" class="p-3">
        <label class="block text-xs text-gray-600 mb-2">
          配置名称
          <input v-model="llm.name" type="text" placeholder="视觉模型" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          端点（OpenAI 兼容，支持多模态）
          <input v-model="llm.endpoint" type="text" placeholder="https://xxx/v1" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          API Key（可留空）
          <input v-model="llm.api_key" type="text" placeholder="sk-xxx" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border font-mono text-xs" />
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          模型
          <div class="flex gap-1 mt-1">
            <select v-model="llm.model" class="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 bg-white">
              <option value="" disabled>选择模型</option>
              <option v-for="m in (llm.modelList || [])" :key="m" :value="m">{{ m }}</option>
            </select>
            <button @click="probeModels(llm)" :disabled="llm.probing" class="shrink-0 px-3 py-2 rounded-xl text-xs cursor-pointer border-0" :class="llm.probing?'bg-gray-200 text-gray-400 cursor-not-allowed':'bg-blue-100 text-blue-600 hover:bg-blue-200'">{{ llm.probing ? '...' : '🔍 探测模型' }}</button>
          </div>
          <div class="flex gap-1 mt-1">
            <input v-model="llm.model" type="text" placeholder="或手动输入模型名" class="flex-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
          </div>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          max_tokens：{{ llm.max_tokens }}
          <input v-model.number="llm.max_tokens" type="range" min="512" max="50000" step="256" class="mt-1 w-full accent-pink-500 h-1 cursor-pointer" />
        </label>
        <label class="flex items-center justify-between gap-2 text-xs text-gray-600 mb-2">
          <span>流式输出</span>
          <button @click="llm.stream=!llm.stream" class="relative w-10 h-5 rounded-full transition-colors cursor-pointer border-0" :class="llm.stream?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'">
            <span class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all" :class="llm.stream?'left-5.5':'left-0.5'"></span>
          </button>
        </label>
        <div class="flex gap-2">
          <button @click="testLlm(llm)" :disabled="llm.testing" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 flex items-center justify-center gap-1" :class="llm.testing?'bg-gray-200 text-gray-400 cursor-not-allowed':'bg-green-100 text-green-700 hover:bg-green-200'">
            <span v-if="llm.testing" class="inline-block w-3 h-3 border-2 border-green-400 border-t-green-700 rounded-full animate-spin"></span>
            {{ llm.testing ? '测试中...' : '🧪 测试模型' }}
          </button>
        </div>
        <div v-if="llm.testStatus" class="text-xs mt-2 px-2 py-1.5 rounded-lg" :class="llm.testStatus.startsWith('✅')?'bg-green-50 text-green-700':'bg-red-50 text-red-600'">{{ llm.testStatus }}</div>
        </div>
      </div>
      <div v-if="llms.length" class="flex items-center justify-center border-2 border-dashed border-gray-200 rounded-xl py-6 mb-3">
        <button @click="newLlm" class="px-4 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0">➕ 新建配置</button>
      </div>
      <p class="text-[11px] text-gray-400 mb-2">独立于 app.py 的 LLM 配置，卡片「启用」按钮选择当前使用的模型。</p>
      <button @click="saveCfg" :disabled="cfgLoading" class="px-4 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0 disabled:opacity-50" :class="cfgLoading?'cursor-not-allowed':''">
        {{ cfgLoading ? '保存中...' : '💾 保存配置' }}
      </button>
      <span v-if="cfgStatus" class="ml-2 text-xs" :class="cfgStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ cfgStatus }}</span>
    </div>

    <!-- 联网搜索配置 -->
    <div class="border border-gray-100 rounded-xl p-3 bg-gray-50/60">
      <div class="text-sm font-semibold text-gray-700 mb-2">🔍 联网搜索（SearXNG）</div>
      <label class="block text-xs text-gray-600 mb-2">
        SearXNG 地址
        <input v-model="searxngUrl" type="text" placeholder="http://192.168.x.x:8080" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
      </label>
      <label class="block text-xs text-gray-600 mb-2">
        API Key（与 SearXNG 服务器 api_key.conf 一致）
        <input v-model="searxngKey" type="text" placeholder="sxng_xxxxxxxx" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border font-mono text-xs" />
      </label>
      <div class="flex gap-2 mb-2">
        <button @click="testSearch" :disabled="searchTesting" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 flex items-center justify-center gap-1" :class="searchTesting?'bg-gray-200 text-gray-400 cursor-not-allowed':'bg-green-100 text-green-700 hover:bg-green-200'">
          <span v-if="searchTesting" class="inline-block w-3 h-3 border-2 border-green-400 border-t-green-700 rounded-full animate-spin"></span>
          {{ searchTesting ? '测试中...' : '🧪 测试搜索' }}
        </button>
        <button @click="refreshWorkflows" :disabled="wfRefreshLoading" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 flex items-center justify-center gap-1" :class="wfRefreshLoading?'bg-gray-200 text-gray-400 cursor-not-allowed':'bg-purple-100 text-purple-700 hover:bg-purple-200'">
          <span v-if="wfRefreshLoading" class="inline-block w-3 h-3 border-2 border-purple-400 border-t-purple-700 rounded-full animate-spin"></span>
          {{ wfRefreshLoading ? '刷新中...' : '🔄 刷新工作流清单' }}
        </button>
      </div>
      <div v-if="searchTestStatus" class="text-xs mb-2 px-2 py-1.5 rounded-lg" :class="searchTestStatus.startsWith('✅')?'bg-green-50 text-green-700':'bg-red-50 text-red-600'">{{ searchTestStatus }}</div>
      <div v-if="wfRefreshStatus" class="text-xs mb-2 px-2 py-1.5 rounded-lg" :class="wfRefreshStatus.startsWith('✅')?'bg-green-50 text-green-700':'bg-red-50 text-red-600'">{{ wfRefreshStatus }}</div>
      <label class="flex items-center justify-between gap-2 text-xs text-gray-600 mb-2">
        <span>启用联网搜索</span>
        <button @click="webSearchEnabled=!webSearchEnabled" class="relative w-10 h-5 rounded-full transition-colors cursor-pointer border-0" :class="webSearchEnabled?'bg-pink-500':'bg-gray-300'">
          <span class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all" :class="webSearchEnabled?'left-5.5':'left-0.5'"></span>
        </button>
      </label>
      <label class="block text-xs text-gray-600 mb-2">
        抓取网页数（0-5）：{{ searchMaxPages }}
        <input v-model.number="searchMaxPages" type="range" min="0" max="5" step="1" class="mt-1 w-full accent-pink-500 h-1 cursor-pointer" />
        <span class="text-gray-400">0 = 只给搜索摘要不抓正文</span>
      </label>
      <label class="flex items-center justify-between gap-2 text-xs text-gray-600 mb-2">
        <span>LLM 改写搜索词</span>
        <button @click="searchRewrite=!searchRewrite" class="relative w-10 h-5 rounded-full transition-colors cursor-pointer border-0" :class="searchRewrite?'bg-pink-500':'bg-gray-300'">
          <span class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all" :class="searchRewrite?'left-5.5':'left-0.5'"></span>
        </button>
      </label>
      <label class="block text-xs text-gray-600 mb-2">
        抓取网页字数上限：{{ webFetchMaxChars.toLocaleString() }}
        <input v-model.number="webFetchMaxChars" type="range" min="1000" max="50000" step="1000" class="mt-1 w-full accent-pink-500 h-1 cursor-pointer" />
        <span class="text-gray-400">越大看到内容越多，但消耗 token 越多</span>
      </label>
      <p class="text-[11px] text-gray-400 mb-2">仅「额度模式」用户可使用联网搜索；用户自定义 Key 模式不可用。答案会附带来源链接。</p>
      <button @click="saveCfg" :disabled="cfgLoading" class="px-4 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0 disabled:opacity-50" :class="cfgLoading?'cursor-not-allowed':''">
        {{ cfgLoading ? '保存中...' : '💾 保存配置' }}
      </button>
      <span v-if="cfgStatus" class="ml-2 text-xs" :class="cfgStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ cfgStatus }}</span>
    </div>

    <!-- 系统提示词与温度 -->
    <div class="border border-gray-100 rounded-xl p-3 bg-gray-50/60">
      <div class="text-sm font-semibold text-gray-700 mb-2">🤖 默认系统提示词</div>
      <textarea v-model="sysPrompt" rows="5" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border resize-y font-mono text-[11px]"></textarea>
      <label class="block text-xs text-gray-600 mt-2 mb-2">
        默认温度 (0-2)：{{ temperature }}
        <input v-model.number="temperature" type="range" min="0" max="2" step="0.1" class="mt-1 w-full accent-pink-500 h-1 cursor-pointer" />
      </label>
      <button @click="saveCfg" :disabled="cfgLoading" class="px-4 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0 disabled:opacity-50" :class="cfgLoading?'cursor-not-allowed':''">
        {{ cfgLoading ? '保存中...' : '💾 保存配置' }}
      </button>
      <span v-if="cfgStatus" class="ml-2 text-xs" :class="cfgStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ cfgStatus }}</span>
    </div>

    <!-- 补充提示词（可为空） -->
    <div class="border border-gray-100 rounded-xl p-3 bg-gray-50/60">
      <div class="flex items-center justify-between mb-2">
        <div class="text-sm font-semibold text-gray-700">🧩 补充提示词（可为空）</div>
        <label class="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
          启用
          <input v-model="extraEnabled" type="checkbox" class="w-4 h-4 accent-pink-500" />
        </label>
      </div>
      <p class="text-[11px] text-gray-400 mb-2">启用并填写后，该内容会作为 AI 聊天生图的系统提示词前缀注入（全局生效）。留空或关闭则不注入。</p>
      <textarea v-model="extraPrompt" rows="4" placeholder="可选：输入补充提示词内容..." class="w-full border border-gray-200 rounded-xl px-3 py-2 text-xs font-mono outline-none focus:border-pink-400 bg-white text-gray-700 resize-y box-border"></textarea>
      <div class="flex items-center gap-2 mt-2">
        <button @click="saveExtra" :disabled="extraLoading" class="px-3 py-1.5 text-xs bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 cursor-pointer border-0 disabled:opacity-50">{{ extraLoading ? '保存中...' : '💾 保存' }}</button>
        <span v-if="extraStatus" class="text-xs" :class="extraStatus.startsWith('❌')?'text-red-400':'text-green-500'">{{ extraStatus }}</span>
      </div>
    </div>

    <!-- 额度 Token 管理 -->
    <div class="border border-gray-100 rounded-xl p-3 bg-gray-50/60">
      <div class="text-sm font-semibold text-gray-700 mb-2">🎟️ 额度 Token 管理</div>
      <div class="flex items-center gap-2 mb-3">
        <label class="text-xs text-gray-600 flex items-center gap-1">
          次数上限
          <input v-model.number="maxUses" type="number" min="0" max="999999" class="w-24 border border-gray-200 rounded-xl px-2 py-1.5 text-sm outline-none focus:border-pink-400 box-border" />
          <span class="text-gray-400">（0=不限）</span>
        </label>
        <button @click="generate" :disabled="genLoading" class="px-3 py-1.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0 disabled:opacity-50" :class="genLoading?'cursor-not-allowed':''">
          {{ genLoading ? '生成中...' : '➕ 生成' }}
        </button>
        <button @click="cleanupTokens" :disabled="tLoading" class="px-3 py-1.5 bg-gray-100 text-gray-600 rounded-xl hover:bg-gray-200 text-xs font-semibold cursor-pointer border-0 disabled:opacity-50" title="清理所有已用完的额度 Token">🧹 清理失效</button>
      </div>
      <div v-if="genStatus" class="text-xs mb-2" :class="genStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ genStatus }}</div>
      <div v-if="newToken" class="flex items-center gap-2 mb-3 p-2 bg-white border border-pink-200 rounded-xl">
        <code class="flex-1 text-xs text-pink-600 font-mono break-all">{{ newToken }}</code>
        <button @click="copyToken" class="shrink-0 px-2 py-1 text-[10px] bg-pink-100 text-pink-600 rounded hover:bg-pink-200 cursor-pointer border-0">复制</button>
      </div>
      <div v-if="tLoading" class="text-xs text-gray-400">加载中...</div>
      <div v-else-if="tokens.length" class="space-y-1.5">
        <div v-for="t in tokens" :key="t.token" class="flex items-center gap-2 p-2 bg-white rounded-xl border border-gray-100">
          <div class="flex-1 min-w-0">
            <div class="text-xs font-mono text-gray-700 truncate">{{ t.token }}</div>
            <div class="text-[10px] text-gray-400">
              {{ t.used }} / {{ t.max_uses === 0 ? '∞' : t.max_uses }} 次 · 创建 {{ fmtShort(t.created_at) }} · {{ t.created_by || '未知' }}
            </div>
          </div>
          <button @click="delToken(t.token)" class="shrink-0 px-2 py-1 text-[10px] bg-red-100 text-red-500 rounded hover:bg-red-200 cursor-pointer border-0">删除</button>
        </div>
      </div>
      <div v-else class="text-xs text-gray-400">暂无 Token</div>
    </div>

  </div>
</template>
