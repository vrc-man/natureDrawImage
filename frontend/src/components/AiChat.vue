<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { api } from '@/api/client'
import AiPromptPresets from '@/components/AiPromptPresets.vue'

// 模式: 'own' = 用自己的 API Key, 'token' = 用服务器额度
type Mode = 'own' | 'token'

const mode = ref<Mode>((localStorage.getItem('aiChatMode') as Mode) || 'own')
const ownEndpoint = ref(localStorage.getItem('aiChatEndpoint') || '')
const ownModel = ref(localStorage.getItem('aiChatModel') || '')
const ownKey = ref(localStorage.getItem('aiChatKey') || '')
const defaultPrompt = ref('')
const defaultTemp = ref(0.7)
const ownPrompt = ref(localStorage.getItem('aiChatSysPrompt') || '')
const ownTemp = ref(parseFloat(localStorage.getItem('aiChatTemp') || '0.7'))
// 系统提示词预设（独立弹窗组件 AiPromptPresets）
const promptPresetsRef = ref<InstanceType<typeof AiPromptPresets> | null>(null)
function openPromptPresets() { promptPresetsRef.value?.openList() }
function applyPromptPreset(text: string) { ownPrompt.value = text }

async function loadDefaultPrompt() {
  try {
    const d = await api<any>('GET', '/api/features/ai-chat/default-config')
    defaultPrompt.value = d.system_prompt || ''
    defaultTemp.value = d.temperature ?? 0.7
    ownPrompt.value = defaultPrompt.value
    ownTemp.value = defaultTemp.value
  } catch { alert('读取默认提示词失败') }
}
const token = ref(localStorage.getItem('aiChatToken') || '')
const tokenProfile = ref<any>(null)
const tokenLoading = ref(false)

interface SessionItem { id: string; name: string; messages: {role:'user'|'assistant'; text:string; reasoning?:string; image?:string; sources?:{title:string;url:string;snippet?:string}[]}[]; createdAt: number }

const sessions = ref<SessionItem[]>([])
const currentSessionId = ref('')
const showSessions = ref(false)
const renamingId = ref('')
const renameText = ref('')

const messages = ref<{role:'user'|'assistant', text:string, reasoning?:string, image?:string, sources?:{title:string;url:string;snippet?:string}[]}[]>([])
const inputText = ref('')
const sending = ref(false)
const imageBase64 = ref('')
const imagePreview = ref('')

// 设置面板
const showSettings = ref(false)
const settingMode = ref<Mode>('own')
const fullscreen = ref(false)
const modelList = ref<string[]>([])
const modelLoading = ref(false)
const testStatus = ref('')
const testLoading = ref(false)
const ownTopP = ref(parseFloat(localStorage.getItem('aiChatTopP') || '1'))
const ownTopK = ref(parseInt(localStorage.getItem('aiChatTopK') || '0'))
const ownFreqPen = ref(parseFloat(localStorage.getItem('aiChatFreqPen') || '0'))
const ownPresPen = ref(parseFloat(localStorage.getItem('aiChatPresPen') || '0'))
const ownMinP = ref(parseFloat(localStorage.getItem('aiChatMinP') || '0'))
// 采样推荐预设（Qwen 官方）
const SAMPLING_PRESETS = {
  thinking: { temp: 0.6, topP: 0.95, topK: 20, minP: 0 },
  nonThinking: { temp: 0.7, topP: 0.8, topK: 20, minP: 0 },
}
function applySamplingPreset(key: 'thinking' | 'nonThinking') {
  const p = SAMPLING_PRESETS[key]
  ownTemp.value = p.temp
  ownTopP.value = p.topP
  ownTopK.value = p.topK
  ownMinP.value = p.minP
}
function resetSampling() {
  ownTemp.value = 0.7
  ownTopP.value = 1
  ownTopK.value = 0
  ownFreqPen.value = 0
  ownPresPen.value = 0
  ownMinP.value = 0
}
const ownMaxTokens = ref(parseInt(localStorage.getItem('aiChatMaxTokens') || '4096'))
const ownContextLimit = ref(parseInt(localStorage.getItem('aiChatContextLimit') || '0'))
const msgEditMode = ref(false)

function webSearchKey() { return 'aiChatWebSearch_' + (token.value || ownKey.value.slice(-8) || 'default') }
const webSearch = ref(localStorage.getItem(webSearchKey()) === '1')
function toggleWebSearch() { webSearch.value = !webSearch.value; localStorage.setItem(webSearchKey(), webSearch.value ? '1' : '0') }

const showReasoning = ref(localStorage.getItem('aiChatShowReasoning') === '1')
function toggleShowReasoning() { showReasoning.value = !showReasoning.value; localStorage.setItem('aiChatShowReasoning', showReasoning.value ? '1' : '0') }

// 流式输出（用户可自定义，默认开）
const userStream = ref(localStorage.getItem('aiChatStream') !== '0')
function toggleUserStream() { userStream.value = !userStream.value; localStorage.setItem('aiChatStream', userStream.value ? '1' : '0') }

// 主题
type ThemeKey = 'pink' | 'blue' | 'purple' | 'green'
const themeKey = ref<ThemeKey>((localStorage.getItem('aiChatTheme') as ThemeKey) || 'pink')
const userBubbleColor = ref(localStorage.getItem('aiChatUserColor') || '#ec4899')
const userBubbleTextColor = ref(localStorage.getItem('aiChatUserTextColor') || '#ffffff')
const aiBubbleColor = ref(localStorage.getItem('aiChatAiColor') || '#f3f4f6')
const aiBubbleTextColor = ref(localStorage.getItem('aiChatAiTextColor') || '#374151')
const chatBgColor = ref(localStorage.getItem('aiChatBgColor') || '')
const cardBgColor = ref(localStorage.getItem('aiChatCardColor') || '')
const confirmDeleteId = ref('')
const confirmDeleteInput = ref('')
const confirmDeleteMode = ref<'session' | 'all'>('session')

function sessionKey() { return 'aiChatSessions_' + (token.value || ownKey.value.slice(-8) || 'default') }

function loadSessions() {
  try {
    const raw = localStorage.getItem(sessionKey())
    if (raw) {
      const data = JSON.parse(raw)
      sessions.value = data.sessions || []
      currentSessionId.value = data.currentId || ''
    } else {
      sessions.value = []
      currentSessionId.value = ''
    }
  } catch { sessions.value = []; currentSessionId.value = '' }
}

