<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

interface LLMProfile {
  name: string
  provider: string
  local_endpoint?: string
  google_model?: string
  google_thinking?: string
  custom_endpoint?: string
  custom_model?: string
  llm_stream?: boolean
  llm_max_tokens?: number
  has_google_key?: boolean
  has_custom_key?: boolean
  google_api_key?: string
  custom_api_key?: string
}

const profiles = ref<LLMProfile[]>([])
const activeName = ref('')
const loading = ref(false)
const status = ref('')
const showModal = ref(false)
const editProfile = ref<LLMProfile>({ name: '', provider: 'local' })
const isNewProfile = ref(false)
const testResult = ref('')
const models = ref<{ id: string; name: string }[]>([])
const showModels = ref(false)

const providerLabels: Record<string, string> = {
  local: 'LM Studio（本地）',
  google: 'Google AI Studio',
  custom: '自定义 API',
}
const providerColors: Record<string, string> = {
  local: 'bg-gray-100 text-gray-700',
  google: 'bg-green-100 text-green-700',
  custom: 'bg-purple-100 text-purple-700',
}

async function loadProfiles() {
  loading.value = true
  try {
    const d = await api('GET', '/api/admin/llm/profiles')
    profiles.value = Object.entries(d.profiles || {}).map(([name, cfg]: [string, any]) => ({ name, ...cfg }))
    activeName.value = d.active || ''
  } catch { }
  loading.value = false
}

function openNewProfile() {
  isNewProfile.value = true
  editProfile.value = { name: '', provider: 'local', llm_stream: true, llm_max_tokens: 1024 }
  testResult.value = ''
  models.value = []
  showModels.value = false
  showModal.value = true
}

function openEdit(p: LLMProfile) {
  isNewProfile.value = false
  editProfile.value = { ...p }
  testResult.value = ''
  models.value = []
  showModels.value = false
  // 加载当前完整配置
  loadProfileDetail(p.name)
  showModal.value = true
}

async function loadProfileDetail(name: string) {
  try {
    const d = await api('GET', '/api/admin/llm')
    const c = d.llm || {}
    // 只填充当前 profile 的字段，不覆盖已有字段
    if (!editProfile.value.local_endpoint) editProfile.value.local_endpoint = c.local_endpoint
    if (!editProfile.value.google_model) editProfile.value.google_model = c.google_model
    if (!editProfile.value.custom_endpoint) editProfile.value.custom_endpoint = c.custom_endpoint
    if (!editProfile.value.custom_model) editProfile.value.custom_model = c.custom_model
  } catch { }
}

async function saveProfile() {
  if (!editProfile.value.name.trim()) { alert('请输入配置名称'); return }
  try {
    const body: Record<string, any> = {
      provider: editProfile.value.provider,
      local_endpoint: editProfile.value.local_endpoint || '',
      google_model: editProfile.value.google_model || '',
      google_thinking: editProfile.value.google_thinking || 'off',
      custom_endpoint: editProfile.value.custom_endpoint || '',
      custom_model: editProfile.value.custom_model || '',
      llm_stream: editProfile.value.llm_stream ?? true,
      llm_max_tokens: editProfile.value.llm_max_tokens || 1024,
    }
    if (editProfile.value.provider === 'google' && editProfile.value.google_api_key) {
      body.google_api_key = editProfile.value.google_api_key
    }
    if (editProfile.value.provider === 'custom' && editProfile.value.custom_api_key) {
      body.custom_api_key = editProfile.value.custom_api_key
    }
    await api('POST', `/api/admin/llm/profiles/${encodeURIComponent(editProfile.value.name)}`, body)
    status.value = '✓ 已保存'
    setTimeout(() => status.value = '', 2000)
    showModal.value = false
    await loadProfiles()
  } catch (e: any) { alert('保存失败: ' + e.message) }
}

async function deleteProfile(p: LLMProfile) {
  const label = p.name === activeName.value ? `（当前激活）` : ''
  if (!confirm(`确定删除配置「${p.name}」${label}？`)) return
  if (prompt(`确认删除配置「${p.name}」，请输入"确认删除"`) !== '确认删除') { alert('输入不匹配'); return }
  try {
    await api('DELETE', `/api/admin/llm/profiles/${encodeURIComponent(p.name)}`)
    await loadProfiles()
  } catch (e: any) { alert('删除失败: ' + e.message) }
}

