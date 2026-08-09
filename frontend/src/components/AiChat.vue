<script setup lang="ts">
import { ref, onMounted, nextTick, watch, computed } from 'vue'
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

interface GenCardData { prompt: string; negative_prompt: string; width: number; height: number; character: string; style: string; result?: string[]; userReq?: string }
interface SessionItem { id: string; name: string; messages: {role:'user'|'assistant'; text:string; reasoning?:string; reasoningOpen?:boolean; image?:string; selectedChips?:{type:string;name:string;rawIdx:number}[]; genMeta?:any; genCard?:GenCardData; genCardStatus?:string; genCardStatusText?:string; reverseResult?:any; sources?:{title:string;url:string;snippet?:string}[]}[]; createdAt: number }

const sessions = ref<SessionItem[]>([])
const currentSessionId = ref('')
const showSessions = ref(false)
const renamingId = ref('')
const renameText = ref('')

const messages = ref<{role:'user'|'assistant', text:string, reasoning?:string, reasoningOpen?:boolean, image?:string, selectedChips?:{type:string;name:string;rawIdx:number}[], genMeta?:any, genCard?:GenCardData, genCardStatus?:string, genCardStatusText?:string, reverseResult?:any, sources?:{title:string;url:string;snippet?:string}[]}[]>([])
const inputText = ref('')
const sending = ref(false)
const imageBase64 = ref('')
const imagePreview = ref('')
const viewImage = ref('')
const pendingQuestion = ref<{ question: string; options: string[] } | null>(null)
const questionAnswer = ref('')

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

// 生图助手模式：AI 用生图工具自主决策（仿 2x.nz）；关闭则走普通联网搜索对话
const genMode = ref(localStorage.getItem('aiChatGenMode') !== '0')
function toggleGenMode() { genMode.value = !genMode.value; localStorage.setItem('aiChatGenMode', genMode.value ? '1' : '0') }

// 顶部生图配置条
const showWfPicker = ref(false)
const genCustomChar = ref('')
const genCustomStyle = ref('')
function genWorkflowName() {
  const p = genConfig.value.workflow_path || ''
  if (!p) return ''
  return p.replace(/\.json$/i, '').split('/').pop() || p
}
function openWorkflowPicker() {
  loadGenWorkflows()
  showWfPicker.value = true
}
function applyCustomChar() {
  const v = genCustomChar.value.trim()
  if (!v) return
  const existing = genConfig.value.character ? genConfig.value.character + ', ' : ''
  genConfig.value.character = existing + v
  const nExisting = genConfig.value.characterName ? genConfig.value.characterName + ', ' : ''
  genConfig.value.characterName = nExisting + v
  genConfig.value.characterCats = [...genConfig.value.characterCats, '']
  genCustomChar.value = ''
  genShowCharPicker.value = false
}
function applyCustomStyle() {
  const v = genCustomStyle.value.trim()
  if (!v) return
  genConfig.value.style = v
  genConfig.value.styleName = v
  genConfig.value.styleCat = ''
  genCustomStyle.value = ''
  genShowStylePicker.value = false
}

const showReasoning = ref(localStorage.getItem('aiChatShowReasoning') !== '0')
function toggleShowReasoning() { showReasoning.value = !showReasoning.value; localStorage.setItem('aiChatShowReasoning', showReasoning.value ? '1' : '0') }
const autoApprove = ref(localStorage.getItem('aiChatAutoApprove') === '1')
function toggleAutoApprove() { autoApprove.value = !autoApprove.value; localStorage.setItem('aiChatAutoApprove', autoApprove.value ? '1' : '0') }

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
const bubbleFontSize = ref(parseInt(localStorage.getItem('aiChatBubbleFontSize') || '14'))
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
  // 新会话清空顶部已选角色/画风，避免残留干扰 AI 决策
  genConfig.value.character = ''
  genConfig.value.characterName = ''
  genConfig.value.characterCats = []
  genConfig.value.style = ''
  genConfig.value.styleName = ''
  genConfig.value.styleCat = ''
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
  localStorage.setItem('aiChatBubbleFontSize', String(bubbleFontSize.value))
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

// 回答 AI 的反问，继续多轮对话
async function answerQuestion(ans: string) {
  const a = (ans || questionAnswer.value || '').trim()
  if (!a || !pendingQuestion.value) return
  pendingQuestion.value = null
  questionAnswer.value = ''
  const userMsg: any = { role: 'user', text: a }
  messages.value.push(userMsg)
  sending.value = true
  scrollBottom()
  try {
    if (mode.value === 'own') {
      await sendOwn(a, '')
    } else {
      await sendToken(a, '', false)
    }
  } catch (e: any) {
    messages.value.push({ role: 'assistant', text: '❌ 错误: ' + (e.message || '未知') })
  } finally { sending.value = false; autoSaveSession(); scrollBottom() }
}

// 发送
async function send() {
  const text = inputText.value.trim()
  if (!text && !imageBase64.value) return
  if (sending.value) return
  if (!currentSessionId.value) newSession()

  // 微调模式：发消息给 AI 基于当前卡片生成新卡
  if (discussMode.value && discussTargetIndex.value >= 0) {
    const ctxText = text
    inputText.value = ''
    discussMode.value = false
    const tidx = discussTargetIndex.value
    discussTargetIndex.value = -1
    const cardMsg = messages.value[tidx]
    const card = cardMsg && cardMsg.genCard
    // 显式带上当前工作流，AI 按该工作流模型规则调整；强制走生图工具生成新卡
    const wfPath = genConfig.value.workflow_path || ''
    const wfName = wfPath ? String(wfPath).split(/[\\/]/).pop() : '未指定'
    const ctx = card ? `（当前生图卡片：正向=${card.prompt}；反向=${card.negative_prompt}；尺寸=${card.width}x${card.height}；角色=${card.character}；画风=${card.style}；当前工作流=${wfName}）\n请在保留原有内容基础上，根据我的新要求调整：${ctxText}\n\n请立即调用生图工具（trigger_generation）生成一张更新后的「审核生图参数」卡片。` : ctxText
    const userMsg: any = { role: 'user', text: ctx }
    messages.value.push(userMsg)
    sending.value = true
    scrollBottom()
    try {
      if (mode.value === 'own') await sendOwn(ctx, '')
      else await sendToken(ctx, '', false, true)
    } catch (e: any) {
      messages.value.push({ role: 'assistant', text: '❌ 错误: ' + (e.message || '未知') })
    } finally { sending.value = false; autoSaveSession(); scrollBottom() }
    return
  }

  const userMsg: any = { role: 'user', text }
  if (imageBase64.value) userMsg.image = imageBase64.value
  if (genMode.value && genSelectedChips.value.length) userMsg.selectedChips = genSelectedChips.value.slice()
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
      // 用户明确表达生图意图（确认词 / 生成卡片 / 生图 / 画）→ 强制走生成审核卡片流程
      const genIntent = isConfirmWord(text) || /(生成卡片|生图|出图|生成图片|生成吧|开始生成|画一张|画个|画一只|画一个|直接生成|来一张)/i.test(text)
      if (genIntent && mode.value !== 'own') {
        const cardMsg = llmText + '\n\n请立即调用生图工具（trigger_generation）生成一张「审核生图参数」卡片，包含正/负提示词、尺寸、角色、画风。'
        await sendToken(cardMsg, imgData, hasUrl, true)
      } else if (mode.value === 'own') {
        await sendOwn(llmText, imgData)
      } else {
        // 生图模式开着：即使消息未触发生图意图词，也强制 AI 一次生成审核卡片（避免需重复强调才生成）
        let finalMsg = llmText
        if (genMode.value) {
          finalMsg = llmText + '\n\n请立即调用生图工具（trigger_generation）生成一张「审核生图参数」卡片，包含正/负提示词、尺寸、角色、画风。'
        }
        await sendToken(finalMsg, imgData, hasUrl, genMode.value)
      }
    }
  } catch (e: any) {
    messages.value.push({ role: 'assistant', text: '❌ 错误: ' + (e.message || '未知') })
  } finally { sending.value = false; autoSaveSession(); scrollBottom() }
}

// 判断用户消息是否为确认词（触发生成审核卡片）
function isConfirmWord(t: string): boolean {
  const s = (t || '').trim().toLowerCase().replace(/[。！!？?~～\s,，.]+$/g, '')
  if (!s || s.length > 10) return false
  return /^(确定|确认|就这样|可以|生成吧|开始吧|ok|好的|yes|对|嗯|行|没问题|就这个|按这个)$/.test(s)
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
  // 取历史上下文（受 context_limit 控制）。历史只发文本，过滤图片（气泡里的图/生图结果不发 LLM）
  const limit = ownContextLimit.value > 0 ? ownContextLimit.value : 999999
  const history = messages.value.slice(-limit)
  for (const m of history) {
    msgs.push({ role: m.role, content: m.text })
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

async function sendToken(text: string, img: string, hasUrl: boolean = false, genMode: boolean = false) {
  const msgText = text
  const body: any = { token: token.value, message: msgText }
  // 顶部已选角色/画风作为独立字段传给后端（AI 决策参考），不混入气泡文本
  if (genMode) {
    if (genConfig.value.character.trim()) body.selected_characters = (genConfig.value.characterName || genConfig.value.character).trim()
    if (genConfig.value.style.trim()) body.selected_style = (genConfig.value.styleName || genConfig.value.style).trim()
  }
  body.system_prompt = ownPrompt.value
  if (ownTemp.value > 0) body.temperature = ownTemp.value
  if (img) body.image = img
  // 消息含 URL 时已前端抓取内容，不再走后端搜索，避免重复
  if (webSearch.value && !hasUrl) body.search = true
  if (genMode) body.gen_mode = true
  if (genMode && genConfig.value.workflow_path) body.workflow_path = genConfig.value.workflow_path
  // 高级面板预设分辨率传给 AI（优先采用；聊天里明确要求其他画幅时 AI 可改）
  if (genMode) { body.width = genConfig.value.width; body.height = genConfig.value.height }
  body.max_tokens = 50000
  body.stream = userStream.value
  body.top_p = ownTopP.value
  body.top_k = ownTopK.value
  body.frequency_penalty = ownFreqPen.value
  body.presence_penalty = ownPresPen.value
  body.min_p = ownMinP.value
  // 发送全部对话历史（排除最后一条空的 assistant 占位），用户自行总结后新开会话
  // 注意：历史只发文本，过滤掉图片（避免把气泡里显示的图片/生图结果图发给 LLM）
  // 同时过滤噪音消息（空文本、生图完成、错误占位），保持上下文干净
  if (messages.value.length > 1) {
    body.history = messages.value.slice(0, -1)
      .filter((m: any) => {
        if (!m || typeof m.text !== 'string') return false
        const t = m.text.trim()
        if (!t) return false
        if (m.genMeta && m.genMeta.status === 'done') return false   // 生图完成消息不发给 LLM
        if (t.startsWith('❌') || t.startsWith('🖼️')) return false   // 错误/生图完成噪音
        return true
      })
      .map((m: any) => ({ role: m.role, text: m.text, ...(m.role === 'assistant' && m.reasoning ? { reasoning: m.reasoning } : {}) }))
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
          else if (ev.gen_card) { aiMsg.genCard = ev.gen_card; aiMsg.genCardStatus = 'pending'; applyGenCardWorkflow(ev.gen_card); autoApproveCard(aiMsg) }
          else if (ev.sources) { aiMsg.sources = ev.sources }
          else if (ev.question) {
            // AI 反问：展示问题与选项，等用户回答
            pendingQuestion.value = { question: ev.question.question || '', options: ev.question.options || [] }
            if (!full) { full = ev.question.question || '请回答：'; aiMsg.text = full }
          }
          else if (ev.error) { full += '\n❌ ' + ev.error; aiMsg.text = full }
        }
      }
    } else {
      const d = await res.json()
      if (d.question) {
        pendingQuestion.value = { question: d.question.question || '', options: d.question.options || [] }
        full = d.question.question || '请回答：'
        aiMsg.text = full
      } else {
        if (!d.reply && !d.gen_card) throw new Error('服务器返回为空')
        full = d.reply || ''
        aiMsg.text = full
        if (d.reasoning) aiMsg.reasoning = d.reasoning
        if (d.sources) aiMsg.sources = d.sources
        if (d.gen_card) { aiMsg.genCard = d.gen_card; aiMsg.genCardStatus = 'pending'; applyGenCardWorkflow(d.gen_card); autoApproveCard(aiMsg) }
      }
    }
    if (!full && !reasoning) throw new Error('服务器返回为空')
  } catch (e: any) {
    // 移除空的 assistant 占位，改推错误消息
    messages.value = messages.value.filter(m => m !== aiMsg)
    throw e
  }
  if (mode.value === 'token') loadProfile()
}