function saveSessions() {
  localStorage.setItem(sessionKey(), JSON.stringify({ sessions: sessions.value, currentId: currentSessionId.value }))
}

function saveCurrentMessages() {
  const s = sessions.value.find(x => x.id === currentSessionId.value)
  if (s) { s.messages = JSON.parse(JSON.stringify(messages.value)); saveSessions() }
}

function newSession() {
  const id = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6)
  const n = sessions.value.length + 1
  sessions.value.unshift({ id, name: '会话 ' + n, messages: [], createdAt: Date.now() })
  currentSessionId.value = id
  messages.value = []
  saveSessions()
}

function switchSession(id: string) {
  saveCurrentMessages()
  const s = sessions.value.find(x => x.id === id)
  if (!s) return
  currentSessionId.value = id
  messages.value = JSON.parse(JSON.stringify(s.messages))
  showSessions.value = false
  scrollBottom()
}

function doDeleteSession(id: string) {
  if (sessions.value.length <= 1) { return }
  sessions.value = sessions.value.filter(x => x.id !== id)
  if (currentSessionId.value === id) {
    const first = sessions.value[0]
    currentSessionId.value = first.id
    messages.value = JSON.parse(JSON.stringify(first.messages))
  }
  saveSessions()
}

function confirmDeleteSession(id: string) {
  confirmDeleteId.value = id
  confirmDeleteInput.value = ''
  confirmDeleteMode.value = 'session'
}

function confirmDeleteAll() {
  confirmDeleteId.value = ''
  confirmDeleteInput.value = ''
  confirmDeleteMode.value = 'all'
}

function executeDelete() {
  if (confirmDeleteInput.value !== '确认删除') return
  if (confirmDeleteMode.value === 'all') {
    sessions.value = []
    saveSessions()
    newSession()
  } else if (confirmDeleteId.value) {
    doDeleteSession(confirmDeleteId.value)
  }
  confirmDeleteId.value = ''
  confirmDeleteInput.value = ''
}

function startRename(id: string) {
  const s = sessions.value.find(x => x.id === id)
  if (!s) return
  renamingId.value = id
  renameText.value = s.name
}
function commitRename(id: string) {
  const s = sessions.value.find(x => x.id === id)
  if (!s) return
  s.name = renameText.value.trim() || s.name
  renamingId.value = ''
  saveSessions()
}

function autoSaveSession() {
  if (!currentSessionId.value) {
    newSession()
  }
  const s = sessions.value.find(x => x.id === currentSessionId.value)
  if (s) { s.messages = JSON.parse(JSON.stringify(messages.value)); saveSessions() }
}

function currentSessionName(): string {
  const s = sessions.value.find(x => x.id === currentSessionId.value)
  return s?.name || '新会话'
}

async function fetchModels() {
  if (!ownEndpoint.value) { alert('请先填写 API 端点'); return }
  modelLoading.value = true
  modelList.value = []
  try {
    const base = ownEndpoint.value.replace(/\/v1\/?$/i, '').replace(/\/$/, '')
    const d = await api<any>('POST', '/api/features/ai-chat/proxy', {
      method: 'GET',
      url: base + '/v1/models',
      api_key: ownKey.value,
    })
    const models: string[] = (d.data || []).map((m: any) => m.id || m).filter(Boolean)
    if (!models.length) { alert('未获取到模型列表'); return }
    modelList.value = models
    if (!ownModel.value || !models.includes(ownModel.value)) {
      ownModel.value = models[0]
    }
  } catch (e: any) {
    alert('探测失败: ' + (e.message || '未知'))
  } finally { modelLoading.value = false }
}

async function testApi() {
  const base = ownEndpoint.value.replace(/\/v1\/?$/i, '').replace(/\/$/, '')
  const model = ownModel.value || ''
  if (!base) { testStatus.value = '请先填写 API 端点'; return }
  testLoading.value = true
  testStatus.value = '测试中...'
  try {
    await api<any>('POST', '/api/features/ai-chat/proxy', {
      method: 'POST',
      url: base + '/v1/chat/completions',
      api_key: ownKey.value,
      body: {
        model: model || undefined,
        messages: [{ role: 'user', content: [{ type: 'text', text: 'Hello' }] }],
        max_tokens: 10,
      },
    })
    testStatus.value = '✅ API 连接正常'
  } catch (e: any) {
    testStatus.value = '❌ 连接失败: ' + (e.message || '未知')
  } finally { testLoading.value = false }
}

// 前端 URL 校验：必须 HTTPS 且不能是内网地址
function validateProxyUrl(url: string): string | null {
  if (!url) return null
  try {
    const u = new URL(url)
    if (u.protocol !== 'https:') return '必须使用 HTTPS 协议'
    const host = u.hostname
    // 检查常见内网模式
    if (host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]') return '不允许访问本地地址'
    if (host.startsWith('10.') || host.startsWith('192.168.') || host.startsWith('169.254.')) return '不允许访问内网地址'
    if (/^172\.(1[6-9]|2\d|3[01])\./.test(host)) return '不允许访问内网地址'
    if (host.endsWith('.local') || host.endsWith('.internal')) return '不允许访问内网地址'
  } catch { return '地址格式不正确' }
  return null
}

function saveSettings() {
  // 前端校验代理 URL
  if (mode.value === 'own' && ownEndpoint.value) {
    const err = validateProxyUrl(ownEndpoint.value)
    if (err) { alert('❌ API 端点' + err + '，请修改'); return }
  }
  localStorage.setItem('aiChatMode', mode.value)
  localStorage.setItem('aiChatEndpoint', ownEndpoint.value)
  localStorage.setItem('aiChatModel', ownModel.value)
  localStorage.setItem('aiChatKey', ownKey.value)
  localStorage.setItem('aiChatSysPrompt', ownPrompt.value)
  localStorage.setItem('aiChatTemp', String(ownTemp.value))
  localStorage.setItem('aiChatTopP', String(ownTopP.value))
  localStorage.setItem('aiChatTopK', String(ownTopK.value))
  localStorage.setItem('aiChatFreqPen', String(ownFreqPen.value))
  localStorage.setItem('aiChatPresPen', String(ownPresPen.value))
  localStorage.setItem('aiChatMinP', String(ownMinP.value))
  localStorage.setItem('aiChatContextLimit', String(ownContextLimit.value))
  localStorage.setItem('aiChatMaxTokens', String(ownMaxTokens.value))
  localStorage.setItem('aiChatToken', token.value)
  localStorage.setItem('aiChatTheme', themeKey.value)
  localStorage.setItem('aiChatUserColor', userBubbleColor.value)
  localStorage.setItem('aiChatUserTextColor', userBubbleTextColor.value)
  localStorage.setItem('aiChatAiColor', aiBubbleColor.value)
  localStorage.setItem('aiChatAiTextColor', aiBubbleTextColor.value)
  localStorage.setItem('aiChatBgColor', chatBgColor.value)
  localStorage.setItem('aiChatCardColor', cardBgColor.value)
  if (mode.value === 'token') loadProfile()
  showSettings.value = false
}