async function activateProfile(name: string) {
  if (name === activeName.value) return
  try {
    await api('POST', `/api/admin/llm/profiles/${encodeURIComponent(name)}/activate`)
    activeName.value = name
    status.value = `✓ 已切换至「${name}」`
    setTimeout(() => status.value = '', 2000)
  } catch (e: any) { alert('切换失败: ' + e.message) }
}

async function testConnection() {
  testResult.value = '测试中…'
  try {
    const body: Record<string, any> = {
      provider: editProfile.value.provider,
      local_endpoint: editProfile.value.local_endpoint || '',
      google_model: editProfile.value.google_model || '',
      google_thinking: editProfile.value.google_thinking || 'off',
      custom_endpoint: editProfile.value.custom_endpoint || '',
      custom_model: editProfile.value.custom_model || '',
      llm_stream: editProfile.value.llm_stream ?? true,
      llm_max_tokens: editProfile.value.llm_max_tokens || 1024,
    }
    if (editProfile.value.google_api_key) body.google_api_key = editProfile.value.google_api_key
    if (editProfile.value.custom_api_key) body.custom_api_key = editProfile.value.custom_api_key
    const d = await api('POST', '/api/admin/llm/test', body)
    testResult.value = d.ok ? `✓ 连接成功：${d.reply || ''}` : `✗ 失败：${d.error}`
  } catch (e: any) { testResult.value = '✗ 测试失败: ' + e.message }
}

async function detectModels() {
  testResult.value = '探测中…'
  showModels.value = false
  try {
    const body: Record<string, any> = {
      provider: editProfile.value.provider,
      local_endpoint: editProfile.value.local_endpoint || '',
      google_model: editProfile.value.google_model || '',
      custom_endpoint: editProfile.value.custom_endpoint || '',
      custom_model: editProfile.value.custom_model || '',
    }
    if (editProfile.value.google_api_key) body.google_api_key = editProfile.value.google_api_key
    if (editProfile.value.custom_api_key) body.custom_api_key = editProfile.value.custom_api_key
    const d = await api('POST', '/api/admin/llm/models', body)
    if (!d.ok) { testResult.value = `✗ ${d.error}`; return }
    const list = d.models || []
    if (!list.length) { testResult.value = '未发现模型'; return }
    models.value = list
    showModels.value = true
    testResult.value = `发现 ${list.length} 个模型`
  } catch (e: any) { testResult.value = '✗ 探测失败: ' + e.message }
}

function selectModel(id: string) {
  if (editProfile.value.provider === 'google') editProfile.value.google_model = id
  else editProfile.value.custom_model = id
  showModels.value = false
  testResult.value = `已选择: ${id}`
}

function profileIcon(provider: string): string {
  const icons: Record<string, string> = { local: '🖥️', google: '☁️', custom: '🔌' }
  return icons[provider] || '❓'
}

function hasKey(p: LLMProfile): boolean {
  return (p.provider === 'google' && p.has_google_key) ||
         (p.provider === 'custom' && p.has_custom_key) ||
         (p.provider === 'local')
}

onMounted(loadProfiles)
</script>