// 兼容 JSON 数组格式的 AI 回复（如 ["正文", []]），自动提取第一个字符串元素
function normalizeText(v: any): string {
  if (typeof v === 'string') {
    const s = v.trim()
    if (s.startsWith('[') && s.endsWith(']')) {
      try {
        const arr = JSON.parse(s)
        if (Array.isArray(arr)) {
          const first = arr.find((x: any) => typeof x === 'string')
          if (first) return first
        }
      } catch {}
    }
    return v
  }
  if (Array.isArray(v)) {
    const first = v.find((x: any) => typeof x === 'string')
    if (first) return first
    return v.map((x: any) => (typeof x === 'string' ? x : JSON.stringify(x))).join('')
  }
  return v ? String(v) : ''
}

// 纯前端 token 估算（中文≈1.5字/token，英文≈3.5字/token）
function estimateTokens(text: unknown): number {
  if (typeof text !== 'string' || !text) return 0
  let tokens = 0
  for (const ch of text) {
    tokens += ch.charCodeAt(0) > 127 ? 1 / 1.5 : 1 / 3.5
  }
  return Math.round(tokens)
}

function chatTokens(): number {
  let total = 0
  for (const m of messages.value) {
    if (typeof m.text === 'string' && m.text) total += estimateTokens(m.text)
    if (m.image) total += 256 // 每张图估算 256 tokens
  }
  if (ownPrompt.value) total += estimateTokens(ownPrompt.value)
  return total
}

// ── 生图助手（聊天气泡内直接出图，复用 /ws/run 队列/冷却）──
interface GenConfig {
  direct: string
  negative: string
  workflow_path: string
  width: number
  height: number
  character: string       // 角色 tags（自定义填写或内置选择，逗号分隔多个，喂给生图工作流）
  style: string           // 画风 tags（自定义填写或内置选择，喂给生图工作流）
  characterName: string   // 角色显示名（顶栏展示用）
  styleName: string       // 画风显示名（顶栏展示用）
  characterCats: string[] // 角色分类（对应 characterName，用于"名 · 分类"展示）
  styleCat: string        // 画风分类
  userReq: string         // 用户描述需求（AI 优化用）
}
const showGenPanel = ref(false)
const genTargetIndex = ref(-1)   // 从哪条消息生图（-1 = 手动新建）
const genConfig = ref<GenConfig>({ direct: '', negative: '', workflow_path: '', width: 896, height: 1152, character: '', style: '', characterName: '', styleName: '', characterCats: [], styleCat: '', userReq: '' })
const genLoading = ref(false)
const genOptimizing = ref(false)
const genSizeCustom = ref(false)  // 尺寸是否为手动自定义（手动自定义限 512~2000，预设不受上限约束）
const genWs = ref<WebSocket | null>(null)
const genStatusText = ref('')
const genStatusPct = ref(0)
const genDoneImages = ref<{ url: string; filename: string; path: string }[]>([])
const genCooldown = ref(0)
const genRefImages = ref<{ name: string; preview: string }[]>([])
const genRefUploading = ref(false)
const genRefUploadErr = ref('')
// 文生图工作流列表 + 内置角色/画风（供选择）
const genWorkflows = ref<{ path: string; name: string; thumbnail?: string; category?: string }[]>([])
const genCharacters = ref<{ name: string; tags: string; category: string }[]>([])
const genStyles = ref<{ name: string; tags: string; category: string }[]>([])
const genShowCharPicker = ref(false)
const genShowStylePicker = ref(false)
const genCharSearch = ref('')
const genAllCharSearch = ref('')
const genAllCharResults = ref<{ name: string; franchise: string; tags: string; image?: string }[]>([])
const genAllCharSearching = ref(false)
let genAllCharTimer: any = null
// 搜索全部角色库（SQLite 44000+，含花火等内置库没有的）
function searchAllChars() {
  if (genAllCharTimer) clearTimeout(genAllCharTimer)
  const q = genAllCharSearch.value.trim()
  if (!q) { genAllCharResults.value = []; return }
  genAllCharTimer = setTimeout(async () => {
    genAllCharSearching.value = true
    try {
      const d = await api<any>('GET', '/api/features/ai-chat/search-characters?q=' + encodeURIComponent(q))
      genAllCharResults.value = (d.characters || []).slice(0, 20)
    } catch { genAllCharResults.value = [] }
    finally { genAllCharSearching.value = false }
  }, 350)
}
function pickAllGenCharacter(c: { name: string; tags?: string }) {
  pickGenCharacter(c)
  genAllCharResults.value = []
  genAllCharSearch.value = ''
}
const genStyleSearch = ref('')

async function loadGenWorkflows() {
  try {
    const d = await api<any>('GET', '/api/workflows')
    const dir = d.txt2img_dir || ''
    const wfs = d.workflows || d.all || []
    genWorkflows.value = wfs
      .filter((w: any) => !dir || (w.path && w.path.startsWith(dir)))
      .map((w: any) => ({ path: w.path, name: (w.name || w.path || '').replace(/\.json$/i, '').split('/').pop() || w.path, thumbnail: w.thumbnail || '', category: w.category || '未分类' }))
    if (genWorkflows.value.length && !genConfig.value.workflow_path) {
      genConfig.value.workflow_path = genWorkflows.value[0].path
    }
  } catch { genWorkflows.value = [] }
  // 用后端分辨率预设覆盖尺寸列表（保证提交的分辨率一定在预设里）
  try {
    const r = await api<any>('GET', '/api/resolutions')
    const presets = (r && r.presets) || []
    if (presets.length) {
      GEN_SIZES.value = presets.map((p: any) => ({ w: p.w, h: p.h, label: p.label || `${p.w}x${p.h}` }))
      // 当前尺寸不在预设 → 自动用第一个预设
      const cur = (genConfig.value.width + 'x' + genConfig.value.height)
      const inPreset = presets.some((p: any) => p.w === genConfig.value.width && p.h === genConfig.value.height)
      if (!inPreset) {
        genConfig.value.width = presets[0].w
        genConfig.value.height = presets[0].h
      }
      genSizeCustom.value = false
    }
  } catch {}
}
async function loadGenAssets() {
  try {
    const [c, s] = await Promise.all([
      api<any>('GET', '/api/characters').catch(() => ({ characters: [] })),
      api<any>('GET', '/api/styles').catch(() => ({ styles: [] })),
    ])
    genCharacters.value = c.characters || []
    genStyles.value = s.styles || []
  } catch {}
}
const genCharFiltered = computed(() => {
  const q = genCharSearch.value.trim().toLowerCase()
  if (!q) return genCharacters.value
  return genCharacters.value.filter(c => (c.name || '').toLowerCase().includes(q) || (c.category || '').toLowerCase().includes(q) || (c.tags || '').toLowerCase().includes(q))
})
const genStyleFiltered = computed(() => {
  const q = genStyleSearch.value.trim().toLowerCase()
  if (!q) return genStyles.value
  return genStyles.value.filter(s => (s.name || '').toLowerCase().includes(q) || (s.category || '').toLowerCase().includes(q))
})
// 按分类分组：返回 [{category, items:[...]}]
const genCharGroups = computed(() => {
  const groups = new Map<string, any[]>()
  for (const c of genCharFiltered.value) {
    const cat = (c.category || '未分类').trim() || '未分类'
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push(c)
  }
  return Array.from(groups.entries()).map(([category, items]) => ({ category, items }))
})
const genStyleGroups = computed(() => {
  const groups = new Map<string, any[]>()
  for (const s of genStyleFiltered.value) {
    const cat = (s.category || '未分类').trim() || '未分类'
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push(s)
  }
  return Array.from(groups.entries()).map(([category, items]) => ({ category, items }))
})
// 工作流搜索/分组
const genWfSearch = ref('')
const genWfFiltered = computed(() => {
  const q = genWfSearch.value.trim().toLowerCase()
  if (!q) return genWorkflows.value
  return genWorkflows.value.filter(w => (w.name || '').toLowerCase().includes(q) || (w.category || '').toLowerCase().includes(q))
})
const genWfGroups = computed(() => {
  const groups = new Map<string, any[]>()
  for (const w of genWfFiltered.value) {
    const cat = (w.category || '未分类').trim() || '未分类'
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push(w)
  }
  return Array.from(groups.entries()).map(([category, items]) => ({ category, items }))
})
function pickGenCharacter(c: { name: string; tags?: string; category?: string }) {
  const t = (c.tags || c.name || '').trim()
  const existing = genConfig.value.character ? genConfig.value.character + ', ' : ''
  genConfig.value.character = existing + t
  const nExisting = genConfig.value.characterName ? genConfig.value.characterName + ', ' : ''
  genConfig.value.characterName = nExisting + c.name
  genConfig.value.characterCats = [...genConfig.value.characterCats, (c.category || '').trim()]
  genShowCharPicker.value = false
}
function pickGenStyle(s: { name: string; tags?: string; category?: string }) {
  genConfig.value.style = (s.tags || s.name || '').trim()
  genConfig.value.styleName = s.name
  genConfig.value.styleCat = (s.category || '').trim()
  genShowStylePicker.value = false
}
// 已选角色/画风 chips（仿 2x.nz：输入框上方展示，可单独取消，多角色组合）
const genSelectedChips = computed(() => {
  const chips: { type: string; name: string; rawIdx: number }[] = []
  const names = genConfig.value.characterName ? genConfig.value.characterName.split(',').map(s => s.trim()).filter(Boolean) : []
  const cats = genConfig.value.characterCats || []
  names.forEach((n, i) => chips.push({ type: '角色', name: n + (cats[i] ? ' · ' + cats[i] : ''), rawIdx: i }))
  if (genConfig.value.styleName) chips.push({ type: '画风', name: genConfig.value.styleName + (genConfig.value.styleCat ? ' · ' + genConfig.value.styleCat : ''), rawIdx: -1 })
  return chips
})
function removeGenChip(chip: { type: string; rawIdx: number }) {
  if (chip.type === '画风') { genConfig.value.style = ''; genConfig.value.styleName = ''; genConfig.value.styleCat = ''; return }
  const names = genConfig.value.characterName.split(',').map(s => s.trim())
  const tags = genConfig.value.character.split(',').map(s => s.trim())
  const cats = genConfig.value.characterCats || []
  if (chip.rawIdx >= 0 && chip.rawIdx < names.length) { names.splice(chip.rawIdx, 1); tags.splice(chip.rawIdx, 1); cats.splice(chip.rawIdx, 1) }
  genConfig.value.characterName = names.filter(Boolean).join(', ')
  genConfig.value.character = tags.filter(Boolean).join(', ')
  genConfig.value.characterCats = cats
}