function openSettings() {
  settingMode.value = mode.value
  showSettings.value = true
}

function switchMode(next: Mode) {
  if (mode.value === next) return
  mode.value = next
  localStorage.setItem('aiChatMode', mode.value)
  if (mode.value === 'token') loadProfile()
}

async function loadProfile() {
  if (!token.value) return
  tokenLoading.value = true
  try {
    const d = await api<any>('GET', '/api/features/ai-chat/profile?token=' + encodeURIComponent(token.value))
    tokenProfile.value = d
  } catch { tokenProfile.value = null } finally { tokenLoading.value = false }
}

// 图片压缩：转 JPG，短边 ≤720，长边 ≤1024
function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(img.src)
      let w = img.width, h = img.height
      const shortSide = Math.min(w, h)
      const longSide = Math.max(w, h)
      if (shortSide > 720 || longSide > 1024) {
        const ratio = Math.min(720 / shortSide, 1024 / longSide)
        w = Math.round(w * ratio)
        h = Math.round(h * ratio)
      }
      const c = document.createElement('canvas')
      c.width = w
      c.height = h
      const ctx = c.getContext('2d')!
      ctx.drawImage(img, 0, 0, w, h)
      resolve(c.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = URL.createObjectURL(file)
  })
}

async function onImageSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const data = await compressImage(file)
    imageBase64.value = data
    imagePreview.value = data
  } catch {
    alert('图片处理失败')
  }
}
function removeImage() { imageBase64.value = ''; imagePreview.value = '' }

// 发送
async function send() {
  const text = inputText.value.trim()
  if (!text && !imageBase64.value) return
  if (sending.value) return
  if (!currentSessionId.value) newSession()

  const userMsg: any = { role: 'user', text }
  if (imageBase64.value) userMsg.image = imageBase64.value
  messages.value.push(userMsg)
  inputText.value = ''
  const imgData = imageBase64.value
  removeImage()
  sending.value = true
  scrollBottom()

  try {
    // 纯图片（无文字）：直接发送，不联网不抓取
    if (!text) {
      if (mode.value === 'own') {
        await sendOwn(text, imgData)
      } else {
        await sendToken(text, imgData, false)
      }
    } else {
      // 联网开关关闭：完全不联网（不搜索、不抓 URL）
      // 联网开关开启：消息含 URL 走抓取总结；不含 URL 走搜索
      const hasUrl = /https?:\/\//.test(text)
      const llmText = webSearch.value ? (hasUrl ? await enrichWithPage(text) : text) : text
      if (mode.value === 'own') {
        await sendOwn(llmText, imgData)
      } else {
        await sendToken(llmText, imgData, hasUrl)
      }
    }
  } catch (e: any) {
    messages.value.push({ role: 'assistant', text: '❌ 错误: ' + (e.message || '未知') })
  } finally { sending.value = false; autoSaveSession(); scrollBottom() }
}

// 提取文本中的 URL 并抓取网页内容，追加给 LLM；失败或无法识别则原样返回
async function enrichWithPage(text: string): Promise<string> {
  // 严格匹配 URL 允许字符，遇到中文/全角标点立即停止
  const m = text.match(/https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+/g)
  if (!m) return text
  let url = m[0]
  url = url.replace(/[),.;]+$/, '')
  try {
    const d = await api<any>('POST', '/api/features/ai-chat/fetch', { url })
    if (d.ok && d.text) {
      return `${text}\n\n以下是网页内容（${d.url}）：\n${d.title ? '标题：' + d.title + '\n' : ''}${d.text}`
    }
  } catch { /* 抓取失败则保持原文 */ }
  return text
}

async function sendOwn(text: string, img: string) {
  if (!ownEndpoint.value) {
    messages.value.push({ role: 'assistant', text: '请先在设置中配置 API 端点' })
    return
  }
  const err = validateProxyUrl(ownEndpoint.value)
  if (err) {
    messages.value.push({ role: 'assistant', text: '❌ 代理地址不合法: ' + err })
    return
  }
  // 构建完整 messages
  const msgs: any[] = []
  if (ownPrompt.value) {
    msgs.push({ role: 'system', content: ownPrompt.value })
  }
  // 取历史上下文（受 context_limit 控制）
  const limit = ownContextLimit.value > 0 ? ownContextLimit.value : 999999
  const history = messages.value.slice(-limit)
  for (const m of history) {
    if (m.image) {
      msgs.push({ role: m.role, content: [{ type: 'text', text: m.text }, { type: 'image_url', image_url: { url: m.image } }] })
    } else {
      msgs.push({ role: m.role, content: m.text })
    }
  }
  // 当前消息（纯图片时无 text 块）
  const curContent: any[] = []
  if (text) curContent.push({ type: 'text', text })
  if (img) curContent.push({ type: 'image_url', image_url: { url: img } })
  msgs.push({ role: 'user', content: curContent })

  const base = ownEndpoint.value.replace(/\/v1\/?$/i, '').replace(/\/$/, '')
  const body: any = {
    method: 'POST',
    url: base + '/v1/chat/completions',
    api_key: ownKey.value,
    body: {
      model: ownModel.value || undefined,
      messages: msgs,
      temperature: ownTemp.value,
      top_p: ownTopP.value,
      top_k: ownTopK.value,
      frequency_penalty: ownFreqPen.value,
      presence_penalty: ownPresPen.value,
      min_p: ownMinP.value,
      max_tokens: Math.min(50000, Math.max(1, ownMaxTokens.value || 4096)),
      stream: true,
    },
  }

  // 先插入空的 assistant 消息，流式逐块填充
  const aiMsg: any = { role: 'assistant', text: '' }
  messages.value.push(aiMsg)
  let full = ''

  try {
    const res = await fetch('/api/features/ai-chat/proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const d = await res.json().catch(() => ({}))
      throw new Error(d.detail || ('HTTP ' + res.status))
    }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        const l = line.trim()
        if (!l.startsWith('data:')) continue
        const payload = l.slice(5).trim()
        if (!payload) continue
        let ev: any = {}
        try { ev = JSON.parse(payload) } catch { continue }
        if (ev.error) { full += '\n❌ ' + ev.error; aiMsg.text = full; continue }
        const delta = ((ev.choices || [{}])[0]?.delta || {})?.content
        if (delta) { full += delta; aiMsg.text = full }
      }
    }
    if (!full) throw new Error('LLM 返回为空')
  } catch (e: any) {
    messages.value = messages.value.filter(m => m !== aiMsg)
    throw e
  }
}

