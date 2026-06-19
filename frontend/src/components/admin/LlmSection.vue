<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const provider = ref('local')
const localEndpoint = ref('')
const googleKey = ref('')
const googleKeyMasked = ref('')
const googleModel = ref('')
const googleThinking = ref('off')
const customEndpoint = ref('')
const customKey = ref('')
const customKeyMasked = ref('')
const customModel = ref('')
const llmStream = ref(true)
const llmMaxTokens = ref(1024)
const status = ref('')
const models = ref<{ id: string; name: string }[]>([])
const showModels = ref(false)
const loading = ref(false)

const badgeText = computed(() => {
  const m: Record<string, string> = { local: '本地', google: 'Google AI Studio', custom: '自定义 API' }
  return m[provider.value] || '本地'
})
const badgeClass = computed(() => {
  const m: Record<string, string> = {
    local: 'bg-gray-200 text-gray-700',
    google: 'bg-green-500 text-white',
    custom: 'bg-purple-500 text-white',
  }
  return `ml-2 text-xs px-2 py-0.5 rounded ${m[provider.value] || m.local}`
})

function buildPayload() {
  const p: Record<string, any> = {
    provider: provider.value,
    local_endpoint: localEndpoint.value,
    google_model: googleModel.value,
    google_thinking: googleThinking.value,
    custom_endpoint: customEndpoint.value,
    custom_model: customModel.value,
    llm_stream: llmStream.value,
    llm_max_tokens: parseInt(String(llmMaxTokens.value), 10) || 1024,
  }
  if (googleKey.value) p.google_api_key = googleKey.value
  if (customKey.value) p.custom_api_key = customKey.value
  return p
}

async function load() {
  try {
    loading.value = true
    const d = await api('GET', '/api/admin/llm')
    const c = d.llm || {}
    provider.value = c.provider || 'local'
    localEndpoint.value = c.local_endpoint || ''
    googleKey.value = ''
    googleKeyMasked.value = c.google_api_key_masked || ''
    googleModel.value = c.google_model || ''
    googleThinking.value = c.google_thinking || 'off'
    customEndpoint.value = c.custom_endpoint || ''
    customKey.value = ''
    customKeyMasked.value = c.custom_api_key_masked || ''
    customModel.value = c.custom_model || ''
    llmStream.value = c.llm_stream !== false
    llmMaxTokens.value = c.llm_max_tokens || 1024
    status.value = ''
    models.value = []
    showModels.value = false
  } catch (e: any) {
    status.value = '加载失败: ' + e.message
  } finally {
    loading.value = false
  }
}

async function save() {
  try {
    status.value = '保存中…'
    await api('POST', '/api/admin/llm', buildPayload())
    googleKeyMasked.value = googleKey.value ? '****' + googleKey.value.slice(-4) : googleKeyMasked.value
    customKeyMasked.value = customKey.value ? '****' + customKey.value.slice(-4) : customKeyMasked.value
    googleKey.value = ''
    customKey.value = ''
    status.value = '✓ 已保存'
    setTimeout(() => { if (status.value === '✓ 已保存') status.value = '' }, 2000)
  } catch (e: any) {
    status.value = '保存失败: ' + e.message
  }
}

async function testConn() {
  try {
    status.value = '测试中…'
    const d = await api('POST', '/api/admin/llm/test', buildPayload())
    if (d.ok) {
      status.value = `✓ 连接成功：${d.reply || '(空回复)'}`
    } else {
      status.value = `✗ 失败：${d.error}`
    }
    setTimeout(() => { if (status.value?.startsWith('✓') || status.value?.startsWith('✗')) status.value = '' }, 6000)
  } catch (e: any) {
    status.value = '测试失败: ' + e.message
  }
}