async function genUploadRef(file: File) {
  if (genRefImages.value.length >= 3) { alert('最多 3 张参考图'); return }
  genRefUploading.value = true
  genRefUploadErr.value = ''
  try {
    const compressed = await compressImage(file)
    const base64Body = compressed.split(',')[1] || compressed
    const binStr = atob(base64Body)
    const bytes = new Uint8Array(binStr.length)
    for (let bi = 0; bi < binStr.length; bi++) bytes[bi] = binStr.charCodeAt(bi)
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    const fd = new FormData()
    fd.append('image1', blob, file.name || 'img.jpg')
    const d = await fetch('/api/img2img/upload', { method: 'POST', body: fd }).then(r => r.json())
    if (d && d.image1_name) {
      genRefImages.value.push({ name: d.image1_name, preview: compressed })
    } else {
      genRefUploadErr.value = d.detail || d.error || '上传失败'
    }
  } catch (e: any) {
    genRefUploadErr.value = '上传失败: ' + (e.message || '未知')
  } finally { genRefUploading.value = false }
}
function genRemoveRef(i: number) { genRefImages.value.splice(i, 1) }
function genOnRefChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) genUploadRef(f)
  ;(e.target as HTMLInputElement).value = ''
}

// ── 图片反推（ComfyUI 反推工作流，不占生图冷却/不写日志）──
const reversing = ref(false)
const reverseErr = ref('')
const reverseWs = ref<WebSocket | null>(null)

async function startReverse() {
  if (reversing.value) return
  if (!imageBase64.value) { alert('请先上传图片'); return }
  reverseErr.value = ''
  reversing.value = true
  try {
    // 1. 上传图片到 ComfyUI input 目录（前端已压缩 + 后端校验）
    const compressed = imageBase64.value
    const base64Body = compressed.split(',')[1] || compressed
    const binStr = atob(base64Body)
    const bytes = new Uint8Array(binStr.length)
    for (let bi = 0; bi < binStr.length; bi++) bytes[bi] = binStr.charCodeAt(bi)
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    const fd = new FormData()
    fd.append('image1', blob, 'reverse.jpg')
    const up = await fetch('/api/img2img/upload', { method: 'POST', body: fd }).then(r => r.json())
    if (!up || !up.image1_name) {
      reverseErr.value = up.detail || up.error || '图片上传失败'
      reversing.value = false
      return
    }
    // 2. 建 WebSocket 提交反推任务（复用 /ws/run 队列，task_type=reverse 跳过冷却）
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/ws/run`)
    reverseWs.value = ws
    const reverseWorkflow = localStorage.getItem('aiChatReverseWorkflow') || '反推/绘画反推.json'
    ws.onopen = () => {
      const payload: any = {
        task_type: 'reverse',
        workflow_path: reverseWorkflow,
        mode: 'img2img',
        image1_name: up.image1_name,
        image2_name: '', image3_name: '',
        direct_prompt: '', nl_prompt: '', negative_prompt: '', rewrite: false,
        prompt_mode: 'tags', llm_template_id: null,
        width: null, height: null, style_tags: '', character_tags: '',
        img2img_use_preset: false, seed_mode: 'default',
      }
      ws.send(JSON.stringify(payload))
    }
    ws.onmessage = (e) => {
      let m: any = {}
      try { m = JSON.parse(e.data) } catch { return }
      if (m.type === 'reverse_result' && m.result) {
        const r = m.result
        // 展示反推结果卡片（sd标签 + 中文描述）
        const parts: string[] = []
        if (r.sd_tags) parts.push(`**🎯 SD 标签（反推）**\n${r.sd_tags}`)
        if (r.chinese_prompt) parts.push(`**📝 中文描述（反推）**\n${r.chinese_prompt}`)
        if (parts.length) {
          messages.value.push({ role: 'assistant', text: parts.join('\n\n'), reverseResult: r })
          scrollBottom()
        }
      } else if (m.type === 'done') {
        reversing.value = false
        try { ws.close() } catch {}
        reverseWs.value = null
        // 反推完成后自动清除输入框图片，避免后续对话误把图发给 LLM
        removeImage()
      } else if (m.type === 'error') {
        reverseErr.value = m.message || '反推失败'
        reversing.value = false
        try { ws.close() } catch {}
        reverseWs.value = null
      }
    }
    ws.onclose = () => { reverseWs.value = null; reversing.value = false }
    ws.onerror = () => { reverseErr.value = '连接失败'; reversing.value = false }
  } catch (e: any) {
    reverseErr.value = '反推出错: ' + (e.message || '未知')
    reversing.value = false
  }
}

// 默认尺寸列表（打开面板时用后端 /api/resolutions 预设覆盖）
const GEN_SIZES = ref([
  { w: 512, h: 768, label: '竖屏 2:3' },
  { w: 768, h: 512, label: '横屏 3:2' },
  { w: 768, h: 768, label: '方图 1:1' },
  { w: 896, h: 1152, label: '竖屏 3:4' },
  { w: 1152, h: 896, label: '横屏 4:3' },
  { w: 832, h: 1216, label: '竖屏 9:16' },
  { w: 1216, h: 832, label: '横屏 16:9' },
  { w: 1024, h: 1024, label: '方图 1:1(高清)' },
])

function initGenDefaults() {
  // 复用生图页存的默认工作流/尺寸（若存在），否则用内置默认；尺寸限制 512~2000
  try {
    const wf = localStorage.getItem('currentWorkflow') || ''
    if (wf) genConfig.value.workflow_path = wf
  } catch {}
  try {
    const w = parseInt(localStorage.getItem('formState_w') || '896')
    const h = parseInt(localStorage.getItem('formState_h') || '1152')
    if (w >= 512 && w <= 2000 && h >= 512 && h <= 2000) { genConfig.value.width = w; genConfig.value.height = h }
  } catch {}
}
initGenDefaults()

function openGenPanel(idx: number, directText: string) {
  genTargetIndex.value = idx
  genConfig.value.direct = directText || genConfig.value.direct
  if (!genConfig.value.negative) genConfig.value.negative = 'low quality, worst quality, bad anatomy, bad hands, extra limbs, extra fingers, blurry, watermark, text'
  genStatusText.value = ''
  genStatusPct.value = 0
  genDoneImages.value = []
  showGenPanel.value = true
  loadGenWorkflows()
  loadGenAssets()
}
function closeGenPanel() {
  showGenPanel.value = false
  if (genWs.value) { try { genWs.value.close() } catch {} genWs.value = null }
  genLoading.value = false
}
function applyGenSize(s: { w: number; h: number }) {
  genConfig.value.width = s.w
  genConfig.value.height = s.h
  genSizeCustom.value = false
}

// 卡片预设分辨率：匹配当前宽高对应的预设 label，未匹配返回空（=自定义）
function genCardSizeLabel(card: any): string {
  if (!card) return ''
  const hit = GEN_SIZES.value.find(s => s.w === card.width && s.h === card.height)
  return hit ? hit.label : ''
}
// AI 生成卡片时同步顶部：工作流 + 角色 + 画风（顶部显示并供后续对话参考）
function applyGenCardWorkflow(card: any) {
  if (!card) return
  if (card.workflow_path && card.workflow_path !== genConfig.value.workflow_path) {
    genConfig.value.workflow_path = card.workflow_path
  }
  if (card.character) {
    genConfig.value.character = card.character
    genConfig.value.characterName = card.character
    genConfig.value.characterCats = []
  }
  if (card.style) {
    genConfig.value.style = card.style
    genConfig.value.styleName = card.style
    genConfig.value.styleCat = ''
  }
}
// 自动批准：收到卡片后自动确认生成（跳过手动点确认）
function autoApproveCard(msg: any) {
  if (!autoApprove.value) return
  const idx = messages.value.indexOf(msg)
  if (idx < 0) return
  setTimeout(() => {
    const m = messages.value[idx]
    if (m && m.genCard && (m.genCardStatus === 'pending' || m.genCardStatus === 'queued')) {
      confirmGenCard(idx)
    }
  }, 400)
}
function applyGenCardSize(idx: number, label: string) {
  const msg = messages.value[idx]
  if (!msg || !msg.genCard) return
  const hit = GEN_SIZES.value.find(s => s.label === label)
  if (hit) { msg.genCard.width = hit.w; msg.genCard.height = hit.h }
}

async function submitGen(cardData?: GenCardData | null) {
  const cardMode = !!cardData
  // 卡片提交模式：直接用卡片数据（不弹面板）
  if (cardData) {
    genConfig.value.direct = cardData.prompt || ''
    genConfig.value.negative = cardData.negative_prompt || ''
    genConfig.value.width = cardData.width || 896
    genConfig.value.height = cardData.height || 1152
    genConfig.value.character = cardData.character || ''
    genConfig.value.style = cardData.style || ''
    genConfig.value.characterName = cardData.character || ''
    genConfig.value.styleName = cardData.style || ''
  }
  const direct = genConfig.value.direct.trim()
  if (!direct) { alert('请先填写提示词'); return }
  if (genLoading.value) return
  // 手动自定义尺寸才校验 512~2000；预设选中（工作流默认/预设按钮）不受上限约束
  const w = Math.round(genConfig.value.width), h = Math.round(genConfig.value.height)
  if (genSizeCustom.value && (w < 512 || w > 2000 || h < 512 || h > 2000)) {
    alert('自定义尺寸需在 512×512 ~ 2000×2000 之间')
    return
  }
  genConfig.value.width = w; genConfig.value.height = h
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${location.host}/ws/run`)
  genWs.value = ws
  genLoading.value = true
  genStatusText.value = '连接中...'
  genStatusPct.value = 0
  genDoneImages.value = []

  ws.onopen = () => {
    const payload: any = {
      workflow_path: genConfig.value.workflow_path || undefined,
      mode: 'txt2img',
      direct_prompt: direct,
      nl_prompt: '',
      negative_prompt: genConfig.value.negative.trim(),
      rewrite: false,
      prompt_mode: 'tags',
      llm_template_id: null,
      width: genConfig.value.width,
      height: genConfig.value.height,
      style_tags: cardMode ? '' : genConfig.value.style.trim(),
      character_tags: cardMode ? '' : genConfig.value.character.trim(),
      img2img_use_preset: false,
      image1_name: '', image2_name: '', image3_name: '',
      seed_mode: 'default',
    }
    ws.send(JSON.stringify(payload))
  }
  ws.onmessage = (e) => {
    let m: any = {}
    try { m = JSON.parse(e.data) } catch { return }
    // 卡片模式时同步生成进度文本到卡片
    const syncCard = (txt: string) => {
      if (cardMode && genTargetIndex.value >= 0) {
        const c = messages.value[genTargetIndex.value]
        if (c && c.genCard) c.genCardStatusText = txt
      }
    }
    if (m.type === 'queued' || m.type === 'queue_start') {
      const txt = m.message || (m.type === 'queued' ? '排队中...' : '开始执行...')
      genStatusText.value = txt
      genStatusPct.value = 0
      syncCard(txt)
    } else if (m.type === 'log') {
      genStatusText.value = m.message
      syncCard(m.message)
    } else if (m.type === 'progress') {
      if (m.max && m.max > 1) {
        genStatusPct.value = Math.floor((m.value || 0) * 100 / m.max)
        const txt = `${m.node || ''} ${m.value || 0}/${m.max} (${genStatusPct.value}%)`
        genStatusText.value = txt
        syncCard(txt)
      } else {
        const txt = `执行: ${m.node || ''}`
        genStatusText.value = txt
        syncCard(txt)
      }
    } else if (m.type === 'image') {
      // 只收集图片，由 done 事件统一插入一次（避免重复）
      genDoneImages.value.push({ url: m.url, filename: m.filename, path: m.path })
    } else if (m.type === 'done') {
      genStatusText.value = `✅ 完成，共 ${m.count || 0} 张`
      genCooldown.value = typeof m.cooldown_remaining === 'number' ? m.cooldown_remaining : 0
      genLoading.value = false
      // 卡片模式：更新卡片状态为完成（图片显示在卡片内），不再额外插入
      if (cardMode && genTargetIndex.value >= 0) {
        const cardMsg = messages.value[genTargetIndex.value]
        if (cardMsg && cardMsg.genCard) {
          cardMsg.genCardStatus = 'done'
          cardMsg.genCardStatusText = `✅ 完成，共 ${m.count || 0} 张`
          if (genDoneImages.value.length) {
            cardMsg.genCard.result = genDoneImages.value.map((im: any) => im.url)
          }
        }
      } else if (genTargetIndex.value >= 0) {
        // 非卡片模式：插入完成卡片（含图片）
        const imgs = genDoneImages.value
        if (imgs.length) {
          messages.value.push({
            role: 'assistant',
            text: '🖼️ 生图完成' + (genCooldown.value ? `（冷却 ${genCooldown.value}s）` : ''),
            image: imgs[imgs.length - 1].url,
            genMeta: { status: 'done', url: imgs[imgs.length - 1].url, filename: imgs[imgs.length - 1].filename, count: imgs.length },
          })
          scrollBottom()
        }
      }
      try { ws.close() } catch {}
      genWs.value = null
      if (!cardMode) showGenPanel.value = false
    } else if (m.type === 'error') {
      genStatusText.value = '❌ ' + (m.message || '生图失败')
      if (typeof m.cooldown_remaining === 'number' && m.cooldown_remaining > 0) {
        genCooldown.value = m.cooldown_remaining
        genStatusText.value = `⏳ 生图间隔限制：请 ${m.cooldown_remaining}s 后再试`
      }
      genLoading.value = false
      if (cardMode && genTargetIndex.value >= 0) {
        const cardMsg = messages.value[genTargetIndex.value]
        if (cardMsg && cardMsg.genCard) {
          cardMsg.genCardStatus = 'error'
          cardMsg.genCardStatusText = '❌ ' + (m.message || '生图失败')
        }
      }
    }
  }
  ws.onclose = () => { genWs.value = null; if (genLoading.value) { genLoading.value = false } }
  ws.onerror = () => { genStatusText.value = '❌ 连接失败，请重试'; genLoading.value = false }
}