async function sendToken(text: string, img: string, hasUrl: boolean = false) {
  const body: any = { token: token.value, message: text }
  body.system_prompt = ownPrompt.value
  if (ownTemp.value > 0) body.temperature = ownTemp.value
  if (img) body.image = img
  // 消息含 URL 时已前端抓取内容，不再走后端搜索，避免重复
  if (webSearch.value && !hasUrl) body.search = true
  body.max_tokens = 50000
  body.stream = userStream.value
  body.top_p = ownTopP.value
  body.top_k = ownTopK.value
  body.frequency_penalty = ownFreqPen.value
  body.presence_penalty = ownPresPen.value
  body.min_p = ownMinP.value
  // 发送全部对话历史（排除最后一条空的 assistant 占位），用户自行总结后新开会话
  if (messages.value.length > 1) {
    body.history = messages.value.slice(0, -1).map((m: any) => ({
      role: m.role,
      text: m.text,
      image: m.image || '',
    }))
  }

  // 先插入空的 assistant 消息，流式逐块填充
  const aiMsg: any = { role: 'assistant', text: '', reasoning: '' }
  messages.value.push(aiMsg)
  let full = ''
  let reasoning = ''

  try {
    const res = await fetch('/api/features/ai-chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const d = await res.json().catch(() => ({}))
      throw new Error(d.detail || ('HTTP ' + res.status))
    }
    const ctype = res.headers.get('content-type') || ''
    if (ctype.includes('text/event-stream')) {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          const l = line.trim()
          if (!l.startsWith('data:')) continue
          const payload = l.slice(5).trim()
          if (!payload) continue
          let ev: any = {}
          try { ev = JSON.parse(payload) } catch { continue }
          if (ev.kind === 'reasoning' && ev.delta) { reasoning += ev.delta; aiMsg.reasoning = reasoning }
          else if (ev.delta) { full += ev.delta; aiMsg.text = full }
          else if (ev.sources) { aiMsg.sources = ev.sources }
          else if (ev.error) { full += '\n❌ ' + ev.error; aiMsg.text = full }
        }
      }
    } else {
      const d = await res.json()
      if (!d.reply) throw new Error('服务器返回为空')
      full = d.reply
      aiMsg.text = full
      if (d.sources) aiMsg.sources = d.sources
    }
    if (!full && !reasoning) throw new Error('服务器返回为空')
  } catch (e: any) {
    // 移除空的 assistant 占位，改推错误消息
    messages.value = messages.value.filter(m => m !== aiMsg)
    throw e
  }
  if (mode.value === 'token') loadProfile()
}

// 纯前端 token 估算（中文≈1.5字/token，英文≈3.5字/token）
function estimateTokens(text: string): number {
  let tokens = 0
  for (const ch of text) {
    tokens += ch.charCodeAt(0) > 127 ? 1 / 1.5 : 1 / 3.5
  }
  return Math.round(tokens)
}

function chatTokens(): number {
  let total = 0
  for (const m of messages.value) {
    if (m.text) total += estimateTokens(m.text)
    if (m.image) total += 256 // 每张图估算 256 tokens
  }
  if (ownPrompt.value) total += estimateTokens(ownPrompt.value)
  return total
}

const estimatedTokens = ref(0)

watch(messages, () => { estimatedTokens.value = chatTokens() }, { deep: true })
watch(ownPrompt, () => { estimatedTokens.value = chatTokens() })

function scrollBottom() { nextTick(() => { const el = document.querySelector('.chat-msgs'); if (el) el.scrollTop = el.scrollHeight }) }
function scrollTop() { nextTick(() => { const el = document.querySelector('.chat-msgs'); if (el) el.scrollTop = 0 }) }

function deleteMessage(i: number) { messages.value.splice(i, 1); autoSaveSession() }
function copyMessage(text: string) { navigator.clipboard.writeText(text).then(() => {}).catch(() => {}) }