async function detectModels() {
  try {
    status.value = '探测中…'
    showModels.value = false
    const d = await api('POST', '/api/admin/llm/models', buildPayload())
    if (!d.ok) {
      status.value = `✗ 失败：${d.error}`
      return
    }
    const list = d.models || []
    if (!list.length) {
      status.value = '未发现可用模型'
      return
    }
    models.value = list
    showModels.value = true
    status.value = `发现 ${list.length} 个模型`
  } catch (e: any) {
    status.value = '探测失败: ' + e.message
  }
}

function selectModel(id: string) {
  if (provider.value === 'google') googleModel.value = id
  else customModel.value = id
  showModels.value = false
  status.value = `已选择: ${id}`
  setTimeout(() => { status.value = '' }, 2000)
}

watch(() => provider.value, () => { showModels.value = false })
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <h2 class="text-sm font-bold text-gray-700 mb-3">
      🤖 LLM 配置
      <span :class="badgeClass">{{ badgeText }}</span>
    </h2>

    <!-- Provider radio -->
    <div class="flex items-center gap-4 text-sm mb-3 flex-wrap">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="radio" v-model="provider" value="local" class="accent-pink-500" /> LM Studio（本地）
      </label>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="radio" v-model="provider" value="google" class="accent-pink-500" /> Google AI Studio
      </label>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="radio" v-model="provider" value="custom" class="accent-pink-500" /> 自定义 API
      </label>
      <button @click="load" class="ml-auto text-xs px-3 py-1 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 cursor-pointer border-0">刷新</button>
    </div>

    <!-- Local section -->
    <div v-if="provider === 'local'" class="text-sm mb-3">
      <label class="flex flex-col gap-1 max-w-md">
        <span>本地端点</span>
        <input v-model="localEndpoint" type="text" class="border border-gray-200 rounded-lg px-2 py-1 font-mono text-xs outline-none focus:border-pink-400" placeholder="http://127.0.0.1:1234" />
        <span class="text-[10px] text-gray-500">LM Studio 本地服务地址。</span>
      </label>
    </div>

    <!-- Google section -->
    <div v-if="provider === 'google'" class="text-sm mb-3">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label class="flex flex-col gap-1">
          <span>API Key</span>
          <input v-model="googleKey" type="password" class="border border-gray-200 rounded-lg px-2 py-1 font-mono text-xs outline-none focus:border-pink-400" :placeholder="googleKeyMasked || 'AIza...'" autocomplete="off" />
          <span class="text-[10px] text-gray-500">{{ googleKeyMasked ? `当前: ${googleKeyMasked}，留空不修改` : '留空则不修改已保存的密钥。' }}</span>
        </label>
        <label class="flex flex-col gap-1">
          <span>模型</span>
          <input v-model="googleModel" type="text" class="border border-gray-200 rounded-lg px-2 py-1 font-mono text-xs outline-none focus:border-pink-400" placeholder="gemma-4-31b-it" />
          <span class="text-[10px] text-gray-500">Google AI Studio 模型 ID。</span>
        </label>
        <label class="flex flex-col gap-1">
          <span>思考 (Thinking)</span>
          <select v-model="googleThinking" class="border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400">
            <option value="off">关闭（不发送 thinkingConfig）</option>
            <optgroup label="── Gemini 3 系列 (thinkingLevel) ──">
              <option value="level_minimal">minimal（几乎不思考）</option>
              <option value="level_low">low（低延迟）</option>
              <option value="level_medium">medium（平衡）</option>
              <option value="level_high">high（深度推理，默认）</option>
            </optgroup>
            <optgroup label="── Gemini 2.5 系列 (thinkingBudget) ──">
              <option value="budget_auto">自动 (thinkingBudget=-1)</option>
              <option value="budget_0">0（关闭思考，仅 Flash/Lite）</option>
              <option value="budget_1024">1024 tokens</option>
              <option value="budget_2048">2048 tokens</option>
              <option value="budget_4096">4096 tokens</option>
              <option value="budget_8192">8192 tokens</option>
              <option value="budget_16384">16384 tokens</option>
              <option value="budget_24576">24576 tokens</option>
              <option value="budget_32768">32768 tokens</option>
            </optgroup>
          </select>
          <span class="text-[10px] text-gray-500">Gemini 3 用 thinkingLevel，Gemini 2.5 用 thinkingBudget；不支持的模型请关闭。</span>
        </label>
      </div>
    </div>

    <!-- Custom section -->
    <div v-if="provider === 'custom'" class="text-sm mb-3">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label class="flex flex-col gap-1">
          <span>API 端点</span>
          <input v-model="customEndpoint" type="text" class="border border-gray-200 rounded-lg px-2 py-1 font-mono text-xs outline-none focus:border-pink-400" placeholder="https://api.openai.com" />
          <span class="text-[10px] text-gray-500">兼容 OpenAI 格式的 Base URL。</span>
        </label>
        <label class="flex flex-col gap-1">
          <span>API 密钥</span>
          <input v-model="customKey" type="password" class="border border-gray-200 rounded-lg px-2 py-1 font-mono text-xs outline-none focus:border-pink-400" :placeholder="customKeyMasked || 'sk-...'" autocomplete="off" />
          <span class="text-[10px] text-gray-500">{{ customKeyMasked ? `当前: ${customKeyMasked}，留空不修改` : '留空则不修改已保存的密钥。' }}</span>
        </label>
        <label class="flex flex-col gap-1">
          <span>模型名称</span>
          <input v-model="customModel" type="text" class="border border-gray-200 rounded-lg px-2 py-1 font-mono text-xs outline-none focus:border-pink-400" placeholder="gpt-4o" />
          <span class="text-[10px] text-gray-500">API 的 model 参数。</span>
        </label>
      </div>
    </div>

    <!-- Stream -->
    <div class="mt-3 flex items-center gap-3 flex-wrap text-sm">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" v-model="llmStream" class="accent-pink-500" />
        <span>流式输出 (SSE)</span>
      </label>
      <span class="text-[10px] text-gray-500">关闭后使用普通请求，适用于不支持 SSE 的网络环境。</span>
    </div>

    <!-- Max tokens -->
    <div class="mt-3 flex items-center gap-3 flex-wrap text-sm">
      <label class="flex items-center gap-1">
        <span>最大 Token:</span>
        <input v-model.number="llmMaxTokens" type="number" min="1" max="32768" class="border border-gray-200 rounded-lg px-2 py-1 text-xs w-24 outline-none focus:border-pink-400" />
      </label>
      <span class="text-[10px] text-gray-500">LLM 返回的正负向提示词总上限（1-32768）。</span>
    </div>

    <!-- Buttons -->
    <div class="mt-3 flex items-center gap-2 flex-wrap">
      <button @click="save" class="px-3 py-1 bg-pink-500 text-white rounded-lg hover:bg-pink-600 text-sm cursor-pointer border-0">保存</button>
      <button @click="testConn" class="px-3 py-1 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 text-sm cursor-pointer border-0">测试连接</button>
      <button @click="detectModels" class="px-3 py-1 bg-purple-500 text-white rounded-lg hover:bg-purple-600 text-sm cursor-pointer border-0">探测模型</button>
      <span class="text-xs text-gray-500">{{ status }}</span>
    </div>

    <!-- Models list -->
    <div v-if="showModels && models.length" class="mt-2 max-h-40 overflow-y-auto border border-gray-200 rounded-lg p-2 text-xs bg-gray-50">
      <div v-for="m in models" :key="m.id" @click="selectModel(m.id)" class="flex items-center justify-between py-0.5 border-b last:border-0 cursor-pointer hover:bg-blue-50 px-1 rounded" :data-model-id="m.id">
        <span>{{ m.name || m.id }}</span>
        <span class="text-[10px] text-gray-400">{{ m.id }}</span>
      </div>
    </div>
  </div>
</template>