async function optimizeGen() {
  if (genOptimizing.value) return
  const tk = token.value
  if (!tk) { alert('请在设置中填写额度 Token'); return }
  const base = genConfig.value.direct.trim()
  const req = genConfig.value.userReq.trim()
  if (!base && !req) return
  genOptimizing.value = true
  try {
    // 走后端 /api/features/ai-chat/optimize：按当前工作流对应模型规则智能扩写，并传递角色/画风/分辨率
    const res = await fetch('/api/features/ai-chat/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token: tk,
        workflow_path: genConfig.value.workflow_path || '',
        prompt: base,
        negative: genConfig.value.negative.trim(),
        character: genConfig.value.character.trim(),
        style: genConfig.value.style.trim(),
        userReq: req,
        width: genConfig.value.width,
        height: genConfig.value.height,
        thinking: aiOptThinking.value,
      }),
    })
    const d = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(d.detail || ('HTTP ' + res.status))
    const pos = (d.positive || '').trim()
    const neg = (d.negative || '').trim()
    if (pos) genConfig.value.direct = pos
    if (neg) genConfig.value.negative = neg
    else if (!genConfig.value.negative.trim()) genConfig.value.negative = 'low quality, worst quality, bad anatomy, bad hands, extra limbs, extra fingers, blurry, watermark, text'
    genStatusText.value = '🤖 AI 优化完成，请核对提示词'
  } catch (e: any) {
    genStatusText.value = '❌ AI 优化失败: ' + (e.message || '未知')
  } finally { genOptimizing.value = false }
}

// 卡片内 AI 优化提示词（走后端 optimize：按工作流模型规则重写，传递卡片角色/画风/分辨率）
const genCardOptimizing = ref<number>(-1)
// AI 优化是否启用思考模式（默认关=快；开=质量更高，用户可在设置里切换）
const aiOptThinking = ref(localStorage.getItem('aiOptThinking') === '1')
watch(aiOptThinking, v => localStorage.setItem('aiOptThinking', v ? '1' : '0'))
async function cardOptimize(idx: number) {
  const msg = messages.value[idx]
  if (!msg || !msg.genCard) return
  if (genCardOptimizing.value >= 0) return
  const tk = token.value
  if (!tk) { alert('请在设置中填写额度 Token'); return }
  const base = (msg.genCard.prompt || '').trim()
  if (!base) return
  genCardOptimizing.value = idx
  msg.genCardStatusText = '🤖 AI 优化中...'
  try {
    const res = await fetch('/api/features/ai-chat/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token: tk,
        workflow_path: genConfig.value.workflow_path || ((msg.genCard as any).workflow_path || ''),
        prompt: base,
        negative: (msg.genCard.negative_prompt || '').trim(),
        character: (msg.genCard.character || '').trim(),
        style: (msg.genCard.style || '').trim(),
        userReq: (msg.genCard.userReq || '').trim(),
        width: msg.genCard.width || genConfig.value.width,
        height: msg.genCard.height || genConfig.value.height,
        thinking: aiOptThinking.value,
      }),
    })
    const d = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(d.detail || ('HTTP ' + res.status))
    const pos = (d.positive || '').trim()
    const neg = (d.negative || '').trim()
    if (pos) msg.genCard.prompt = pos
    if (neg) msg.genCard.negative_prompt = neg
    msg.genCardStatusText = ''
  } catch (e: any) {
    msg.genCardStatusText = '❌ 优化失败'
  } finally { genCardOptimizing.value = -1 }
}

// 确认生成卡片（仿 2x.nz：卡片内直接提交，不弹面板）
function confirmGenCard(idx: number) {
  const msg = messages.value[idx]
  if (!msg || !msg.genCard) return
  // 尺寸校验（自定义也限 512-2000）
  const w = Math.round(msg.genCard.width || 896), h = Math.round(msg.genCard.height || 1152)
  if (w < 512 || w > 2000 || h < 512 || h > 2000) { alert('尺寸需在 512×512 ~ 2000×2000 之间'); return }
  msg.genCard.width = w; msg.genCard.height = h
  msg.genCardStatus = 'queued'
  genTargetIndex.value = idx
  submitGen(msg.genCard)
}

// 刷新图片（仿 2x.nz：用同卡重新生成，换随机种子）
function refreshGenImage(idx: number) {
  const msg = messages.value[idx]
  if (!msg || !msg.genCard) return
  msg.genCardStatus = 'queued'
  genTargetIndex.value = idx
  submitGen(msg.genCard)
}

// 反推结果 → 生成智能生图方案卡片（待确认，卡片上可设分辨率/描述需求/AI 优化后点生成）
function genFromReverse(text: string) {
  if (genLoading.value) return
  if (!text || !text.trim()) { alert('反推提示词为空'); return }
  msgEditMode.value = false
  const card: GenCardData = { prompt: text.trim(), negative_prompt: '', width: genConfig.value.width || 896, height: genConfig.value.height || 1152, character: '', style: '', userReq: '' }
  const idx = messages.value.length
  messages.value.push({ role: 'assistant', text: '', genCard: card, genCardStatus: 'pending' })
  genTargetIndex.value = idx
  scrollBottom()
}

// 复制文本到剪贴板
async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text || '')
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text || ''
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  alert('已复制')
}

// 强制 AI 生成「审核生图参数」卡片（基于当前对话内容，token 模式走生图工具）
async function forceGenCard() {
  if (sending.value) return
  const tk = token.value
  if (!tk) { alert('请在设置中填写额度 Token'); return }
  if (!currentSessionId.value) newSession()
  const msgText = '请根据我们刚才对话讨论的需求，立即生成一张「审核生图参数」卡片：调用生图工具提交正/负提示词、尺寸、角色、画风。'
  const userMsg: any = { role: 'user', text: msgText }
  messages.value.push(userMsg)
  sending.value = true
  scrollBottom()
  try {
    if (mode.value === 'own') await sendOwn(msgText, '')
    else await sendToken(msgText, '', false, true)
  } catch (e: any) {
    messages.value.push({ role: 'assistant', text: '❌ 错误: ' + (e.message || '未知') })
  } finally { sending.value = false; autoSaveSession(); scrollBottom() }
}

// 继续讨论（仿 2x.nz：进入微调模式，输入框变"进一步调整参数"）
const discussTargetIndex = ref(-1)
function startContinueDiscuss(idx: number) {
  discussTargetIndex.value = idx
  discussMode.value = true
  showGenPanel.value = false
  inputText.value = ''
  nextTick(() => {
    const el = document.querySelector('.chat-input textarea, textarea[placeholder*="输入消息"]')
    if (el) (el as HTMLTextAreaElement).focus()
  })
  scrollBottom()
}
const discussMode = ref(false)