<template>
  <div v-if="visible">
    <!-- Header bar -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold text-gray-700">🤖 LLM 配置</span>
        <span v-if="activeName" class="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">
          当前: {{ activeName }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-gray-500">{{ status }}</span>
        <button @click="openNewProfile" class="px-3 py-1 bg-emerald-500 text-white rounded hover:bg-emerald-600 text-sm cursor-pointer border-0">+ 新建配置</button>
        <button @click="loadProfiles" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0">刷新</button>
      </div>
    </div>

    <!-- Profile cards grid -->
    <div v-if="!profiles.length && !loading" class="text-center text-gray-400 text-sm py-8 border-2 border-dashed border-gray-200 rounded-xl">
      暂无 LLM 配置，点击「+ 新建配置」创建
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div v-for="p in profiles" :key="p.name"
        @dblclick="activateProfile(p.name)"
        class="relative border rounded-xl p-4 cursor-pointer transition-all hover:shadow-md"
        :class="p.name === activeName ? 'border-blue-400 bg-blue-50/50 ring-2 ring-blue-200' : 'border-gray-200 bg-white hover:border-gray-300'">

        <!-- Active badge -->
        <div v-if="p.name === activeName" class="absolute top-2 right-2 text-xs px-2 py-0.5 rounded-full bg-blue-500 text-white font-medium">当前</div>

        <div class="flex items-start gap-3">
          <div class="text-2xl mt-0.5">{{ profileIcon(p.provider) }}</div>
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-gray-800 mb-1 truncate">{{ p.name }}</div>
            <div class="text-xs space-y-0.5 text-gray-500">
              <div class="flex items-center gap-1">
                <span class="px-1.5 py-0.5 rounded text-[10px]" :class="providerColors[p.provider] || 'bg-gray-100'">{{ providerLabels[p.provider] || p.provider }}</span>
              </div>
              <div v-if="p.provider === 'local' && p.local_endpoint" class="truncate font-mono text-[10px]">端点: {{ p.local_endpoint }}</div>
              <div v-if="p.provider === 'google'">
                <span>模型: {{ p.google_model || '-' }}</span>
                <span v-if="p.has_google_key" class="ml-2 text-green-600">Key ✓</span>
                <span v-else class="ml-2 text-amber-500">Key ✗</span>
              </div>
              <div v-if="p.provider === 'custom'">
                <div class="truncate font-mono text-[10px]">端点: {{ p.custom_endpoint || '-' }}</div>
                <span>模型: {{ p.custom_model || '-' }}</span>
                <span v-if="p.has_custom_key" class="ml-2 text-green-600">Key ✓</span>
                <span v-else-if="p.custom_endpoint" class="ml-2 text-amber-500">Key ✗</span>
              </div>
              <div>
                <span>流式: {{ p.llm_stream !== false ? '✓ 开' : '✗ 关' }}</span>
                <span class="ml-3">Token: {{ p.llm_max_tokens || 1024 }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Action buttons -->
        <div class="flex items-center gap-1 mt-3 pt-2 border-t border-gray-100">
          <button v-if="p.name !== activeName" @click.stop="activateProfile(p.name)" class="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 cursor-pointer border-0">激活</button>
          <button @click.stop="openEdit(p)" class="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">编辑</button>
          <button v-if="profiles.length > 1" @click.stop="deleteProfile(p)" class="text-xs px-2 py-1 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0">删除</button>
        </div>
      </div>
    </div>

    <!-- Edit/Create Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.self="showModal=false">
        <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-5 max-h-[90vh] overflow-y-auto" @click.stop>
          <h3 class="text-lg font-semibold mb-4">{{ isNewProfile ? '新建 LLM 配置' : '编辑 LLM 配置' }}</h3>

          <!-- Profile name -->
          <div class="mb-3">
            <label class="block text-sm font-medium text-gray-700 mb-1">配置名称</label>
            <input v-model="editProfile.name" type="text" class="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400 box-border" placeholder="如: 本地 LM Studio" :disabled="!isNewProfile" />
          </div>

          <!-- Provider -->
          <div class="mb-3">
            <label class="block text-sm font-medium text-gray-700 mb-1">提供商</label>
            <div class="flex items-center gap-3 flex-wrap">
              <label class="flex items-center gap-1 cursor-pointer"><input type="radio" v-model="editProfile.provider" value="local" class="accent-blue-500" /> 🖥️ LM Studio</label>
              <label class="flex items-center gap-1 cursor-pointer"><input type="radio" v-model="editProfile.provider" value="google" class="accent-blue-500" /> ☁️ Google AI Studio</label>
              <label class="flex items-center gap-1 cursor-pointer"><input type="radio" v-model="editProfile.provider" value="custom" class="accent-blue-500" /> 🔌 自定义 API</label>
            </div>
          </div>

          <!-- Fields by provider -->
          <template v-if="editProfile.provider === 'local'">
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-1">端点地址</label>
              <input v-model="editProfile.local_endpoint" type="text" class="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:border-blue-400 box-border" placeholder="http://127.0.0.1:1234" />
            </div>
          </template>

          <template v-if="editProfile.provider === 'google'">
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-1">API Key <span class="text-gray-400 font-normal">（留空不修改）</span></label>
              <input v-model="editProfile.google_api_key" type="password" class="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:border-blue-400 box-border" placeholder="AIza..." autocomplete="off" />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">模型</label>
                <input v-model="editProfile.google_model" type="text" class="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:border-blue-400 box-border" placeholder="gemma-4-31b-it" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Thinking</label>
                <select v-model="editProfile.google_thinking" class="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400 box-border">
                  <option value="off">关闭</option>
                  <optgroup label="Gemini 3 (thinkingLevel)">
                    <option value="level_minimal">minimal</option>
                    <option value="level_low">low</option>
                    <option value="level_medium">medium</option>
                    <option value="level_high">high</option>
                  </optgroup>
                  <optgroup label="Gemini 2.5 (thinkingBudget)">
                    <option value="budget_auto">auto</option>
                    <option value="budget_0">0</option>
                    <option value="budget_1024">1024</option>
                    <option value="budget_2048">2048</option>
                    <option value="budget_4096">4096</option>
                    <option value="budget_8192">8192</option>
                    <option value="budget_16384">16384</option>
                    <option value="budget_24576">24576</option>
                    <option value="budget_32768">32768</option>
                  </optgroup>
                </select>
              </div>
            </div>
          </template>

          <template v-if="editProfile.provider === 'custom'">
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-1">API 端点</label>
              <input v-model="editProfile.custom_endpoint" type="text" class="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:border-blue-400 box-border" placeholder="https://api.openai.com" />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">API 密钥 <span class="text-gray-400 font-normal">（选填）</span></label>
                <input v-model="editProfile.custom_api_key" type="password" class="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:border-blue-400 box-border" placeholder="sk-..." autocomplete="off" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">模型名称</label>
                <input v-model="editProfile.custom_model" type="text" class="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:border-blue-400 box-border" placeholder="gpt-4o" />
              </div>
            </div>
          </template>

          <!-- Common options -->
          <div class="mb-3 flex items-center gap-4 flex-wrap">
            <label class="flex items-center gap-1 cursor-pointer text-sm">
              <input type="checkbox" v-model="editProfile.llm_stream" class="accent-blue-500" /> 流式输出 (SSE)
            </label>
            <label class="flex items-center gap-1 text-sm">
              <span>最大 Token:</span>
              <input v-model.number="editProfile.llm_max_tokens" type="number" min="1" max="32768" class="w-20 border rounded px-2 py-1 text-xs outline-none" />
            </label>
          </div>

          <!-- Test & Detect -->
          <div class="flex items-center gap-2 mb-3">
            <button @click="testConnection" class="px-3 py-1 bg-emerald-500 text-white rounded hover:bg-emerald-600 text-sm cursor-pointer border-0">测试连接</button>
            <button @click="detectModels" class="px-3 py-1 bg-purple-500 text-white rounded hover:bg-purple-600 text-sm cursor-pointer border-0">探测模型</button>
            <span class="text-xs" :class="testResult.startsWith('✓') ? 'text-green-600' : testResult.startsWith('✗') ? 'text-red-500' : 'text-gray-500'">{{ testResult }}</span>
          </div>

          <!-- Model list -->
          <div v-if="showModels && models.length" class="mb-3 max-h-32 overflow-y-auto border rounded-lg p-2 text-xs bg-gray-50">
            <div v-for="m in models" :key="m.id" @click="selectModel(m.id)" class="flex items-center justify-between py-1 px-2 cursor-pointer hover:bg-blue-50 rounded">
              <span>{{ m.name || m.id }}</span>
              <span class="text-[10px] text-gray-400">{{ m.id }}</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-gray-100">
            <button @click="showModal=false" class="px-4 py-2 text-sm rounded-lg bg-gray-200 hover:bg-gray-300 cursor-pointer border-0">取消</button>
            <button @click="saveProfile" class="px-4 py-2 text-sm rounded-lg bg-blue-500 text-white hover:bg-blue-600 cursor-pointer border-0">{{ isNewProfile ? '创建配置' : '保存配置' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>