// 编辑模式批量删除：勾选 + Shift 区间选择
const selectedMsgs = ref<Set<number>>(new Set())
const lastSelIndex = ref(-1)
function toggleSelectMsg(i: number, event?: any) {
  const s = new Set(selectedMsgs.value)
  if (event?.shiftKey && lastSelIndex.value >= 0 && lastSelIndex.value !== i) {
    const a = Math.min(lastSelIndex.value, i)
    const b = Math.max(lastSelIndex.value, i)
    for (let k = a; k <= b; k++) s.add(k)
  } else if (s.has(i)) {
    s.delete(i)
  } else {
    s.add(i)
  }
  selectedMsgs.value = s
  lastSelIndex.value = i
}
function selectAllMsgs() {
  selectedMsgs.value = new Set(messages.value.map((_, i) => i))
  lastSelIndex.value = -1
}
function clearSelectedMsgs() {
  selectedMsgs.value = new Set()
  lastSelIndex.value = -1
}
function deleteSelectedMsgs() {
  const idxs = [...selectedMsgs.value].sort((a, b) => b - a)
  if (!idxs.length) return
  const count = idxs.length
  for (const i of idxs) messages.value.splice(i, 1)
  selectedMsgs.value = new Set()
  lastSelIndex.value = -1
  autoSaveSession()
  alert(`已删除 ${count} 条消息`)
}
function exportSession(messages: any[], name: string) {
  const blob = new Blob([JSON.stringify(messages, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `chat_${name}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}

// 新开窗口
function newChat() { saveCurrentMessages(); newSession(); removeImage() }

// 导出历史
function exportChat() {
  const blob = new Blob([JSON.stringify(messages.value, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `ai_chat_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  // 后台加载默认配置（不自动填充，用户点"读取默认"才用）
  try {
    const d = await api<any>('GET', '/api/features/ai-chat/default-config')
    defaultPrompt.value = d.system_prompt || ''
    defaultTemp.value = d.temperature ?? 0.7
  } catch {}
  loadSessions()
  if (currentSessionId.value) {
    const s = sessions.value.find(x => x.id === currentSessionId.value)
    if (s) messages.value = JSON.parse(JSON.stringify(s.messages))
  }
  if (!currentSessionId.value) newSession()
  if (mode.value === 'token') loadProfile()
  scrollBottom()
})
</script>

<template>
  <div class="flex flex-col h-full" :class="fullscreen ? 'fixed inset-0 z-[100]' : ''" :style="chatBgColor ? {backgroundColor: chatBgColor} : {}">
    <!-- 顶部栏 -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-pink-100 shrink-0 bg-white/80 backdrop-blur">
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <button @click="showSessions=true" class="shrink-0 text-xs px-2 py-1 rounded-lg cursor-pointer border-0 bg-transparent hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400" title="会话管理">☰</button>
        <button @click="showSessions=true" class="text-sm font-semibold text-gray-700 dark:text-gray-200 truncate cursor-pointer border-0 bg-transparent hover:text-pink-500 text-left">{{ currentSessionName() }}</button>
        <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full" :class="mode==='own'?'bg-blue-100 text-blue-600':'bg-green-100 text-green-600'">{{ mode==='own'?'自用':'额度' }}</span>
        <button @click="switchMode(mode==='own'?'token':'own')" class="shrink-0 text-[10px] px-2 py-1 rounded-lg cursor-pointer border-0" :class="mode==='own'?'bg-blue-50 text-blue-600 hover:bg-blue-100':'bg-green-50 text-green-600 hover:bg-green-100'" title="切换模式：自用 Key / 服务器额度">{{ mode==='own' ? '切额度' : '切自用' }}</button>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <button @click="fullscreen=!fullscreen" class="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0 dark:text-gray-300" :title="fullscreen?'退出全屏':'全屏'">{{ fullscreen ? '🗕' : '⛶' }}</button>
        <button @click="newChat" class="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0 dark:text-gray-300" title="新会话">📝</button>
        <button @click="exportChat" class="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0 dark:text-gray-300" title="导出对话">⬇️</button>
        <button @click="msgEditMode = !msgEditMode; if (!msgEditMode) clearSelectedMsgs()" class="text-xs px-2 py-1 rounded cursor-pointer border-0" :class="msgEditMode?'bg-pink-500 text-white':'bg-gray-100 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'" title="编辑消息">{{ msgEditMode ? '✕完成' : '✎编辑' }}</button>
        <button @click="scrollTop" class="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0 dark:text-gray-300" title="回到最顶">⏫</button>
        <button @click="scrollBottom" class="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0 dark:text-gray-300" title="跳到最新">⏬</button>
        <button @click="openSettings" class="text-xs px-2 py-1 rounded cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600">⚙️</button>
      </div>
    </div>

    <!-- 会话管理弹窗 -->
    <div v-if="showSessions" class="fixed inset-0 z-[60] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-sm w-full p-5 max-h-[70vh] flex flex-col">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-bold text-gray-700 dark:text-gray-200">📋 会话管理</h3>
          <div class="flex items-center gap-2">
            <span class="text-[10px] text-gray-400">{{ sessions.length }} 个</span>
            <button @click="confirmDeleteAll" class="text-xs text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent" title="清空所有">🗑</button>
            <button @click="showSessions=false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">&times;</button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto space-y-1.5 min-h-0">
          <div v-for="s in sessions" :key="s.id" class="flex items-center gap-1.5 px-3 py-2.5 rounded-xl cursor-pointer text-sm" :class="s.id===currentSessionId?'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300':'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400'" @click="switchSession(s.id)">
            <template v-if="renamingId===s.id">
              <input v-model="renameText" class="flex-1 border border-pink-300 dark:border-pink-600 rounded-lg px-2 py-1 text-sm outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" @blur="commitRename(s.id)" @keydown.enter="commitRename(s.id)" @click.stop autofocus />
            </template>
            <template v-else>
              <span class="flex-1 truncate" @dblclick.stop="startRename(s.id)">{{ s.name }}</span>
            </template>
            <span class="text-xs text-gray-400 shrink-0">{{ s.messages.length }}</span>
            <button @click.stop="exportSession(s.messages, s.name)" class="text-gray-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent px-1 text-sm" title="导出">⬇</button>
            <button @click.stop="confirmDeleteSession(s.id)" class="text-gray-400 hover:text-red-500 cursor-pointer border-0 bg-transparent px-1 text-sm" title="删除">✕</button>
          </div>
        </div>
        <div class="text-[10px] text-gray-400 text-center pt-2">双击会话名称可重命名</div>
      </div>
    </div>

    <!-- 消息列表 -->
    <div class="flex-1 overflow-y-auto p-3 space-y-3 chat-msgs">
      <div v-if="!messages.length" class="text-center text-xs text-gray-400 dark:text-gray-500 py-8">
        <p class="text-lg mb-1">🤖</p>
        <p>发送消息开始对话</p>
        <p class="mt-1">支持上传图片进行反推/改写</p>
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="flex flex-col" :class="msg.role==='user'?'items-end':'items-start'">
        <div class="flex items-center gap-1.5 w-full" :class="msg.role==='user'?'justify-end':'justify-start'">
          <input v-if="msgEditMode" type="checkbox" :checked="selectedMsgs.has(i)" @change="toggleSelectMsg(i)" @click.stop class="w-4 h-4 accent-pink-500 cursor-pointer shrink-0" :class="msg.role==='user'?'order-last':''" />
          <div class="max-w-[85%] rounded-2xl px-3 py-2 text-sm overflow-hidden cursor-default" :style="msg.role==='user'?{backgroundColor:userBubbleColor,color:userBubbleTextColor}:{backgroundColor:aiBubbleColor,color:aiBubbleTextColor}" :class="[msg.role==='user'?'rounded-br-md':'rounded-bl-md', msgEditMode && selectedMsgs.has(i) ? 'ring-2 ring-pink-400' : '']" @click="msgEditMode && toggleSelectMsg(i)">
            <img v-if="msg.image" :src="msg.image" class="max-w-[200px] max-h-[200px] rounded-lg mb-1" />
            <div v-if="msg.role==='assistant' && showReasoning && msg.reasoning" class="mb-2 text-xs italic whitespace-pre-wrap break-words border-l-2 pl-2" style="border-color:currentColor;opacity:0.6;overflow-wrap:anywhere;min-width:0">{{ msg.reasoning }}</div>
            <div class="whitespace-pre-wrap break-words" style="overflow-wrap:anywhere;min-width:0">{{ msg.text }}</div>
            <div v-if="msg.role==='assistant' && msg.sources && msg.sources.length" class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600">
              <div class="text-[10px] text-gray-400 mb-1">来源：</div>
              <div v-for="(s, si) in msg.sources.slice(0, 5)" :key="si" class="flex items-center gap-1 text-[11px] leading-tight">
                <span class="text-gray-400">·</span>
                <a v-if="s.url" :href="s.url" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline truncate cursor-pointer" :title="s.url">{{ s.title || s.url }}</a>
                <span v-else class="text-gray-600 dark:text-gray-300 truncate">{{ s.title || '' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="msgEditMode" class="flex gap-1 mt-1 px-1">
          <button @click="copyMessage(msg.text)" class="text-[9px] px-1.5 py-0.5 rounded bg-pink-100 dark:bg-pink-900 text-pink-600 dark:text-pink-300 hover:bg-pink-200 cursor-pointer border-0" title="复制">📋 复制</button>
          <button @click="deleteMessage(i)" class="text-[9px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900 text-red-500 dark:text-red-300 hover:bg-red-200 cursor-pointer border-0" title="删除">✕ 删除</button>
        </div>
      </div>

      <!-- 批量删除工具栏 -->
      <div v-if="msgEditMode" class="sticky bottom-0 pt-2">
        <div class="flex items-center justify-between gap-2 px-3 py-2 bg-white/95 dark:bg-gray-800/95 backdrop-blur rounded-xl border border-pink-200 dark:border-gray-600 shadow-lg">
          <div class="flex items-center gap-1 text-[11px] text-gray-600 dark:text-gray-300">
            <button @click="selectAllMsgs" class="px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0">全选</button>
            <button @click="clearSelectedMsgs" class="px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0" :disabled="!selectedMsgs.size">取消</button>
            <span class="ml-1 text-gray-400">{{ selectedMsgs.size }} 已选</span>
          </div>
          <button @click="deleteSelectedMsgs" :disabled="!selectedMsgs.size" class="px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer border-0" :class="selectedMsgs.size?'bg-red-500 text-white hover:bg-red-600':'bg-gray-200 text-gray-400 cursor-not-allowed'">🗑 删除选中 ({{ selectedMsgs.size }})</button>
        </div>
        <p class="text-[10px] text-gray-400 text-center mt-1">点气泡勾选 · Shift+点击 = 区间选择</p>
      </div>
    </div>

    <!-- 图片预览 -->
    <div v-if="imagePreview" class="relative px-3 py-1 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0">
      <img :src="imagePreview" class="max-w-[80px] max-h-[80px] rounded-lg border border-gray-200 dark:border-gray-600" />
      <button @click="removeImage" class="absolute top-0 left-0 w-5 h-5 bg-black/50 text-white rounded-full text-xs flex items-center justify-center cursor-pointer border-0">✕</button>
    </div>

    <!-- 输入区 -->
    <div class="flex items-center gap-2 px-3 pt-2 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0">
      <button v-if="mode==='token'" @click="toggleWebSearch" class="flex items-center gap-1.5 text-[11px] cursor-pointer select-none shrink-0 border-0 bg-transparent p-1 -m-1" :class="webSearch?'text-pink-500 font-medium':'text-gray-500 dark:text-gray-400'">
        <span class="relative inline-block rounded-full transition-colors" :class="webSearch?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'" style="width:28px;height:18px">
          <span class="absolute bg-white rounded-full transition-all" :class="webSearch?'left-4':'left-0.5'" style="top:2px;width:14px;height:14px"></span>
        </span>
        <span>🔍 联网</span>
      </button>
    </div>
    <div class="flex items-stretch gap-2 p-3 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0">
      <label class="shrink-0 cursor-pointer flex items-center justify-center">
        <input type="file" accept="image/*" class="hidden" @change="onImageSelected" />
        <span class="text-2xl leading-none text-gray-400 dark:text-gray-500 hover:text-pink-500">📷</span>
      </label>
      <textarea v-model="inputText" rows="2" class="flex-1 border border-pink-200 dark:border-gray-500 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 resize-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500" placeholder="输入消息..." @keydown.enter.ctrl="send"></textarea>
      <button @click="send" :disabled="sending || (!inputText.trim() && !imageBase64)" class="shrink-0 px-4 rounded-xl bg-gradient-to-r from-pink-400 to-rose-400 text-white text-sm font-semibold hover:from-pink-300 hover:to-rose-300 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer border-0 flex items-center justify-center gap-1">
        <span v-if="sending" class="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"></span>
        {{ sending ? '...' : '发送' }}
      </button>
    </div>

    <!-- Token 用量 / 额度显示 -->
    <div class="shrink-0 px-3 py-1 border-t border-gray-100 dark:border-gray-600 text-[10px] text-gray-400 dark:text-gray-500 flex items-center gap-3" :class="mode==='token' ? 'bg-gray-50 dark:bg-gray-800' : 'bg-white dark:bg-gray-800'">
      <template v-if="mode==='token' && tokenProfile">
        <span>额度: {{ tokenProfile.remaining ?? '?' }}/{{ tokenProfile.max_uses ?? '?' }}</span>
        <span :class="(tokenProfile.remaining ?? 0) > 0 ? 'text-green-500' : 'text-red-500'">●</span>
      </template>
      <span class="ml-auto">上下文: ~{{ chatTokens() }} tokens</span>
    </div>

    <!-- 确认删除弹窗 -->
    <div v-if="confirmDeleteId || confirmDeleteMode==='all'" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-xs w-full p-5">
        <h4 class="text-sm font-bold text-gray-700 dark:text-gray-200 mb-2">⚠️ 确认删除</h4>
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">{{ confirmDeleteMode==='all' ? '确定删除所有会话？此操作不可恢复。' : '确定删除此会话？此操作不可恢复。' }}</p>
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">请输入"确认删除"以继续：</p>
        <input v-model="confirmDeleteInput" type="text" placeholder='输入"确认删除"' class="w-full border border-gray-200 dark:border-gray-600 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 mb-3" @keydown.enter="executeDelete" />
        <div class="flex gap-2">
          <button @click="confirmDeleteId='';confirmDeleteMode='session'" class="flex-1 py-2 bg-gray-100 dark:bg-gray-700 rounded-xl hover:bg-gray-200 dark:hover:bg-gray-600 text-sm text-gray-600 dark:text-gray-300 cursor-pointer border-0">取消</button>
          <button @click="executeDelete" :disabled="confirmDeleteInput!=='确认删除'" class="flex-1 py-2 bg-red-500 text-white rounded-xl hover:bg-red-600 text-sm font-semibold cursor-pointer border-0 disabled:opacity-40">确认删除</button>
        </div>
      </div>
    </div>

    <!-- 设置弹窗 -->
    <div v-if="showSettings" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl shadow-xl max-w-sm w-full max-h-[80vh] flex flex-col overflow-hidden">
        <div class="flex items-center justify-between px-5 py-3 shrink-0 bg-white border-b border-gray-100">
          <h3 class="text-base font-bold text-gray-700">⚙️ AI 助手设置</h3>
          <button @click="showSettings=false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">&times;</button>
        </div>
        <div class="flex-1 overflow-y-auto px-5 py-4">

        <!-- 模式选择 -->
        <div class="flex gap-2 mb-3">
          <button @click="settingMode='own'" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0" :class="settingMode==='own'?'bg-blue-500 text-white':'bg-gray-100 text-gray-600'">用自己的 Key</button>
          <button @click="settingMode='token'" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0" :class="settingMode==='token'?'bg-green-500 text-white':'bg-gray-100 text-gray-600'">用额度 Token</button>
        </div>

        <template v-if="settingMode==='own'">
          <label class="block text-xs text-gray-600 mb-2">
            API 端点
            <input v-model="ownEndpoint" type="url" placeholder="https://api.openai.com/v1" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
          </label>
          <label class="block text-xs text-gray-600 mb-2">
            API Key
            <input v-model="ownKey" type="password" placeholder="sk-..." class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
          </label>
          <label class="block text-xs text-gray-600 mb-2">
            模型
            <div class="flex gap-1 mt-1">
              <select v-model="ownModel" class="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 bg-white">
                <option value="" disabled>选择模型</option>
                <option v-for="m in modelList" :key="m" :value="m">{{ m }}</option>
              </select>
              <button @click="fetchModels" :disabled="modelLoading" class="shrink-0 px-3 py-2 rounded-xl text-xs cursor-pointer border-0" :class="modelLoading?'bg-gray-200 text-gray-400 cursor-not-allowed':'bg-blue-100 text-blue-600 hover:bg-blue-200'">{{ modelLoading ? '...' : '🔍 探测' }}</button>
            </div>
            <div class="flex gap-1 mt-1">
              <input v-model="ownModel" type="text" placeholder="或手动输入模型名" class="flex-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
            </div>
          </label>
          <div class="flex gap-2 mb-3">
            <button @click="testApi" :disabled="testLoading" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 flex items-center justify-center gap-1" :class="testLoading?'bg-gray-200 text-gray-400 cursor-not-allowed':'bg-green-100 text-green-700 hover:bg-green-200'">
              <span v-if="testLoading" class="inline-block w-3 h-3 border-2 border-green-400 border-t-green-700 rounded-full animate-spin"></span>
              {{ testLoading ? '测试中...' : '🧪 测试 API' }}
            </button>
          </div>
          <div v-if="testStatus" class="text-xs mb-3 px-2 py-1.5 rounded-lg" :class="testStatus.startsWith('✅')?'bg-green-50 text-green-700':'bg-red-50 text-red-600'">{{ testStatus }}</div>
        </template>
        <template v-else>
          <label class="block text-xs text-gray-600 mb-2">
            额度 Token
            <input v-model="token" type="text" placeholder="ai_chat_xxx" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
          </label>
          <div v-if="tokenProfile" class="text-xs text-gray-500 mb-2">
            剩余: {{ tokenProfile.remaining ?? '?' }} / {{ tokenProfile.max_uses ?? '?' }} 次
          </div>
        </template>

        <label class="block text-xs text-gray-600 mb-2">
          <div class="flex items-center justify-between mb-1">
            <span>系统提示词</span>
            <button @click="openPromptPresets" class="text-[10px] px-2 py-1 rounded-lg cursor-pointer border-0 bg-pink-100 dark:bg-pink-900 text-pink-600 dark:text-pink-300 hover:bg-pink-200">📝 管理预设</button>
          </div>
          <textarea id="aiChatSysPromptTa" v-model="ownPrompt" rows="4" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border resize-y font-mono text-[11px]" placeholder="可在此自定义系统提示词，或点击下方加载后台默认"></textarea>
          <button @click="loadDefaultPrompt" class="mt-1 text-[10px] text-pink-500 hover:text-pink-600 cursor-pointer border-0 bg-transparent">📥 读取后台默认</button>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          温度 (0-2)
          <div class="flex items-center gap-2">
            <input v-model.number="ownTemp" type="range" min="0" max="2" step="0.1" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-8 text-right">{{ ownTemp }}</span>
          </div>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          top_p (0-1)
          <div class="flex items-center gap-2">
            <input v-model.number="ownTopP" type="range" min="0" max="1" step="0.05" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-8 text-right">{{ ownTopP }}</span>
          </div>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          top_k (0-200，0=不限制)
          <div class="flex items-center gap-2">
            <input v-model.number="ownTopK" type="range" min="0" max="200" step="1" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-8 text-right">{{ ownTopK }}</span>
          </div>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          重复惩罚 frequency_penalty (-2~2)
          <div class="flex items-center gap-2">
            <input v-model.number="ownFreqPen" type="range" min="-2" max="2" step="0.1" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-10 text-right">{{ ownFreqPen.toFixed(1) }}</span>
          </div>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          存在惩罚 presence_penalty (-2~2)
          <div class="flex items-center gap-2">
            <input v-model.number="ownPresPen" type="range" min="-2" max="2" step="0.1" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-10 text-right">{{ ownPresPen.toFixed(1) }}</span>
          </div>
        </label>
        <label class="block text-xs text-gray-600 mb-2">
          min_p (0-1，0=不限制)
          <div class="flex items-center gap-2">
            <input v-model.number="ownMinP" type="range" min="0" max="1" step="0.05" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-8 text-right">{{ ownMinP }}</span>
          </div>
        </label>
        <div class="flex gap-1.5 mb-2 flex-wrap">
          <button @click="applySamplingPreset('thinking')" class="px-2 py-1 text-[10px] rounded-lg cursor-pointer border-0 bg-blue-100 text-blue-600 hover:bg-blue-200">🧠 思考模式推荐 (0.6/0.95/20)</button>
          <button @click="applySamplingPreset('nonThinking')" class="px-2 py-1 text-[10px] rounded-lg cursor-pointer border-0 bg-purple-100 text-purple-600 hover:bg-purple-200">⚡ 非思考推荐 (0.7/0.8/20)</button>
          <button @click="resetSampling" class="px-2 py-1 text-[10px] rounded-lg cursor-pointer border-0 bg-gray-100 text-gray-500 hover:bg-gray-200">↺ 恢复默认</button>
        </div>
        <label class="block text-xs text-gray-600 mb-2">
          最大输出 tokens（1-50000）
          <div class="flex items-center gap-2">
            <input v-model.number="ownMaxTokens" type="range" min="1" max="50000" step="128" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
            <span class="text-sm text-gray-600 w-14 text-right">{{ ownMaxTokens }}</span>
          </div>
        </label>
        <label v-if="settingMode === 'token'" class="flex items-center justify-between gap-2 text-xs text-gray-600 dark:text-gray-400 mb-2">
          <span>🔍 联网 <span class="text-gray-400">（自动搜索并读取网页内容）</span></span>
          <button @click="toggleWebSearch" class="relative w-10 h-5 rounded-full transition-colors cursor-pointer border-0" :class="webSearch?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'">
            <span class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all" :class="webSearch?'left-5.5':'left-0.5'"></span>
          </button>
        </label>
        <label class="flex items-center justify-between gap-2 text-xs text-gray-600 dark:text-gray-400 mb-2">
          <span>🧠 显示思考过程</span>
          <button @click="toggleShowReasoning" class="relative w-10 h-5 rounded-full transition-colors cursor-pointer border-0" :class="showReasoning?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'">
            <span class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all" :class="showReasoning?'left-5.5':'left-0.5'"></span>
          </button>
        </label>
        <label class="flex items-center justify-between gap-2 text-xs text-gray-600 dark:text-gray-400 mb-2">
          <span>⚡ 流式输出 <span class="text-gray-400">（关=更稳定，长回答不中断）</span></span>
          <button @click="toggleUserStream" class="relative w-10 h-5 rounded-full transition-colors cursor-pointer border-0" :class="userStream?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'">
            <span class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all" :class="userStream?'left-5.5':'left-0.5'"></span>
          </button>
        </label>
        <hr class="my-3 border-gray-200 dark:border-gray-600" />
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">🎨 主题与气泡颜色</div>

        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-2">
          主题色
          <div class="flex gap-2 mt-1">
            <button v-for="t in (['pink','blue','purple','green'] as const)" :key="t" @click="themeKey=t" class="flex-1 py-1.5 rounded-xl text-[10px] font-semibold cursor-pointer border-0" :class="themeKey===t?'ring-2 ring-offset-1 text-white':''" :style="{backgroundColor:t==='pink'?'#ec4899':t==='blue'?'#3b82f6':t==='purple'?'#8b5cf6':'#10b981',color:themeKey===t?'#fff':''}">{{ {pink:'粉',blue:'蓝',purple:'紫',green:'绿'}[t] }}</button>
          </div>
        </label>

        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-2">
          自己气泡颜色
          <input v-model="userBubbleColor" type="color" class="mt-1 w-full h-8 rounded-xl border border-gray-200 cursor-pointer box-border" />
        </label>
        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-2">
          自己气泡文字色
          <input v-model="userBubbleTextColor" type="color" class="mt-1 w-full h-8 rounded-xl border border-gray-200 cursor-pointer box-border" />
        </label>
        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-2">
          AI 气泡背景色
          <input v-model="aiBubbleColor" type="color" class="mt-1 w-full h-8 rounded-xl border border-gray-200 cursor-pointer box-border" />
        </label>
        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-2">
          AI 气泡文字色
          <input v-model="aiBubbleTextColor" type="color" class="mt-1 w-full h-8 rounded-xl border border-gray-200 cursor-pointer box-border" />
        </label>
        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-2">
          聊天面板背景色
          <input v-model="chatBgColor" type="color" class="mt-1 w-full h-8 rounded-xl border border-gray-200 cursor-pointer box-border" />
          <button @click="chatBgColor=''" class="text-[10px] text-gray-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">重置</button>
        </label>
        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-3">
          卡片/列表背景色
          <input v-model="cardBgColor" type="color" class="mt-1 w-full h-8 rounded-xl border border-gray-200 cursor-pointer box-border" />
          <button @click="cardBgColor=''" class="text-[10px] text-gray-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">重置</button>
        </label>

        <div class="flex gap-2">
          <button @click="showSettings=false" class="flex-1 py-2 bg-gray-100 dark:bg-gray-700 rounded-xl hover:bg-gray-200 dark:hover:bg-gray-600 text-sm text-gray-600 dark:text-gray-300 cursor-pointer border-0">取消</button>
          <button @click="saveSettings" class="flex-1 py-2 rounded-xl text-sm font-semibold cursor-pointer border-0 text-white" :style="{backgroundColor:themeKey==='pink'?'#ec4899':themeKey==='blue'?'#3b82f6':themeKey==='purple'?'#8b5cf6':'#10b981'}">保存</button>
        </div>
        </div>
      </div>
    </div>

    <!-- 系统提示词预设弹窗 -->
    <AiPromptPresets ref="promptPresetsRef" :on-fill="applyPromptPreset" />
  </div>
</template>