// 发送文本消息（复用 sendToken），供微调模式调用；forceCard 时强制走生图工具生成卡片
async function sendText(text: string, forceCard: boolean = false) {
  const userMsg: any = { role: 'user', text }
  if (genSelectedChips.value.length) userMsg.selectedChips = genSelectedChips.value.slice()
  messages.value.push(userMsg)
  sending.value = true
  scrollBottom()
  try {
    if (mode.value === 'own') await sendOwn(text, '')
    else await sendToken(text, '', false, forceCard ? true : genMode.value)
  } catch (e: any) {
    messages.value.push({ role: 'assistant', text: '❌ 错误: ' + (e.message || '未知') })
  } finally { sending.value = false; autoSaveSession(); scrollBottom() }
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
  loadGenWorkflows()
  loadGenAssets()
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

    <!-- 生图配置条（仿 2x.nz：工作流/角色/画风 可选，不选直接提需求 AI 自主扩写） -->
    <div class="flex items-center gap-1.5 px-3 py-1.5 border-b border-pink-100 dark:border-gray-700 shrink-0 bg-white/60 dark:bg-gray-800/60 overflow-x-auto">
      <span class="shrink-0 text-[10px] font-semibold text-gray-500 dark:text-gray-400">🎨 生图</span>
      <button @click="openWorkflowPicker" class="shrink-0 max-w-[130px] truncate text-[11px] px-2 py-1 rounded-lg cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 dark:text-gray-300 hover:bg-pink-100 dark:hover:bg-pink-900/40" :title="genConfig.workflow_path">
        {{ genWorkflowName() || '选择工作流' }}
      </button>
      <button @click="genShowCharPicker=!genShowCharPicker" class="shrink-0 max-w-[110px] truncate text-[11px] px-2 py-1 rounded-lg cursor-pointer border-0" :class="genConfig.character ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300' : 'bg-gray-100 dark:bg-gray-700 dark:text-gray-300 hover:bg-blue-100'" :title="genConfig.character">
        {{ genConfig.characterName || genConfig.character || '🎯 角色' }}
      </button>
      <button @click="genShowStylePicker=!genShowStylePicker" class="shrink-0 max-w-[110px] truncate text-[11px] px-2 py-1 rounded-lg cursor-pointer border-0" :class="genConfig.style ? 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300' : 'bg-gray-100 dark:bg-gray-700 dark:text-gray-300 hover:bg-emerald-100'" :title="genConfig.style">
        {{ genConfig.styleName || genConfig.style || '🎨 画风' }}
      </button>
      <button @click="openGenPanel(-1, '')" class="shrink-0 text-[11px] px-2 py-1 rounded-lg cursor-pointer border-0 bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300 hover:bg-pink-200" title="高级手动配置">⚙️ 高级</button>
      <!-- 角色/画风选择弹层 -->
      <Teleport to="body">
        <div v-if="genShowCharPicker || genShowStylePicker" class="fixed inset-0 z-[80] bg-black/30 backdrop-blur-sm flex items-start justify-center pt-16 p-4" @click="genShowCharPicker=false; genShowStylePicker=false">
          <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-md w-full p-4 max-h-[70vh] flex flex-col" @click.stop>
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-bold text-gray-700 dark:text-gray-200">{{ genShowCharPicker ? '🎯 选择角色' : '🎨 选择画风' }}</h3>
              <div class="flex items-center gap-2">
                <input v-if="genShowCharPicker" v-model="genCharSearch" type="text" placeholder="搜索角色..." class="border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none w-32 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
                <input v-else v-model="genStyleSearch" type="text" placeholder="搜索画风..." class="border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none w-32 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
                <button @click="genShowCharPicker=false; genShowStylePicker=false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">&times;</button>
              </div>
            </div>
            <div class="flex-1 overflow-y-auto min-h-0 space-y-2">
              <template v-if="genShowCharPicker">
                <div class="relative mb-1.5">
                  <input v-model="genAllCharSearch" @input="searchAllChars" type="text" placeholder="🔍 搜索全部角色库（40000+，含花火等）..." class="w-full border border-blue-200 dark:border-gray-600 rounded-lg px-2 py-1.5 pr-7 text-[11px] outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
                  <button v-if="genAllCharSearch" @click="genAllCharSearch=''; searchAllChars()" class="absolute right-1.5 top-1/2 -translate-y-1/2 text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 cursor-pointer border-0 bg-transparent px-1" title="清空搜索">✕</button>
                </div>
                <div v-if="genAllCharSearching" class="flex items-center gap-1.5 text-[10px] text-blue-500 px-1 mb-1.5">
                  <span class="inline-block w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></span>
                  正在搜索角色库...
                </div>
                <div v-if="genAllCharResults.length" class="space-y-0.5 mb-2">
                  <div class="text-[10px] font-semibold text-blue-500 px-1">搜索结果（共 {{ genAllCharResults.length }} 个，点击选用）</div>
                  <div v-for="c in genAllCharResults" :key="c.name + c.tags" @click="pickAllGenCharacter(c)" class="flex items-center gap-2 px-2 py-1 rounded text-[11px] cursor-pointer border-0 hover:bg-blue-50 dark:hover:bg-blue-900/40">
                    <img v-if="c.image" :src="c.image" class="w-9 h-9 object-cover rounded-md shrink-0 border border-gray-200 dark:border-gray-600" loading="lazy" />
                    <span v-else class="w-9 h-9 rounded-md bg-gray-100 dark:bg-gray-700 flex items-center justify-center shrink-0 text-sm">🎭</span>
                    <span class="truncate flex-1">{{ c.name }}<span v-if="c.franchise" class="text-gray-400"> · {{ c.franchise }}</span></span>
                    <button @click.stop="copyText(c.tags || c.name)" class="shrink-0 text-[9px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300 hover:bg-gray-200 cursor-pointer border-0" title="复制 tag">📋</button>
                  </div>
                </div>
                <div v-else-if="!genAllCharSearching && genAllCharSearch" class="text-[10px] text-gray-400 px-1 mb-2">未找到匹配角色，可用自然语言绘制原创角色</div>
                <div v-for="g in genCharGroups" :key="g.category" class="space-y-0.5">
                  <div class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 px-1">{{ g.category }} ({{ g.items.length }})</div>
                  <div class="flex flex-wrap gap-1.5">
                    <div v-for="c in g.items" :key="c.name" class="flex flex-col items-center gap-1 w-[86px] p-1.5 rounded-xl cursor-pointer border-0 hover:bg-blue-50 dark:hover:bg-blue-900/40" :class="genConfig.characterName && genConfig.characterName.includes(c.name) ? 'bg-blue-100 dark:bg-blue-900 ring-1 ring-blue-300' : ''" :title="c.name" @click="pickGenCharacter(c)">
                      <div class="relative w-[72px] h-[72px]">
                        <img v-if="c.image" :src="'/api/character_thumbnail?name=' + encodeURIComponent(c.image)" class="w-[72px] h-[72px] object-cover rounded-lg" loading="lazy" />
                        <div v-else class="w-[72px] h-[72px] rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-lg">🎭</div>
                        <button @click.stop="copyText(c.tags || c.name)" class="absolute top-0.5 right-0.5 w-5 h-5 text-[9px] leading-none rounded-md bg-black/50 text-white hover:bg-black/70 cursor-pointer border-0" title="复制 tag">📋</button>
                      </div>
                      <span class="text-[10px] text-gray-600 dark:text-gray-300 line-clamp-2 text-center break-all">{{ c.name }}</span>
                      <span class="text-[9px] text-blue-400/70 cursor-pointer" @click.stop="copyText(c.tags || c.name)">复制 tag</span>
                    </div>
                  </div>
                </div>
                <div v-if="!genCharGroups.length" class="text-[11px] text-gray-400 text-center py-3">无匹配角色，可直接在输入框描述需求让 AI 生成原创角色</div>
              </template>
              <template v-else>
                <div v-for="g in genStyleGroups" :key="g.category" class="space-y-0.5">
                  <div class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 px-1">{{ g.category }} ({{ g.items.length }})</div>
                  <div class="flex flex-wrap gap-1.5">
                    <div v-for="s in g.items" :key="s.name" class="flex flex-col items-center gap-1 w-[86px] p-1.5 rounded-xl cursor-pointer border-0 hover:bg-emerald-50 dark:hover:bg-emerald-900/40" :class="genConfig.styleName === s.name || genConfig.style === s.tags ? 'bg-emerald-100 dark:bg-emerald-900 ring-1 ring-emerald-300' : ''" :title="s.name" @click="pickGenStyle(s)">
                      <div class="relative w-[72px] h-[72px]">
                        <img v-if="s.image" :src="'/api/style_thumbnail?name=' + encodeURIComponent(s.image)" class="w-[72px] h-[72px] object-cover rounded-lg" loading="lazy" />
                        <div v-else class="w-[72px] h-[72px] rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-lg">🖌️</div>
                        <button @click.stop="copyText(s.tags || s.name)" class="absolute top-0.5 right-0.5 w-5 h-5 text-[9px] leading-none rounded-md bg-black/50 text-white hover:bg-black/70 cursor-pointer border-0" title="复制 tag">📋</button>
                      </div>
                      <span class="text-[10px] text-gray-600 dark:text-gray-300 line-clamp-2 text-center break-all">{{ s.name }}</span>
                      <span class="text-[9px] text-emerald-400/70 cursor-pointer" @click.stop="copyText(s.tags || s.name)">复制 tag</span>
                    </div>
                  </div>
                </div>
                <div v-if="!genStyleGroups.length" class="text-[11px] text-gray-400 text-center py-3">无匹配画风，可直接在输入框描述画风</div>
              </template>
            </div>
            <div class="flex gap-2 mt-3 pt-2 border-t border-gray-100 dark:border-gray-600">
              <input v-if="genShowCharPicker" v-model="genCustomChar" type="text" placeholder="自定义角色名..." class="flex-1 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" @keydown.enter="applyCustomChar" />
              <input v-else v-model="genCustomStyle" type="text" placeholder="自定义画风..." class="flex-1 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" @keydown.enter="applyCustomStyle" />
              <button v-if="genShowCharPicker" @click="applyCustomChar" class="shrink-0 px-3 py-1 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-blue-500 text-white hover:bg-blue-600">自定义</button>
              <button v-else @click="applyCustomStyle" class="shrink-0 px-3 py-1 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-emerald-500 text-white hover:bg-emerald-600">自定义</button>
            </div>
          </div>
        </div>
      </Teleport>
      <!-- 工作流选择弹层 -->
      <Teleport to="body">
        <div v-if="showWfPicker" class="fixed inset-0 z-[80] bg-black/30 backdrop-blur-sm flex items-start justify-center pt-16 p-4" @click="showWfPicker=false">
          <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-md w-full p-4 max-h-[70vh] flex flex-col" @click.stop>
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-bold text-gray-700 dark:text-gray-200">📋 选择工作流（文生图）</h3>
              <input v-model="genWfSearch" type="text" placeholder="搜索工作流..." class="border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none w-32 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
              <button @click="showWfPicker=false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">&times;</button>
            </div>
            <div class="flex-1 overflow-y-auto min-h-0 space-y-2">
              <template v-if="genWfGroups.length">
                <div v-for="g in genWfGroups" :key="g.category" class="space-y-1">
                  <div class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 px-1">{{ g.category }} ({{ g.items.length }})</div>
                  <div class="flex flex-wrap gap-1.5">
                    <div v-for="w in g.items" :key="w.path" class="flex flex-col items-center gap-1 w-[86px] p-1.5 rounded-xl cursor-pointer border-0 hover:bg-pink-50 dark:hover:bg-pink-900/40" :class="genConfig.workflow_path===w.path ? 'bg-pink-100 dark:bg-pink-900 ring-1 ring-pink-300' : ''" :title="w.name" @click="genConfig.workflow_path=w.path; showWfPicker=false">
                      <img v-if="w.thumbnail" :src="'/api/thumbnail?path=' + encodeURIComponent(w.path)" class="w-[72px] h-[72px] object-cover rounded-lg" loading="lazy" />
                      <div v-else class="w-[72px] h-[72px] rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-lg">🎨</div>
                      <span class="text-[10px] text-gray-600 dark:text-gray-300 line-clamp-2 text-center break-all">{{ w.name }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <div v-else class="text-[11px] text-gray-400 text-center py-3">无匹配工作流</div>
            </div>
          </div>
        </div>
      </Teleport>
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
      <div v-if="!messages.length" class="text-center text-xs text-gray-500 dark:text-gray-400 py-8">
        <p class="text-lg mb-1">🤖</p>
        <p>发送消息开始对话</p>
        <p class="mt-1">支持上传图片进行反推/改写</p>
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="flex flex-col" :class="msg.role==='user'?'items-end':'items-start'">
        <div class="flex items-center gap-1.5 w-full" :class="msg.role==='user'?'justify-end':'justify-start'">
          <input v-if="msgEditMode" type="checkbox" :checked="selectedMsgs.has(i)" @change="toggleSelectMsg(i)" @click.stop class="w-4 h-4 accent-pink-500 cursor-pointer shrink-0" :class="msg.role==='user'?'order-last':''" />
          <div class="max-w-[85%] rounded-2xl px-3 py-2 overflow-hidden cursor-default" :style="[{backgroundColor:msg.role==='user'?userBubbleColor:aiBubbleColor,color:msg.role==='user'?userBubbleTextColor:aiBubbleTextColor},{fontSize:bubbleFontSize+'px'}]" :class="[msg.role==='user'?'rounded-br-md':'rounded-bl-md', msgEditMode && selectedMsgs.has(i) ? 'ring-2 ring-pink-400' : '']" @click="msgEditMode && toggleSelectMsg(i)">
            <img v-if="msg.image" :src="msg.image" class="max-w-[200px] max-h-[200px] rounded-lg mb-1 cursor-zoom-in" @click.stop="viewImage=msg.image" />
            <div v-if="msg.role==='assistant' && showReasoning && msg.reasoning" class="mb-2">
              <button @click="msg.reasoningOpen = msg.reasoningOpen === false ? true : false" class="text-[10px] text-gray-500 dark:text-gray-400 cursor-pointer border-0 bg-transparent p-0 mb-0.5 hover:text-pink-500 flex items-center gap-1">🧠 思考过程 <span class="inline-block transition-transform" :class="msg.reasoningOpen === false ? '' : 'rotate-90'">▸</span></button>
              <div v-show="msg.reasoningOpen !== false" class="text-xs italic whitespace-pre-wrap break-words border-l-2 pl-2 text-gray-500 dark:text-gray-400" style="border-color:currentColor;opacity:0.85;overflow-wrap:anywhere;min-width:0">{{ msg.reasoning }}</div>
            </div>
            <div v-if="msg.reverseResult" class="w-full space-y-2">
              <div v-if="msg.reverseResult.sd_tags" class="rounded-xl border border-blue-800 bg-blue-900 dark:bg-blue-950 p-2.5">
                <div class="flex items-center justify-between mb-1 gap-2">
                  <span class="text-[11px] font-semibold text-blue-200">🎯 SD 标签（反推）</span>
                  <div class="flex items-center gap-1.5 shrink-0">
                    <button @click.stop="genFromReverse(msg.reverseResult.sd_tags)" class="text-[11px] px-2 py-1 rounded-lg bg-blue-500 text-white hover:bg-blue-600 cursor-pointer border-0">🎨 智能生图方案</button>
                    <button @click.stop="openGenPanel(i, msg.reverseResult.sd_tags)" class="text-[11px] px-2 py-1 rounded-lg bg-white/10 text-white hover:bg-white/20 cursor-pointer border-0">✏️ 选此润色</button>
                    <button @click.stop="copyText(msg.reverseResult.sd_tags)" class="text-[11px] px-2 py-1 rounded-lg bg-white/10 text-white hover:bg-white/20 cursor-pointer border-0">📋 复制</button>
                  </div>
                </div>
                <div class="text-[11px] text-blue-50 whitespace-pre-wrap break-words">{{ msg.reverseResult.sd_tags }}</div>
              </div>
              <div v-if="msg.reverseResult.chinese_prompt" class="rounded-xl border border-emerald-800 bg-emerald-900 dark:bg-emerald-950 p-2.5">
                <div class="flex items-center justify-between mb-1 gap-2">
                  <span class="text-[11px] font-semibold text-emerald-200">📝 中文描述（反推）</span>
                  <div class="flex items-center gap-1.5 shrink-0">
                    <button @click.stop="genFromReverse(msg.reverseResult.chinese_prompt)" class="text-[11px] px-2 py-1 rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 cursor-pointer border-0">🎨 智能生图方案</button>
                    <button @click.stop="openGenPanel(i, msg.reverseResult.chinese_prompt)" class="text-[11px] px-2 py-1 rounded-lg bg-white/10 text-white hover:bg-white/20 cursor-pointer border-0">✏️ 选此润色</button>
                    <button @click.stop="copyText(msg.reverseResult.chinese_prompt)" class="text-[11px] px-2 py-1 rounded-lg bg-white/10 text-white hover:bg-white/20 cursor-pointer border-0">📋 复制</button>
                  </div>
                </div>
                <div class="text-[11px] text-emerald-50 whitespace-pre-wrap break-words">{{ msg.reverseResult.chinese_prompt }}</div>
              </div>
            </div>
            <div v-else-if="!msg.genCard || !normalizeText(msg.text).trim().startsWith('生图参数已接收')" class="whitespace-pre-wrap break-words" style="overflow-wrap:anywhere;min-width:0">{{ normalizeText(msg.text) }}</div>
            <!-- 已选角色/画风 chips（仿 2x.nz：随用户消息展示，带类型标签） -->
            <div v-if="msg.role==='user' && msg.selectedChips && msg.selectedChips.length" class="flex flex-wrap gap-1.5 mt-1.5">
              <span v-for="(chip, ci) in msg.selectedChips" :key="ci" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium" :class="chip.type==='角色' ? 'bg-white/25 text-white' : 'bg-black/20 text-white'">
                {{ chip.type === '角色' ? '🎭 角色' : '🎨 画风' }} · {{ chip.name }}
              </span>
            </div>
            <div v-if="msg.role==='assistant' && msg.sources && msg.sources.length" class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600">
              <div class="text-[10px] text-gray-400 mb-1">来源：</div>
              <div v-for="(s, si) in msg.sources.slice(0, 5)" :key="si" class="flex items-center gap-1 text-[11px] leading-tight">
                <span class="text-gray-400">·</span>
                <a v-if="s.url" :href="s.url" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline truncate cursor-pointer" :title="s.url">{{ s.title || s.url }}</a>
                <span v-else class="text-gray-600 dark:text-gray-300 truncate">{{ s.title || '' }}</span>
              </div>
            </div>
            <div v-if="msg.role==='assistant' && !msg.genMeta && normalizeText(msg.text).trim() && !msg.image" class="mt-2">
              <button @click.stop="openGenPanel(i, normalizeText(msg.text))" class="text-[11px] px-2.5 py-1 rounded-lg bg-pink-500 text-white hover:bg-pink-600 cursor-pointer border-0 transition-colors">⚡ 用此提示词生图</button>
            </div>
            <!-- AI 生图卡片（仿 2x.nz） -->
            <div v-if="msg.genCard" class="mt-2 w-full rounded-xl border border-pink-200 dark:border-pink-800 bg-pink-50/60 dark:bg-pink-900/20 p-3">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-semibold text-pink-700 dark:text-pink-300">{{ msg.genCardStatus === 'done' ? '🎉 智能生图方案' : '🃏 审核生图参数' }}</span>
                <span v-if="msg.genCardStatus === 'pending'" class="text-[10px] text-gray-500">等待确认</span>
                <span v-else-if="msg.genCardStatus === 'queued'" class="text-[10px] text-amber-500">⏳ {{ msg.genCardStatusText || '排队中...' }}</span>
                <span v-else-if="msg.genCardStatus === 'done'" class="text-[10px] text-green-600">{{ msg.genCard.width }} × {{ msg.genCard.height }}</span>
                <span v-else-if="msg.genCardStatus === 'error'" class="text-[10px] text-red-500">❌ 生成失败</span>
              </div>
              <p v-if="msg.genCardStatus === 'pending'" class="text-[10px] text-gray-500 dark:text-gray-400 mb-2">请确认以下参数，满意后点击「确认生成」；如需修改可编辑文本框或点「继续讨论」让AI调整。</p>
              <label class="block text-[11px] text-gray-600 dark:text-gray-400 mb-1">
                正向提示词
                <textarea v-model="msg.genCard.prompt" rows="4" class="mt-0.5 w-full border border-pink-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-[11px] outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 resize-y font-mono"></textarea>
              </label>
              <label class="block text-[11px] text-gray-600 dark:text-gray-400 mb-1">
                反向提示词
                <textarea v-model="msg.genCard.negative_prompt" rows="2" class="mt-0.5 w-full border border-pink-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-[11px] outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 resize-y font-mono"></textarea>
              </label>
              <label class="block text-[11px] text-gray-600 dark:text-gray-400 mb-1">
                描述需求
                <textarea v-model="msg.genCard.userReq" rows="2" placeholder="如：加个帽子、改成夜晚、突出足部特写..." class="mt-0.5 w-full border border-pink-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-[11px] outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 resize-y"></textarea>
              </label>
              <div class="flex flex-wrap items-center gap-2 text-[11px] text-gray-600 dark:text-gray-400 mt-1 mb-2">
                <span v-if="msg.genCard.character" @click="msg.genCard.character=''" title="点击取消角色" class="px-2 py-0.5 rounded bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300 cursor-pointer hover:line-through">{{ msg.genCard.character }} ✕</span>
                <span v-if="msg.genCard.style" @click="msg.genCard.style=''" title="点击取消画风" class="px-2 py-0.5 rounded bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 cursor-pointer hover:line-through">{{ msg.genCard.style }} ✕</span>
                <label class="flex items-center gap-1">预设
                  <select :value="genCardSizeLabel(msg.genCard)" @change="applyGenCardSize(i, ($event.target as any).value)" class="border border-pink-200 dark:border-gray-600 rounded px-1.5 py-0.5 text-[11px] outline-none bg-white dark:bg-gray-700">
                    <option value="">自定义</option>
                    <option v-for="s in GEN_SIZES" :key="s.label" :value="s.label">{{ s.label }}</option>
                  </select>
                </label>
                <label class="flex items-center gap-1">宽
                  <input v-model.number="msg.genCard.width" type="number" min="512" max="2000" step="8" class="w-16 border border-pink-200 dark:border-gray-600 rounded px-1.5 py-0.5 text-[11px] outline-none bg-white dark:bg-gray-700" />
                </label>
                <label class="flex items-center gap-1">高
                  <input v-model.number="msg.genCard.height" type="number" min="512" max="2000" step="8" class="w-16 border border-pink-200 dark:border-gray-600 rounded px-1.5 py-0.5 text-[11px] outline-none bg-white dark:bg-gray-700" />
                </label>
              </div>
              <!-- 生成结果图 -->
              <div v-if="msg.genCard.result && msg.genCard.result.length" class="flex flex-wrap gap-2 mb-2">
                <img v-for="(im, ii) in msg.genCard.result" :key="ii" :src="im" class="w-24 h-24 object-cover rounded-lg cursor-zoom-in border border-gray-200 dark:border-gray-600" @click="viewImage=im" />
              </div>
              <!-- 审核态：AI 优化 + 继续讨论 + 确认生成 -->
              <div v-if="msg.genCardStatus !== 'done' && msg.genCardStatus !== 'queued' && msg.genCardStatus !== 'error'" class="flex gap-2">
                <button @click.stop="cardOptimize(i)" :disabled="genCardOptimizing === i" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 disabled:opacity-50">🤖 AI 优化</button>
                <button @click.stop="startContinueDiscuss(i)" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200">继续讨论</button>
                <button @click.stop="confirmGenCard(i)" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-gradient-to-r from-pink-400 to-rose-400 text-white hover:from-pink-300 hover:to-rose-300">🚀 确认生成</button>
              </div>
              <!-- 出图态：刷新图片 + 查看原图 + 编辑（仿 2x.nz） -->
              <div v-else-if="msg.genCardStatus === 'done'" class="flex items-center gap-2">
                <button @click.stop="refreshGenImage(i)" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200">🔄 刷新图片</button>
                <a v-if="msg.genCard.result && msg.genCard.result[0]" :href="msg.genCard.result[0]" target="_blank" rel="noopener noreferrer" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 text-center no-underline">🔗 查看原图</a>
                <button @click.stop="startContinueDiscuss(i)" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300 hover:bg-pink-200">✏️ 编辑</button>
              </div>
              <!-- 失败态：AI 优化 + 重试 + 继续讨论 -->
              <div v-else-if="msg.genCardStatus === 'error'" class="flex gap-2">
                <button @click.stop="cardOptimize(i)" :disabled="genCardOptimizing === i" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 disabled:opacity-50">🤖 AI 优化</button>
                <button @click.stop="confirmGenCard(i)" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300 hover:bg-amber-200">🔄 重试</button>
                <button @click.stop="startContinueDiscuss(i)" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200">继续讨论</button>
              </div>
            </div>
            <div v-if="msg.genMeta" class="mt-2">
              <div class="text-[11px] text-gray-500 dark:text-gray-400 mb-1">{{ msg.genMeta.status === 'done' ? '🖼️ 生图完成' : '⏳ 生成中...' }}</div>
              <a v-if="msg.genMeta.url" :href="msg.genMeta.url" target="_blank" rel="noopener noreferrer" class="text-[11px] text-blue-500 hover:underline cursor-pointer">查看原图 ↗</a>
            </div>
          </div>
        </div>
        <div v-if="msgEditMode" class="flex gap-1 mt-1 px-1">
          <button @click="copyMessage(normalizeText(msg.text))" class="text-[9px] px-1.5 py-0.5 rounded bg-pink-100 dark:bg-pink-900 text-pink-600 dark:text-pink-300 hover:bg-pink-200 cursor-pointer border-0" title="复制">📋 复制</button>
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

    <!-- AI 反问卡片 -->
    <div v-if="pendingQuestion" class="px-3 py-2 border-t border-pink-100 dark:border-gray-600 bg-pink-50/70 dark:bg-gray-800 shrink-0">
      <div class="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">🤔 {{ pendingQuestion.question }}</div>
      <div v-if="pendingQuestion.options.length" class="flex flex-wrap gap-2 mb-2">
        <button v-for="(op, oi) in pendingQuestion.options" :key="oi" @click="answerQuestion(op)" class="px-3 py-1.5 rounded-xl text-xs cursor-pointer border-0 bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300 hover:bg-pink-200">{{ op }}</button>
      </div>
      <div class="flex gap-2">
        <input v-model="questionAnswer" type="text" placeholder="输入你的回答..." class="flex-1 border border-pink-200 dark:border-gray-500 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 placeholder-gray-400" @keydown.enter="answerQuestion('')" />
        <button @click="answerQuestion('')" class="shrink-0 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 bg-pink-500 text-white hover:bg-pink-600">回答</button>
      </div>
    </div>

    <!-- 图片预览 -->
    <div v-if="imagePreview" class="relative px-3 py-1 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0 flex items-center gap-2">
      <img :src="imagePreview" class="max-w-[80px] max-h-[80px] rounded-lg border border-gray-200 dark:border-gray-600 cursor-zoom-in" @click="viewImage=imagePreview" />
      <button @click="removeImage" class="absolute top-0 left-0 w-5 h-5 bg-black/50 text-white rounded-full text-xs flex items-center justify-center cursor-pointer border-0">✕</button>
      <button @click="startReverse" :disabled="reversing" class="text-[11px] px-2.5 py-1 rounded-lg cursor-pointer border-0 transition-colors" :class="reversing ? 'bg-gray-200 text-gray-400 cursor-not-allowed' : 'bg-blue-500 text-white hover:bg-blue-600'">
        {{ reversing ? '反推中...' : '🔍 反推' }}
      </button>
      <div v-if="reverseErr" class="text-[10px] text-red-500">{{ reverseErr }}</div>
    </div>

    <!-- 输入区 -->
    <div class="flex items-center gap-2 px-3 pt-2 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0">
      <button v-if="mode==='token'" @click="toggleWebSearch" class="flex items-center gap-1.5 text-[11px] cursor-pointer select-none shrink-0 border-0 bg-transparent p-1 -m-1" :class="webSearch?'text-pink-500 font-medium':'text-gray-500 dark:text-gray-400'">
        <span class="relative inline-block rounded-full transition-colors" :class="webSearch?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'" style="width:28px;height:18px">
          <span class="absolute bg-white rounded-full transition-all" :class="webSearch?'left-4':'left-0.5'" style="top:2px;width:14px;height:14px"></span>
        </span>
        <span>🔍 联网</span>
      </button>
      <button v-if="mode==='token'" @click="toggleGenMode" class="flex items-center gap-1.5 text-[11px] cursor-pointer select-none shrink-0 border-0 bg-transparent p-1 -m-1" :class="genMode?'text-pink-500 font-medium':'text-gray-500 dark:text-gray-400'">
        <span class="relative inline-block rounded-full transition-colors" :class="genMode?'bg-pink-500':'bg-gray-300 dark:bg-gray-600'" style="width:28px;height:18px">
          <span class="absolute bg-white rounded-full transition-all" :class="genMode?'left-4':'left-0.5'" style="top:2px;width:14px;height:14px"></span>
        </span>
        <span>🖼 生图</span>
      </button>
      <button v-if="mode==='token'" @click="forceGenCard" :disabled="sending" class="shrink-0 text-[11px] px-2 py-1 rounded-lg cursor-pointer border-0 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 disabled:opacity-40 disabled:cursor-not-allowed" title="让 AI 基于当前对话生成审核生图参数卡片">🧩 生成卡片</button>
      <label v-if="mode==='token'" class="flex items-center gap-1 text-[11px] cursor-pointer select-none shrink-0 text-gray-500 dark:text-gray-400">
        <input type="checkbox" :checked="autoApprove" @change="toggleAutoApprove" class="w-3.5 h-3.5 accent-pink-500 cursor-pointer" />
        自动批准
      </label>
    </div>
    <div v-if="discussMode" class="flex items-center justify-between px-3 py-1.5 border-t border-pink-100 dark:border-gray-600 bg-pink-50/70 dark:bg-gray-800 shrink-0">
      <span class="text-[11px] font-semibold text-pink-600 dark:text-pink-300">🛠️ 调整生图参数</span>
      <button @click="discussMode=false; discussTargetIndex=-1" class="text-[10px] px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-pointer border-0 hover:bg-gray-200">取消</button>
    </div>
    <!-- 已选角色/画风 chips（仿 2x.nz：多角色/画风组合，可单独取消） -->
    <div v-if="genSelectedChips.length" class="flex flex-wrap items-center gap-1.5 px-3 py-1.5 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0">
      <span class="text-[10px] font-semibold text-gray-400 dark:text-gray-500">已选</span>
      <span v-for="(chip, ci) in genSelectedChips" :key="ci" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]" :class="chip.type==='角色' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300'">
        {{ chip.name }}
        <button @click="removeGenChip(chip)" class="cursor-pointer border-0 bg-transparent p-0 text-inherit hover:text-red-500" title="取消选择">✕</button>
      </span>
      <button @click="genConfig.character=''; genConfig.characterName=''; genConfig.style=''; genConfig.styleName=''" class="text-[10px] px-1.5 py-0.5 rounded text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent" title="清空全部">清空</button>
    </div>
    <div class="flex items-stretch gap-2 p-3 border-t border-pink-100 dark:border-gray-600 bg-white dark:bg-gray-800 shrink-0">
      <label class="shrink-0 cursor-pointer flex items-center justify-center">
        <input type="file" accept="image/*" class="hidden" @change="onImageSelected" />
        <span class="text-2xl leading-none text-gray-400 dark:text-gray-500 hover:text-pink-500">📷</span>
      </label>
      <textarea v-model="inputText" rows="2" class="flex-1 border border-pink-200 dark:border-gray-500 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 resize-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500" :placeholder="discussMode ? '进一步调整参数…' : '输入消息...'" @keydown.enter.ctrl="send"></textarea>
      <button @click="send" :disabled="sending || (!inputText.trim() && !imageBase64)" class="shrink-0 px-4 rounded-xl bg-gradient-to-r from-pink-400 to-rose-400 text-white text-sm font-semibold hover:from-pink-300 hover:to-rose-300 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer border-0 flex items-center justify-center gap-1">
        <span v-if="sending" class="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"></span>
        {{ sending ? '...' : '发送' }}
      </button>
    </div>

    <!-- Token 用量 / 额度显示 -->
    <div class="shrink-0 px-3 py-1 border-t border-gray-100 dark:border-gray-600 text-[10px] text-gray-500 dark:text-gray-400 flex items-center gap-3" :class="mode==='token' ? 'bg-gray-50 dark:bg-gray-800' : 'bg-white dark:bg-gray-800'">
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
        <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 mb-3">
          <input v-model="aiOptThinking" type="checkbox" class="w-4 h-4 accent-pink-500" />
          🤖 AI 优化启用思考模式（关=快，开=质量更高）
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
        <label class="block text-xs text-gray-600 dark:text-gray-400 mb-3">
          气泡文字大小（px）：{{ bubbleFontSize }}
          <input v-model.number="bubbleFontSize" type="range" min="12" max="22" step="1" class="mt-1 w-full accent-pink-500 h-1 cursor-pointer" />
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

    <!-- 生图配置面板 -->
    <Teleport to="body">
      <div v-if="showGenPanel" class="fixed inset-0 z-[85] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-lg w-full p-5 max-h-[85vh] flex flex-col">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-bold text-gray-700 dark:text-gray-200">⚡ 生图配置</h3>
            <button @click="closeGenPanel" class="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 text-xl cursor-pointer border-0 bg-transparent">&times;</button>
          </div>
          <div class="flex-1 overflow-y-auto min-h-0 space-y-3 pr-1">
            <label class="block text-xs text-gray-600 dark:text-gray-400">
              描述你的需求（AI 优化时使用，可留空直接优化）
              <textarea v-model="genConfig.userReq" rows="2" class="mt-1 w-full border border-gray-200 dark:border-gray-600 rounded-xl px-3 py-2 text-xs outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 resize-y" placeholder="如：加个帽子、改成夜晚、突出足部特写..."></textarea>
            </label>
            <div v-if="genOptimizing" class="text-xs rounded-lg px-3 py-2 bg-purple-50 dark:bg-gray-700 text-purple-600 dark:text-purple-300 flex items-center gap-2">
              <span class="inline-block w-3.5 h-3.5 border-2 border-purple-400 border-t-purple-700 rounded-full animate-spin"></span>
              🤖 AI 优化中...
            </div>
            <label class="block text-xs text-gray-600 dark:text-gray-400">
              正向提示词
              <textarea v-model="genConfig.direct" rows="5" class="mt-1 w-full border border-gray-200 dark:border-gray-600 rounded-xl px-3 py-2 text-xs outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 resize-y font-mono" placeholder="输入正面提示词..."></textarea>
            </label>
            <label class="block text-xs text-gray-600 dark:text-gray-400">
              负面提示词
              <textarea v-model="genConfig.negative" rows="3" class="mt-1 w-full border border-gray-200 dark:border-gray-600 rounded-xl px-3 py-2 text-xs outline-none focus:border-pink-400 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 resize-y font-mono" placeholder="可选"></textarea>
            </label>
            <div class="text-xs text-gray-600 dark:text-gray-400">
              工作流（文生图）
              <select v-model="genConfig.workflow_path" class="mt-1 w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                <option value="" disabled>选择工作流</option>
                <option v-for="w in genWorkflows" :key="w.path" :value="w.path">{{ w.name }}</option>
              </select>
            </div>
            <div class="text-xs text-gray-600 dark:text-gray-400">
              角色
              <div class="flex gap-1.5 mt-1">
                <input v-model="genConfig.character" @input="genConfig.characterName = genConfig.character" type="text" class="flex-1 min-w-0 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" placeholder="自定义角色 tags（可多个，逗号分隔）" />
                <button @click="genShowCharPicker=!genShowCharPicker" class="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] cursor-pointer border-0 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 hover:bg-blue-200">{{ genShowCharPicker ? '收起' : '🎯 选内置' }}</button>
              </div>
              <div v-if="genShowCharPicker" class="mt-1.5 border border-gray-200 dark:border-gray-600 rounded-lg p-2 bg-gray-50 dark:bg-gray-700">
                <input v-model="genCharSearch" type="text" placeholder="搜索角色..." class="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 mb-1.5" />
                <div class="max-h-40 overflow-y-auto space-y-2">
                  <div v-for="g in genCharGroups" :key="g.category" class="space-y-0.5">
                    <div class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 px-1 pt-1 first:pt-0 sticky bg-gray-50 dark:bg-gray-700">{{ g.category }} <span class="text-gray-400">({{ g.items.length }})</span></div>
                    <button v-for="c in g.items" :key="c.name" @click="pickGenCharacter(c)" class="block w-full text-left px-2 py-1 rounded text-[11px] cursor-pointer border-0 hover:bg-blue-50 dark:hover:bg-blue-900/40" :title="c.tags">{{ c.name }}</button>
                  </div>
                  <div v-if="!genCharGroups.length" class="text-[11px] text-gray-400 text-center py-2">无匹配角色</div>
                </div>
                <div class="mt-2 pt-1.5 border-t border-gray-200 dark:border-gray-600">
                  <div class="relative mb-1.5">
                    <input v-model="genAllCharSearch" @input="searchAllChars" type="text" placeholder="🔍 搜索全部角色库（40000+，含内置以外）..." class="w-full border border-blue-200 dark:border-gray-600 rounded-lg px-2 py-1.5 pr-7 text-[11px] outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
                    <button v-if="genAllCharSearch" @click="genAllCharSearch=''; searchAllChars()" class="absolute right-1.5 top-1/2 -translate-y-1/2 text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 cursor-pointer border-0 bg-transparent px-1" title="清空搜索">✕</button>
                  </div>
                  <div v-if="genAllCharSearching" class="flex items-center gap-1.5 text-[10px] text-blue-500 px-1 mb-1.5">
                    <span class="inline-block w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></span>
                    正在搜索角色库...
                  </div>
                  <div v-if="genAllCharResults.length" class="space-y-0.5">
                    <div class="text-[10px] font-semibold text-blue-500 px-1">搜索结果（共 {{ genAllCharResults.length }} 个，点击选用）</div>
                    <div v-for="c in genAllCharResults" :key="c.name + c.tags" @click="pickAllGenCharacter(c)" class="flex items-center gap-2 px-2 py-1 rounded text-[11px] cursor-pointer border-0 hover:bg-blue-50 dark:hover:bg-blue-900/40">
                      <img v-if="c.image" :src="c.image" class="w-7 h-7 object-cover rounded-md shrink-0 border border-gray-200 dark:border-gray-600" loading="lazy" />
                      <span v-else class="w-7 h-7 rounded-md bg-gray-100 dark:bg-gray-700 flex items-center justify-center shrink-0 text-xs">🎭</span>
                      <span class="truncate flex-1">{{ c.name }}<span v-if="c.franchise" class="text-gray-400"> · {{ c.franchise }}</span></span>
                      <button @click.stop="copyText(c.tags || c.name)" class="shrink-0 text-[9px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300 hover:bg-gray-200 cursor-pointer border-0" title="复制 tag">📋</button>
                    </div>
                  </div>
                  <div v-else-if="!genAllCharSearching && genAllCharSearch" class="text-[10px] text-gray-400 px-1">未找到匹配角色，可用自然语言绘制原创角色</div>
                </div>
              </div>
            </div>
            <div class="text-xs text-gray-600 dark:text-gray-400">
              画风
              <div class="flex gap-1.5 mt-1">
                <input v-model="genConfig.style" @input="genConfig.styleName = genConfig.style" type="text" class="flex-1 min-w-0 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" placeholder="自定义画风 tags（如：赛博朋克）" />
                <button @click="genShowStylePicker=!genShowStylePicker" class="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] cursor-pointer border-0 bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-200">{{ genShowStylePicker ? '收起' : '🎨 选内置' }}</button>
              </div>
              <div v-if="genShowStylePicker" class="mt-1.5 border border-gray-200 dark:border-gray-600 rounded-lg p-2 bg-gray-50 dark:bg-gray-700">
                <input v-model="genStyleSearch" type="text" placeholder="搜索画风..." class="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-[11px] outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 mb-1.5" />
                <div class="max-h-40 overflow-y-auto space-y-2">
                  <div v-for="g in genStyleGroups" :key="g.category" class="space-y-0.5">
                    <div class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 px-1 pt-1 first:pt-0 sticky bg-gray-50 dark:bg-gray-700">{{ g.category }} <span class="text-gray-400">({{ g.items.length }})</span></div>
                    <button v-for="s in g.items" :key="s.name" @click="pickGenStyle(s)" class="block w-full text-left px-2 py-1 rounded text-[11px] cursor-pointer border-0 hover:bg-emerald-50 dark:hover:bg-emerald-900/40" :title="s.tags">{{ s.name }}</button>
                  </div>
                  <div v-if="!genStyleGroups.length" class="text-[11px] text-gray-400 text-center py-2">无匹配画风</div>
                </div>
              </div>
            </div>
            <div class="text-xs text-gray-600 dark:text-gray-400">
              尺寸（512×512 ~ 2000×2000）
              <div class="flex flex-wrap gap-1.5 mt-1">
                <button v-for="s in GEN_SIZES" :key="s.label" @click="applyGenSize(s)" class="px-2.5 py-1 rounded-lg text-[11px] cursor-pointer border-0 transition-colors" :class="genConfig.width===s.w && genConfig.height===s.h ? 'bg-pink-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-pink-100'">{{ s.label }}</button>
              </div>
              <div class="flex items-center gap-2 mt-2">
                <span class="text-gray-500 dark:text-gray-400">宽</span><input v-model.number="genConfig.width" type="number" min="512" max="2000" step="8" class="w-20 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-xs outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
                <span class="text-gray-500 dark:text-gray-400">高</span><input v-model.number="genConfig.height" type="number" min="512" max="2000" step="8" class="w-20 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 text-xs outline-none bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200" />
              </div>
            </div>
            <div v-if="genStatusText" class="text-xs rounded-lg px-3 py-2" :class="genStatusText.startsWith('❌') || genStatusText.startsWith('⏳') ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300' : 'bg-pink-50 dark:bg-gray-700 text-pink-600 dark:text-pink-300'">
              {{ genStatusText }}
              <div v-if="genStatusPct > 0" class="mt-1 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                <div class="h-full bg-pink-500 rounded-full transition-all" :style="{ width: genStatusPct + '%' }"></div>
              </div>
            </div>
            <div v-if="genDoneImages.length" class="flex flex-wrap gap-2">
              <img v-for="(im, ii) in genDoneImages" :key="ii" :src="im.url" class="w-24 h-24 object-cover rounded-lg cursor-zoom-in border border-gray-200 dark:border-gray-600" @click="viewImage=im.url" />
            </div>
          </div>
          <div class="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100 dark:border-gray-600">
            <button @click="closeGenPanel" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">取消</button>
            <button @click="optimizeGen" :disabled="genOptimizing || !genConfig.direct.trim() && !genConfig.userReq.trim()" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 disabled:opacity-40 disabled:cursor-not-allowed">
              🤖 AI 优化
            </button>
            <button @click="submitGen()" :disabled="genLoading || !genConfig.direct.trim()" class="flex-1 py-2 rounded-xl text-xs font-semibold cursor-pointer border-0 bg-gradient-to-r from-pink-400 to-rose-400 text-white disabled:opacity-40 disabled:cursor-not-allowed">
              {{ genLoading ? '提交中...' : '🚀 确认生成' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 图片查看大图 -->
    <Teleport to="body">
      <div v-if="viewImage" class="fixed inset-0 z-[90] bg-black/80 flex items-center justify-center p-4" @click="viewImage=''">
        <img :src="viewImage" class="max-w-full max-h-full object-contain rounded-lg" @click.stop />
        <button class="absolute top-4 right-4 w-9 h-9 bg-black/60 text-white rounded-full text-xl flex items-center justify-center cursor-pointer border-0 hover:bg-black/80" @click="viewImage=''">✕</button>
      </div>
    </Teleport>
  </div>
</template>
