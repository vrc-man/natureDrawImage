<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useUserStore } from '@/stores/user'
import { api, apiRaw } from '@/api/client'
import { showToast, showErrorToast } from '@/composables/useToast'
import { useSound } from '@/composables/useSound'
import { useLightbox } from '@/composables/useLightbox'
import { useRouter } from 'vue-router'
import Lightbox from '@/components/Lightbox.vue'
import GalleryGrid from '@/components/GalleryGrid.vue'
import MyWorksGrid from '@/components/MyWorksGrid.vue'
import FeaturedGrid from '@/components/FeaturedGrid.vue'
import GPUBar from '@/components/GPUBar.vue'
import WorkflowPicker from '@/components/WorkflowPicker.vue'
import CharStylePicker from '@/components/CharStylePicker.vue'
import Img2ImgUpload from '@/components/Img2ImgUpload.vue'
import PresetManager from '@/components/PresetManager.vue'
import TotpSettings from '@/components/TotpSettings.vue'

const userStore = useUserStore()
const sound = useSound()
const { lbOpen, lbState, current, open: openLb, close: closeLb, prev: prevLb, next: nextLb } = useLightbox()

// ===== Tab =====
type TabKey = 'generate'|'gallery'|'featured'|'myworks'|'more'
const activeTab = ref<TabKey>('generate')
const tabLoaded = ref<Record<string, boolean>>({})
const tabs = computed(() => {
  const all: { key: TabKey; icon: string; label: string }[] = [
    { key: 'generate', icon: '🎨', label: '生图' },
    { key: 'featured', icon: '✨', label: '精选' },
    { key: 'myworks', icon: '👤', label: '我的' },
    { key: 'more', icon: '⚙️', label: '更多' },
  ]
  if (userStore.isAdmin) all.splice(1, 0, { key: 'gallery', icon: '🖼️', label: '画廊' })
  return all
})

watch(activeTab, (t) => {
  if (t === 'gallery' && !tabLoaded.value.gallery) { tabLoaded.value.gallery = true; nextTick(() => galleryRef.value?.load(true)) }
  if (t === 'myworks' && !tabLoaded.value.myworks) { tabLoaded.value.myworks = true; nextTick(() => myworksRef.value?.load(true)) }
  if (t === 'featured') tabLoaded.value.featured = true
  if (t === 'more') tabLoaded.value['more'] = true
})

const galleryRef = ref<InstanceType<typeof GalleryGrid> | null>(null)
const myworksRef = ref<InstanceType<typeof MyWorksGrid> | null>(null)

// ===== State =====
const onlineCount = ref(0)
const darkMode = ref(localStorage.getItem('dark') === '1')
const genNoticeAcked = ref(document.cookie.includes('genNoticeAcked=1'))
const showGenNoticeModal = ref(false)
const pendingGen = ref<{direct:string;nl:string;neg:string;w:number;h:number;style:string;char:string}>({direct:'',nl:'',neg:'',w:512,h:768,style:'',char:''})

// Generate page state
const mode = ref<'txt2img'|'img2img'>('txt2img')
const directPrompt = ref(localStorage.getItem('formState_direct') || '')
const negativePrompt = ref(localStorage.getItem('formState_negative_prompt') || '')
const nlPrompt = ref(localStorage.getItem('formState_nl') || '')
const rewrite = ref(localStorage.getItem('formState_rewrite') === 'true')
const promptMode = ref(localStorage.getItem('formState_promptMode') || 'tags')
const width = ref(parseInt(localStorage.getItem('formState_w') || '512'))
const height = ref(parseInt(localStorage.getItem('formState_h') || '768'))
const currentWorkflowPath = ref(localStorage.getItem('currentWorkflow') || '')
const img2imgUsePreset = ref(false)

// Fork
const forkedWorkflow = ref<any>(null)
const forkedMeta = ref<any>(null)

// Run state
const _isGenerating = ref(false)
const _finishing = ref(false)
const _watchingMode = ref(false)
const _myQueueRunning = ref(false)
const _pendingCooldown = ref(-1)
const _cooldownDefault = 30

// Progress
const progressText = ref('')
const progressPct = ref(0)
const queueStatus = ref('')
const llmText = ref('')
const logLines = ref<string[]>([])
const showLog = ref(false)
const resultImages = ref<any[]>([])
const myQueueItems = ref<any[]>([])

// Cooldown
const cooldownSec = ref(0)
let cooldownTimer: ReturnType<typeof setInterval> | null = null

// WS
let activeWS: WebSocket | null = null
let statusWS: WebSocket | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let gpuTimer: ReturnType<typeof setInterval> | null = null
let notifyTimer: ReturnType<typeof setInterval> | null = null

// Notification state
const notifyQueueCount = ref(0)
const notifyUnreadCount = ref(0)

// Settings modal
const settingsOpen = ref(false)
const settingsView = ref<'main'|'totp'|'password'>('main')
const soundNotify = ref(localStorage.getItem('soundNotify') === 'true')
const doneNotify = ref(localStorage.getItem('doneNotify') !== 'false')
const soundVol = ref(parseFloat(localStorage.getItem('soundVolume') || '0.7'))
const customSounds = ref({
  done: { data: localStorage.getItem('customSound_done_data') || '', name: localStorage.getItem('customSound_done_name') || '' },
  error: { data: localStorage.getItem('customSound_error_data') || '', name: localStorage.getItem('customSound_error_name') || '' },
  queued: { data: localStorage.getItem('customSound_queued_data') || '', name: localStorage.getItem('customSound_queued_name') || '' },
})

// Password change
const cpOld = ref(''), cpNew = ref(''), cpConfirm = ref(''), cpStatus = ref('')

// Access key
const accessKeyInput = ref('')
const accessKeyError = ref('')
const accessKeySuccess = ref('')
const keyExpired = ref(false)
const uiZoom = ref(parseFloat(localStorage.getItem('uiZoom') || '1'))
const compactLayout = ref(localStorage.getItem('compactLayout') === 'true')

function setUiZoom(v: number) {
  uiZoom.value = v; localStorage.setItem('uiZoom', String(v))
  document.documentElement.style.zoom = String(v)
}
function setCompactLayout(v: boolean) {
  compactLayout.value = v; localStorage.setItem('compactLayout', String(v))
  document.documentElement.classList.toggle('compact', v)
}

// Resolution presets
const resolutions = ref([
  { w: 512, h: 768, label: '512×768' },
  { w: 768, h: 512, label: '768×512' },
  { w: 640, h: 640, label: '640×640' },
  { w: 768, h: 768, label: '768×768' },
  { w: 1024, h: 768, label: '1024×768' },
  { w: 1024, h: 1024, label: '1024×1024' },
])

// Img2Img uploader ref
const uploadRef = ref<InstanceType<typeof Img2ImgUpload> | null>(null)

// ===== Lifecycle =====
let _activePopup: HTMLElement | null = null
let _popupTimer: ReturnType<typeof setTimeout> | null = null

function closePopup() {
  if (_activePopup) { _activePopup.remove(); _activePopup = null }
  if (_popupTimer) { clearTimeout(_popupTimer); _popupTimer = null }
}

function initTooltips() {
  document.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest('.tip-btn') as HTMLElement | null
    if (btn) {
      e.preventDefault()
      closePopup()
      const rect = btn.getBoundingClientRect()
      const popup = document.createElement('div')
      popup.className = 'tip-popup'
      popup.textContent = btn.title || ''
      popup.style.left = Math.min(rect.left, window.innerWidth - 270) + 'px'
      popup.style.top = (rect.bottom + 6) + 'px'
      document.body.appendChild(popup)
      _activePopup = popup
      _popupTimer = setTimeout(closePopup, 3000)
    } else {
      closePopup()
    }
  })
}

function initSakuraPetals() {
  for (let i = 0; i < 8; i++) {
    const p = document.createElement('div')
    p.className = 'sakura-petal'
    p.textContent = '🌸'
    p.style.left = (5 + Math.random() * 90) + '%'
    p.style.top = (5 + Math.random() * 85) + '%'
    p.style.fontSize = (12 + Math.random() * 16) + 'px'
    p.style.opacity = String(0.15 + Math.random() * 0.25)
    p.style.transform = `rotate(${Math.random() * 360}deg)`
    document.body.appendChild(p)
  }
}

onMounted(async () => {
  await userStore.fetchWhoami()
  startPolling()
  connectStatusWS()
  loadAnnouncement()
  startGPUPoll()
  startNotifyPoll()
  loadResolutions()
  loadList()
  if (darkMode.value) document.documentElement.classList.add('dark')
  initTooltips()
  initSakuraPetals()
  initTextareaHeightSync()
  // 恢复 UI 设置
  if (uiZoom.value !== 1) document.documentElement.style.zoom = String(uiZoom.value)
  if (compactLayout.value) document.documentElement.classList.add('compact')
  // 检查密钥过期状态 + 初始化通知圆点
  if (userStore.currentUser?.key_status === 'expired') keyExpired.value = true
  if (userStore.currentUser?.unread_notifications) notifyUnreadCount.value = userStore.currentUser.unread_notifications
  if (userStore.currentUser?.my_queue_count) notifyQueueCount.value = userStore.currentUser.my_queue_count
  // Load forked workflow
  try {
    const fw = localStorage.getItem('forkedWorkflow')
    if (fw) forkedWorkflow.value = JSON.parse(fw)
    const fm = localStorage.getItem('forkedMeta')
    if (fm) forkedMeta.value = JSON.parse(fm)
  } catch {}
})

onUnmounted(() => {
  stopPolling()
  if (statusWS) try { statusWS.close() } catch {}
  if (gpuTimer) clearInterval(gpuTimer)
  if (notifyTimer) clearInterval(notifyTimer)
  if (cooldownTimer) clearInterval(cooldownTimer)
})

// ===== Form Persistence =====
const FORM_FIELDS = ['direct', 'negative_prompt', 'nl', 'rewrite', 'promptMode', 'w', 'h']
watch([directPrompt, negativePrompt, nlPrompt, rewrite, promptMode, width, height], () => {
  localStorage.setItem('formState_direct', directPrompt.value)
  localStorage.setItem('formState_negative_prompt', negativePrompt.value)
  localStorage.setItem('formState_nl', nlPrompt.value)
  localStorage.setItem('formState_rewrite', String(rewrite.value))
  localStorage.setItem('formState_promptMode', promptMode.value)
  localStorage.setItem('formState_w', String(width.value))
  localStorage.setItem('formState_h', String(height.value))
})

// ===== Workflows =====
const allWorkflows = ref<any[]>([])
const wfDirs = ref({ txt2img: '', img2img: '' })
async function loadList() {
  try {
    const d = await api<any>('GET', '/api/workflows')
    if (d.workflows) allWorkflows.value = d.workflows
    else if (d.all) allWorkflows.value = d.all
  } catch {}
}
async function onWorkflowSelect(path: string) {
  currentWorkflowPath.value = path
  localStorage.setItem('currentWorkflow', path)
  try {
    const r = await fetch(`/api/workflows/current?path=${encodeURIComponent(path)}&_t=${Date.now()}`)
    const d = await r.json()
    if (d.path && !d.error) {
      if (d.builtin_prompt) directPrompt.value = d.builtin_prompt.trim()
      if (d.builtin_negative_prompt) negativePrompt.value = d.builtin_negative_prompt.trim()
      if (d.default_width && d.default_height) { width.value = d.default_width; height.value = d.default_height }
    }
  } catch {}
}

// ===== Char/Style selection (handled by CharStylePicker via localStorage) =====
const selectedStyleTags = ref(localStorage.getItem('currentStyle') || '')
const selectedCharTags = ref(localStorage.getItem('currentCharacters') || '')

// ===== Fetch resolutions =====
async function loadResolutions() {
  try {
    const r = await api<any>('GET', '/api/resolutions')
    if (r.presets) resolutions.value = r.presets
    else if (Array.isArray(r)) resolutions.value = r
  } catch {}
}

// ===== Polling =====
let _notifiedTaskIds = new Set<number>()
let _hasRunningBefore = false
let _doneNotified = false  // WS done/error 已通知过，防止 pollMyQueue 重复
function startPolling() { pollTimer = setInterval(pollMyQueue, 1000) }
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

async function pollMyQueue() {
  try {
    const d = await api<any>('GET', '/api/my-queue')
    const items: any[] = d.items || []
    myQueueItems.value = items
    const waiting = items.filter((i: any) => i.status === 'waiting')
    const running = items.filter((i: any) => i.status === 'running')
    const hasMyTask = waiting.length || running.length

    // 正在生图中不检查（避免 WS 还没连上、任务还没入队时被恢复逻辑打断）
    if (_isGenerating.value) return

    const noActiveWS = !(activeWS && activeWS.readyState === WebSocket.OPEN)
    if (running.length) _hasRunningBefore = true
    if (!items.length && noActiveWS) {
      _myQueueRunning.value = false
      // 队列空+无WS → 强制恢复按钮（原版逻辑）
      const btn = document.getElementById('btn-run') as HTMLButtonElement | null
      if (btn && btn.disabled) {
        btn.disabled = false
        btn.textContent = '▶ 开始生成'
      }
      // 任务完成通知（先检查再设 _finishing）
      if ((_watchingMode.value || _hasRunningBefore) && !_doneNotified) {
        _watchingMode.value = false
        _hasRunningBefore = false
        _finishing.value = true
        if (!_doneNotified) {
          showToast('✅ 任务已完成，请到「我的」查看')
          sound.play('done')
          sound.sendNotification('✅ 生图完成，请到「我的」查看')
        }
      }
    } else {
      _myQueueRunning.value = !!running.length
      // 有任务时禁用按钮（原版逻辑：刷新页面后 _isGenerating 可能为 false 但任务仍在运行）
      if (hasMyTask) {
        const btn = document.getElementById('btn-run') as HTMLButtonElement | null
        if (btn && !btn.disabled) btn.disabled = true
      }
    }

    // WS 断开后轮询检测任务完成
    if (_watchingMode.value) {
      if (!running.length && !waiting.length) {
        const btn = document.getElementById('btn-run') as HTMLButtonElement | null
        if (btn && btn.disabled) { btn.disabled = false; btn.textContent = '▶ 开始生成' }
        if (!_finishing.value && !_doneNotified) {
          _watchingMode.value = false; _doneNotified = true
          const failedItem = items.find((i: any) => i.status === 'failed')
          const errMsg = failedItem?.error_message || ''
          showToast(errMsg ? '❌ ' + errMsg : '✅ 任务已完成，请到「我的」查看')
          sound.play(errMsg ? 'error' : 'done')
          sound.sendNotification(errMsg ? '❌ ' + errMsg : '✅ 生图完成，请到「我的」查看')
          finishRun()
        }
      } else {
        progressText.value = running.length ? '⚡ 生图中...' : '⏳ ' + (waiting[0]?.position ? `排队第 ${waiting[0].position} 位` : '排队中')
      }
    }
    // 页面刷新后检测已完成/失败的任务
    const doneItems = items.filter((i: any) => i.status === 'done' || i.status === 'failed')
    if (doneItems.length) {
      const btn = document.getElementById('btn-run') as HTMLButtonElement | null
      if (btn && btn.disabled) { btn.disabled = false; btn.textContent = '▶ 开始生成' }
    }
    for (const item of doneItems) {
      if (!_notifiedTaskIds.has(item.id)) {
        _notifiedTaskIds.add(item.id)
        if (!_finishing.value && !_doneNotified && noActiveWS) {
          _doneNotified = true
          const errMsg = item.error_message || ''
          showToast(errMsg ? '❌ ' + errMsg : '✅ 任务已完成，请到「我的」查看')
          sound.play(item.status === 'done' ? 'done' : 'error')
          finishRun()
        }
      }
    }
  } catch {}
}

async function pollNotifications() {
  try {
    const d = await api<any>('GET', '/api/notifications')
    if (d.online_count !== undefined) onlineCount.value = d.online_count
    if (d.my_queue_count !== undefined) notifyQueueCount.value = d.my_queue_count
    if (d.unread_notifications !== undefined) notifyUnreadCount.value = d.unread_notifications
  } catch {}
}

async function onNotifyBellClick() {
  if (notifyUnreadCount.value > 0) {
    alert('您有后台任务已完成，请到「我的」查看新作品')
    try { await api<any>('POST', '/api/whoami/read-notifications'); notifyUnreadCount.value = 0 } catch {}
  } else if (notifyQueueCount.value > 0) {
    alert('任务正在排队或执行中，请稍候')
  }
}

function startGPUPoll() {
  const interval = parseInt(localStorage.getItem('gpuInterval') || '15') * 1000
  gpuTimer = setInterval(() => { api('GET', '/api/gpu').catch(() => {}) }, interval)
}
function startNotifyPoll() { notifyTimer = setInterval(pollNotifications, 2000) }

function connectStatusWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${location.host}/ws/status`)
  ws.onmessage = (e) => {
    try {
      const m = JSON.parse(e.data)
      if (m.type === 'online') onlineCount.value = m.count || 0
      else if (m.type === 'cooldown_done') stopCooldown()
      else if (m.type === 'mirror' && !activeWS) handleMsg(m.event)
    } catch {}
  }
  ws.onclose = () => { setTimeout(connectStatusWS, 2000) }
  statusWS = ws
}

// ===== Generate =====
function setMode(m: 'txt2img'|'img2img') { mode.value = m }

function prepareGen() {
  const direct = directPrompt.value.trim()
  const nl = nlPrompt.value.trim()
  const neg = negativePrompt.value.trim()
  const style = selectedStyleTags.value
  const char = selectedCharTags.value
  if (!direct && !nl) { showErrorToast('请输入提示词'); return null }
  return { direct, nl, neg, w: width.value, h: height.value, style, char }
}

async function startRun() {
  if (_isGenerating.value) return
  const g = prepareGen()
  if (!g) return
  if (g.nl && !genNoticeAcked.value) {
    pendingGen.value = g
    showGenNoticeModal.value = true
    return
  }
  actuallyStartRun(g)
}

function acceptGenNotice() {
  genNoticeAcked.value = true
  document.cookie = 'genNoticeAcked=1; path=/; max-age=31536000; Secure; SameSite=Lax'
  showGenNoticeModal.value = false
  actuallyStartRun(pendingGen.value)
}

function cancelGenNotice() {
  showGenNoticeModal.value = false
  _isGenerating.value = false
}

async function actuallyStartRun(g: {direct:string;nl:string;neg:string;w:number;h:number;style:string;char:string;}) {
  _watchingMode.value = false
  _finishing.value = false
  _doneNotified = false
  _isGenerating.value = true
  progressPct.value = 0
  resultImages.value = []
  logLines.value = []

  let image1_name = '', image2_name = '', image3_name = ''
  if (mode.value === 'img2img' && uploadRef.value) {
    progressText.value = '等待图片上传...'
    await uploadRef.value.waitAllUploads()
    const names = uploadRef.value.getImageNames()
    image1_name = names[0] || ''; image2_name = names[1] || ''; image3_name = names[2] || ''
  } else {
    progressText.value = '等待服务器响应...'
  }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${location.host}/ws/run`)
  activeWS = ws

  ws.onopen = () => {
    const payload: any = {
      workflow_path: currentWorkflowPath.value,
      mode: mode.value,
      direct_prompt: g.direct,
      nl_prompt: g.nl,
      negative_prompt: g.neg,
      rewrite: rewrite.value,
      prompt_mode: promptMode.value,
      width: g.w,
      height: g.h,
      style_tags: g.style,
      character_tags: g.char,
      img2img_use_preset: img2imgUsePreset.value,
      image1_name, image2_name, image3_name,
    }
    if (forkedWorkflow.value) payload.inline_workflow = forkedWorkflow.value
    ws.send(JSON.stringify(payload))
  }
  ws.onmessage = (e) => {
    try { handleMsg(JSON.parse(e.data)) } catch {}
  }
  ws.onclose = () => {
    activeWS = null
    _watchingMode.value = true
    pollMyQueue()
  }
}

function handleMsg(m: any) {
  if (m.type === 'log') { logLines.value.push(m.message) }
  else if (m.type === 'queued') {
    queueStatus.value = m.message || '排队中...'
    progressText.value = '排队中...'
    pollMyQueue()
    showToast('⏳ 任务已提交，排队中')
    sound.play('queued')
  }
  else if (m.type === 'queue_start') {
    queueStatus.value = ''
    progressText.value = m.message || '开始执行...'
    pollMyQueue()
    showToast('⚡ 任务开始执行')
  }
  else if (m.type === 'llm_start') { llmText.value = ''; progressText.value = '' }
  else if (m.type === 'llm_chunk') { llmText.value += m.delta }
  else if (m.type === 'llm_done') {
    if (m.negative && !negativePrompt.value.trim()) negativePrompt.value = m.negative
  }
  else if (m.type === 'progress') {
    queueStatus.value = ''
    if (m.max && m.max > 1) {
      const pct = Math.floor((m.value || 0) * 100 / m.max)
      progressPct.value = pct
      progressText.value = `${m.node} ${m.value}/${m.max} (${pct}%)  节点 ${m.done||0}/${m.total||0}`
    } else { progressText.value = `执行: ${m.node}` }
  }
  else if (m.type === 'prompt_id') {}
  else if (m.type === 'image') { resultImages.value.push({ url: m.url, filename: m.filename, path: m.path }); pushHistory(m) }
  else if (m.type === 'done') {
    logLines.value.push(`✅ 完成，共 ${m.count} 张`)
    progressText.value = '完成，请到「我的」查看'
    showToast('✅ 生图完成，请到「我的」查看')
    sound.play('done')
    sound.sendNotification('✅ 生图完成，请到「我的」查看')
    _pendingCooldown.value = typeof m.cooldown_remaining === 'number' ? m.cooldown_remaining : -1
    flashGreen()
    _doneNotified = true
    finishRun()
  }
  else if (m.type === 'error') {
    logLines.value.push('❌ ' + m.message)
    sound.play('error')
    progressText.value = '失败: ' + m.message
    sound.sendNotification('❌ ' + m.message)
    const el = document.createElement('div')
    el.className = 'toast-el bg-white/95 backdrop-blur border border-red-200 rounded-2xl shadow-xl px-5 py-4 text-sm sm:text-base text-red-700 cursor-pointer select-none'
    el.textContent = '❌ ' + m.message
    el.onclick = () => { el.style.animation = 'toastOut 0.25s ease-in'; setTimeout(() => el.remove(), 250) }
    const tc = document.getElementById('toast-container')
    if (tc) tc.appendChild(el)
    _pendingCooldown.value = typeof m.cooldown_remaining === 'number' ? m.cooldown_remaining : -1
    _doneNotified = true
    finishRun()
  }
}

function pushHistory(m: any) {
  let hist: any[] = []
  try { hist = JSON.parse(localStorage.getItem('genHistory') || '[]') } catch {}
  hist.unshift({ url: m.url, filename: m.filename, time: Date.now() })
  if (hist.length > 100) hist = hist.slice(0, 100)
  localStorage.setItem('genHistory', JSON.stringify(hist))
}

function flashGreen() {
  notifyUnreadCount.value++
  setTimeout(() => { if (notifyUnreadCount.value > 0) notifyUnreadCount.value-- }, 2000)
}

function finishRun() {
  if (_finishing.value) return
  _finishing.value = true
  _isGenerating.value = false
  _myQueueRunning.value = false
  if (activeWS) { try { activeWS.close() } catch {} }
  activeWS = null
  if (!userStore.isAdmin && _pendingCooldown.value >= 0) {
    startCooldown(_pendingCooldown.value >= 0 ? _pendingCooldown.value : _cooldownDefault)
  }
  _pendingCooldown.value = -1
  pollMyQueue()
}

function startCooldown(sec: number) {
  stopCooldown()
  cooldownSec.value = sec
  const tick = () => {
    if (cooldownSec.value <= 0) { stopCooldown(); return }
    cooldownSec.value--
  }
  tick()
  cooldownTimer = setInterval(tick, 1000)
}
function stopCooldown() {
  if (cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = null }
  cooldownSec.value = 0
}

// ===== Access Key =====
async function submitKey() {
  accessKeyError.value = ''; accessKeySuccess.value = ''
  try {
    const d = await api<any>('POST', '/api/auth/claim-key', { key: accessKeyInput.value.trim() })
    if (d.ok) { accessKeySuccess.value = '✅ ' + (d.message || '密钥验证成功'); await userStore.fetchWhoami() }
    else { accessKeyError.value = d.detail || '密钥无效' }
  } catch (e: any) { accessKeyError.value = e.message }
}

// ===== Dark Mode =====
function toggleDark() {
  darkMode.value = !darkMode.value
  localStorage.setItem('dark', darkMode.value ? '1' : '0')
  document.documentElement.classList.toggle('dark', darkMode.value)
}

// ===== Settings =====
const keyInfoHtml = ref('加载中...')
function openSettings() {
  settingsOpen.value = true; settingsView.value = 'main'
  fetch('/api/whoami').then(r => r.json()).then(fresh => {
    const ki = fresh.key_info
    if (ki) {
      let h = '<div class="flex items-center gap-1.5 font-medium text-gray-700 mb-1">🔑 密钥信息</div>'
      if (ki.expires_at) h += `<div class="flex justify-between"><span>过期时间</span><span>${new Date(ki.expires_at * 1000).toLocaleString()}</span></div>`
      if (ki.used_count !== undefined) h += `<div class="flex justify-between"><span>已使用</span><span>${ki.used_count}${ki.max_uses ? ' / ' + ki.max_uses : ''}</span></div>`
      if (ki.remaining_days !== undefined) h += `<div class="flex justify-between"><span>剩余天数</span><span>${ki.remaining_days}</span></div>`
      if (ki.forever) h += '<div class="text-green-500">♾️ 永久有效</div>'
      if (!h.includes('过期') && !ki.forever) h += '<div class="text-gray-400">基本版密钥</div>'
      keyInfoHtml.value = h
    } else { keyInfoHtml.value = '' }
  }).catch(() => { keyInfoHtml.value = '' })
}
function closeSettings() { settingsOpen.value = false }
function saveSoundNotify(v: boolean) { soundNotify.value = v; localStorage.setItem('soundNotify', String(v)) }
function saveDoneNotify(v: boolean) { doneNotify.value = v; localStorage.setItem('doneNotify', String(v)) }
function saveSoundVol(v: number) { soundVol.value = v; localStorage.setItem('soundVolume', String(v)) }
function loadCustomSound(type: string) { return customSounds.value[type as keyof typeof customSounds.value] || { data: '', name: '' } }
function saveCustomSound(type: string, data: string, name: string) {
  if (data) { localStorage.setItem('customSound_' + type + '_data', data); localStorage.setItem('customSound_' + type + '_name', name) }
  else { localStorage.removeItem('customSound_' + type + '_data'); localStorage.removeItem('customSound_' + type + '_name') }
  customSounds.value[type as keyof typeof customSounds.value] = { data, name }
}
function handleSoundUpload(type: string) {
  const inp = document.createElement('input')
  inp.type = 'file'; inp.accept = 'audio/*'
  inp.onchange = () => {
    const f = inp.files![0]; if (!f) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      saveCustomSound(type, ev.target!.result as string, f.name)
      new Audio(ev.target!.result as string).play().catch(() => {})
    }
    reader.readAsDataURL(f)
  }
  inp.click()
}
function resetCustomSound(type: string) { saveCustomSound(type, '', '') }

async function changePassword() {
  cpStatus.value = ''
  if (!cpOld.value) { cpStatus.value = '请输入当前密码'; return }
  if (cpNew.value.length < 6) { cpStatus.value = '新密码至少6位'; return }
  if (cpNew.value !== cpConfirm.value) { cpStatus.value = '两次密码不一致'; return }
  cpStatus.value = '...'
  try {
    const r = await api<any>('POST', '/api/auth/change-password', { old_password: cpOld.value, new_password: cpNew.value })
    cpStatus.value = '✅ ' + (r.message || '修改成功')
  } catch (e: any) { cpStatus.value = e.message }
}

// ===== Logout =====
async function logout() {
  await apiRaw('/auth/logout', { method: 'POST', headers: {'Content-Type':'application/json'} })
  location.href = '/'
}

// ===== Announcement =====
const annTitle = ref('')
const annContent = ref('')
async function loadAnnouncement() {
  try {
    const d = await api<any>('GET', '/api/announcement')
    if (d?.announcement?.title) { annTitle.value = d.announcement.title; annContent.value = d.announcement.content }
  } catch {}
}

// ===== Textarea height sync (与原版一致) =====
let _thTimer: ReturnType<typeof setTimeout> | null = null
let _lastThSync = 0
function initTextareaHeightSync() {
  if (!window.ResizeObserver) return
  ;['direct', 'negative_prompt', 'nl'].forEach(id => {
    const el = document.getElementById(id) as HTMLTextAreaElement | null
    if (!el) return
    new ResizeObserver(() => {
      if (_thTimer) clearTimeout(_thTimer)
      _thTimer = setTimeout(() => {
        const h = el.style.height
        const saved: Record<string, string> = {}
        try { Object.assign(saved, JSON.parse(localStorage.getItem('taHeights') || '{}')) } catch {}
        saved[id] = h
        if (id === 'direct' || id === 'negative_prompt') {
          const peer = document.getElementById(id === 'direct' ? 'negative_prompt' : 'direct') as HTMLTextAreaElement | null
          const now = Date.now()
          if (peer && h && h !== peer.style.height && now - _lastThSync > 300) {
            _lastThSync = now
            peer.style.height = h
          }
          saved.direct = h
          saved.negative_prompt = h
        }
        localStorage.setItem('taHeights', JSON.stringify(saved))
      }, 400)
    }).observe(el)
  })
  // 恢复保存的高度
  try {
    const saved: Record<string, string> = JSON.parse(localStorage.getItem('taHeights') || '{}')
    Object.entries(saved).forEach(([id, h]) => {
      const el = document.getElementById(id) as HTMLTextAreaElement | null
      if (el && h) el.style.height = h
    })
  } catch {}
}

function clearFork() {
  forkedWorkflow.value = null
  localStorage.removeItem('forkedWorkflow')
  localStorage.removeItem('forkedMeta')
}
function fillPreset(text: string, target: 'direct' | 'negative_prompt') {
  if (target === 'direct') directPrompt.value = text
  else negativePrompt.value = text
}
</script>

<template>
  <div class="h-full w-full" :class="{dark:darkMode}">
    <div class="h-full w-full flex flex-col" style="background:linear-gradient(135deg,#fef2f4,#fdf2f8,#faf5ff,#fff1f2,#fef2f4);background-size:400% 400%;animation:bgShift 30s ease infinite">
      <!-- Header -->
      <div class="flex items-center justify-between px-4 pt-3 pb-1 shrink-0 fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md">
        <div class="flex items-center gap-2">
          <h1 class="text-sm font-bold text-pink-500">🎨 二次元绘梦</h1>
          <span class="text-[10px] text-gray-400 bg-white/50 px-2 py-0.5 rounded-full">{{ onlineCount }} 在线</span>
        </div>
        <div class="flex items-center gap-1">
          <button @click="toggleDark" class="text-base px-1.5 py-1 rounded-xl hover:bg-pink-50 transition-all cursor-pointer border-0" title="夜间模式">{{ darkMode ? '☀️' : '🌙' }}</button>
          <div @click="onNotifyBellClick" class="relative w-[18px] h-[18px] rounded-full cursor-pointer" :class="notifyUnreadCount>0?'bg-green-500 shadow':notifyQueueCount>0?'bg-yellow-400 shadow':'bg-gray-400'" title="通知">
            <span v-if="notifyUnreadCount > 0" class="absolute -top-1.5 -right-2.5 bg-gradient-to-b from-green-400 to-green-600 text-white text-[9px] rounded-full min-w-[16px] h-4 flex items-center justify-center font-bold shadow-md px-0.5">{{ notifyUnreadCount }}</span>
            <span v-else-if="notifyQueueCount > 0" class="absolute -top-1.5 -right-2.5 bg-gradient-to-b from-yellow-400 to-yellow-600 text-white text-[9px] rounded-full min-w-[16px] h-4 flex items-center justify-center font-bold shadow-md px-0.5">{{ notifyQueueCount }}</span>
          </div>
          <a v-if="userStore.isAdmin" href="/admin" class="text-xs px-2 py-1 rounded-full bg-pink-50 text-pink-600 font-medium hover:bg-pink-100 transition-all no-underline">管理</a>
          <span v-if="userStore.isLoggedIn" class="px-2 py-1 rounded-full bg-pink-50 text-pink-600 cursor-pointer relative font-medium text-xs select-none" @click="openSettings">
            {{ userStore.currentUser?.login }} ▾
          </span>
          <a v-else href="/auth/email-login" class="text-xs px-2 py-1 rounded-full bg-pink-50 text-pink-600 font-medium hover:bg-pink-100 transition-all no-underline">登录</a>
        </div>
      </div>

        <!-- Tab Pages -->
      <div class="flex-1 relative">
        <!-- ============ GENERATE ============ -->
        <div v-if="activeTab === 'generate'" class="tab-page active p-4 sm:p-6">
          <div class="max-w-5xl mx-auto space-y-6">
            <!-- Access Key (only for non-admin, no key, logged-in) -->
            <div v-if="!userStore.isAdmin && !userStore.currentUser?.access_granted && userStore.isLoggedIn" class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-8 text-center max-w-md mx-auto">
              <p class="text-4xl mb-4">🔑</p>
              <p class="text-sm text-gray-500 mb-4">{{ keyExpired ? '您的密钥已过期，请输入新密钥或联系管理员获取' : '需要使用管理员分配的访问密钥才能使用生图服务' }}</p>
              <input v-model="accessKeyInput" @keydown.enter="submitKey" type="text" placeholder="输入访问密钥" class="w-full border border-pink-200 rounded-xl px-4 py-2.5 text-sm text-center mb-3 outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 box-border" />
              <button @click="submitKey" class="w-full py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl text-sm font-semibold hover:from-pink-300 hover:to-rose-300 transition-all cursor-pointer border-0 shadow-md shadow-pink-300/30">提交</button>
              <p v-if="accessKeyError" class="text-xs text-red-400 mt-2">{{ accessKeyError }}</p>
              <p v-if="accessKeySuccess" class="text-xs text-green-500 mt-2">{{ accessKeySuccess }}</p>
            </div>

            <!-- Main generate area (always visible) -->
            <div>
              <!-- Fork badge -->
              <div v-if="forkedWorkflow" class="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-200 rounded-2xl text-xs text-amber-700 mb-2">
                🍴 Fork: {{ forkedMeta?.display_path || '自定义工作流' }}
                <button @click="clearFork" class="ml-auto text-amber-400 hover:text-amber-600 cursor-pointer border-0 bg-transparent">✕ 取消</button>
              </div>

              <!-- Mode switch -->
              <div class="flex gap-2">
                <button class="flex-1 py-3 text-base font-semibold rounded-2xl transition-all cursor-pointer border-0 active:scale-[0.98]" :class="mode==='txt2img'?'bg-gradient-to-r from-pink-400 to-rose-400 text-white shadow-lg shadow-pink-300/30':'bg-white/70 text-gray-400 border-2 border-pink-100 hover:border-pink-300 hover:text-gray-600'" @click="setMode('txt2img')">📝 文生图</button>
                <button class="flex-1 py-3 text-base font-semibold rounded-2xl transition-all cursor-pointer border-0 active:scale-[0.98]" :class="mode==='img2img'?'bg-gradient-to-r from-pink-400 to-rose-400 text-white shadow-lg shadow-pink-300/30':'bg-white/70 text-gray-400 border-2 border-pink-100 hover:border-pink-300 hover:text-gray-600'" @click="setMode('img2img')">🖼️ 图生图</button>
              </div>

              <!-- Workflow + Char/Style side by side -->
              <div class="flex flex-col sm:flex-row gap-4 sm:gap-6">
                <div class="flex-1 min-w-0 bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6">
                  <WorkflowPicker :mode="mode" @select="onWorkflowSelect" />
                </div>
                <div class="flex-1 min-w-0 bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6">
                  <CharStylePicker />
                </div>
              </div>

              <!-- Prompt form card -->
              <div class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6 space-y-5">
                <!-- Prompt grid -->
                <div class="prompt-grid">
                  <div>
                    <label class="flex text-sm font-semibold mb-1.5 text-gray-600 items-center gap-1">
                      <button type="button" title="提示词预设" class="cursor-pointer hover:scale-110 transition-transform bg-transparent border-0 p-0 text-inherit text-base" @click.stop>📝</button>
                      <span>正面提示词</span>
                      <span class="ml-auto flex items-center gap-1">
                        <PresetManager target="direct" :on-fill="(t:string) => fillPreset(t, 'direct')" />
                        <button @click="directPrompt=''" class="text-xs text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded px-2 py-0.5 transition-all cursor-pointer border-0">清空</button>
                      </span>
                    </label>
                    <textarea id="direct" v-model="directPrompt" placeholder="正面提示词（英文标签或自然语言）" rows="1" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm font-mono bg-white resize-y outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 box-border"></textarea>
                  </div>
                  <div>
                    <label class="flex text-sm font-semibold mb-1.5 text-gray-600 items-center gap-1">
                      <button type="button" title="提示词预设" class="cursor-pointer hover:scale-110 transition-transform bg-transparent border-0 p-0 text-inherit text-base" @click.stop>📝</button>
                      <span>负面提示词</span>
                      <span class="ml-auto flex items-center gap-1">
                        <PresetManager target="negative_prompt" :on-fill="(t:string) => fillPreset(t, 'negative_prompt')" />
                        <button @click="negativePrompt=''" class="text-xs text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded px-2 py-0.5 transition-all cursor-pointer border-0">清空</button>
                      </span>
                    </label>
                    <textarea id="negative_prompt" v-model="negativePrompt" placeholder="负面提示词（可留空）" rows="1" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm font-mono bg-white resize-y outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 box-border"></textarea>
                  </div>
                </div>

                <!-- NL prompt -->
                <div>
                  <label class="flex text-sm font-semibold mb-1.5 text-gray-600 items-center gap-1">
                    <span>自然语言描述</span>
                    <span class="text-gray-400 font-normal text-[7px] sm:text-sm">(中文/英文，LLM 翻译生成提示词)</span>
                    <button @click="nlPrompt=''" class="ml-auto text-xs text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded px-2 py-0.5 transition-all cursor-pointer border-0">清空</button>
                  </label>
                  <textarea id="nl" v-model="nlPrompt" placeholder="描述你想要的画面，LLM 会自动翻译为 tags" rows="2" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm bg-white resize-y outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 box-border"></textarea>
                </div>

                <!-- Options row -->
                <div class="flex items-center flex-wrap gap-3">
                  <label class="flex items-center gap-1.5 text-sm font-medium text-gray-600 cursor-pointer select-none">
                    <input type="checkbox" v-model="rewrite" class="w-4 h-4 accent-pink-500" /> 改写
                    <span class="tip-btn text-gray-400 ml-1 text-base cursor-pointer font-bold" title="改写：LLM 基于「直接 Tag」结合「自然语言描述」整体重写 prompt&#10;不勾选：LLM 翻译后追加到原 prompt 后面">?</span>
                  </label>
                  <select v-model="promptMode" class="text-xs border border-pink-200 rounded-lg px-2 py-1 bg-white text-gray-600 outline-none focus:border-pink-400">
                    <option value="tags">Danbooru Tags</option>
                    <option value="natural">自然英文</option>
                  </select>
                  <div class="flex flex-wrap gap-1.5" id="res-presets">
                    <button v-for="r in resolutions" :key="r.w+'-'+r.h" @click="width=r.w;height=r.h" :title="r.w+'×'+r.h"
                      class="text-xs px-2 py-1 rounded-lg border transition-all cursor-pointer"
                      :class="width===r.w&&height===r.h?'bg-pink-500 text-white border-pink-500':'bg-white text-gray-500 border-pink-100 hover:border-pink-300'">
                      {{ r.label || r.w+'×'+r.h }}
                    </button>
                  </div>
                </div>

                <!-- Img2img upload -->
                <div v-if="mode==='img2img'">
                  <label class="block text-sm font-semibold mb-1.5 text-gray-600">🖼️ 输入图 <span class="text-gray-400 font-normal">(最多3张，单张≤3MB)</span></label>
                  <Img2ImgUpload ref="uploadRef" />
                  <label class="flex items-center gap-1.5 text-sm text-gray-500 mt-2 cursor-pointer select-none">
                    <input v-model="img2imgUsePreset" type="checkbox" class="w-4 h-4 accent-pink-500" />
                    注入上方所选分辨率（默认不勾选，保持原图尺寸）
                  </label>
                </div>

                <!-- Run button -->
                <button @click="startRun"
                  class="w-full py-3 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-2xl font-semibold text-base shadow-lg shadow-pink-300/30 transition-all active:scale-[0.98] disabled:from-gray-200 disabled:to-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed border-0"
                id="btn-run"
                :class="{cooldown: cooldownSec > 0}"
                :disabled="_isGenerating || (!userStore.isAdmin && !userStore.currentUser?.access_granted && userStore.isLoggedIn)">
                {{ _isGenerating ? '⏳ 生成中...' : cooldownSec > 0 ? `⏳ 冷却中 ${cooldownSec}s` : (!userStore.isAdmin && !userStore.currentUser?.access_granted && userStore.isLoggedIn) ? '🔑 需要访问密钥' : '▶ 开始生成' }}
              </button>
              </div>

              <!-- Progress card -->
              <div v-if="progressText || _isGenerating || _watchingMode || llmText" class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6 space-y-3">
                <div v-if="queueStatus" id="queue-status" class="text-sm text-amber-600 text-center font-semibold">{{ queueStatus }}</div>
                <div v-if="progressPct > 0" class="w-full bg-pink-100 rounded-full h-2.5 overflow-hidden">
                  <div id="progress-bar" class="h-2.5 rounded-full" :style="{width:progressPct+'%'}"></div>
                </div>
                <div id="progress-text" class="text-sm text-gray-500 text-center">{{ progressText }}</div>
                <div v-if="llmText" class="text-xs bg-rose-50 border border-pink-100 p-3 rounded-xl max-h-36 overflow-y-auto whitespace-pre-wrap text-gray-700 leading-relaxed">{{ llmText }}</div>
              </div>

              <!-- Result images card -->
              <div v-if="resultImages.length" class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6">
                <div class="text-base font-bold text-gray-700 mb-3">🖼️ 结果</div>
                <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2 justify-items-center">
                  <img v-for="(img, i) in resultImages" :key="i" :src="img.url" class="w-full rounded-xl shadow-sm border border-pink-100 cursor-pointer" @click="openLb(resultImages.map(r=>({url:r.url,title:r.filename,filename:r.filename,path:r.path})), i)" />
                </div>
              </div>

              <!-- My Queue card -->
              <div v-if="myQueueItems.length" class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6">
                <div class="flex items-center justify-between mb-1">
                  <span id="my-queue-status" class="text-xs text-gray-400">{{ myQueueItems.some((i:any)=>i.status==='running') ? '⚡ 正在生成' : myQueueItems.some((i:any)=>i.status==='waiting') ? '⏳ 排队中' : '✅ 空闲' }}</span>
                </div>
                <div class="text-xs space-y-0.5">
                  <div v-for="i in myQueueItems" :key="i.id" class="flex justify-between text-gray-500">
                    <span>任务 #{{ i.id }}{{ i.position ? ' (#'+i.position+')' : '' }}</span>
                    <span>{{ ({waiting:'⏳ 等待',running:'⚡ 生成中',done:'✅ 完成',failed:'❌ 失败',cancelled:'✕ 取消'} as Record<string,string>)[i.status] || i.status }}{{ i.status==='failed' && i.error_message ? ' ' + i.error_message : '' }}</span>
                  </div>
                </div>
              </div>

              <!-- Log (hidden by default, shown on error or toggled) -->
              <div class="text-right">
                <button @click="showLog=!showLog" class="text-[10px] text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">{{ showLog ? '隐藏日志' : '📋 日志' }}</button>
              </div>
              <pre v-if="showLog" class="text-[10px] text-gray-400 bg-white/50 rounded-xl p-3 max-h-40 overflow-y-auto whitespace-pre-wrap">{{ logLines.join('\n') }}</pre>
            </div>
          </div>
        </div>

        <!-- ============ GALLERY ============ -->
        <div v-if="activeTab === 'gallery'" class="tab-page active p-4 sm:p-6"><div class="max-w-5xl mx-auto"><GalleryGrid ref="galleryRef" /><div class="h-20"></div></div></div>
        <!-- ============ FEATURED ============ -->
        <div v-if="activeTab === 'featured'" class="tab-page active p-4 sm:p-6"><div class="max-w-5xl mx-auto"><FeaturedGrid /><div class="h-20"></div></div></div>
        <!-- ============ MY WORKS ============ -->
        <div v-if="activeTab === 'myworks'" class="tab-page active p-4 sm:p-6"><div class="max-w-5xl mx-auto"><MyWorksGrid ref="myworksRef" /><div class="h-20"></div></div></div>
        <!-- ============ MORE ============ -->
        <div v-if="activeTab === 'more'" class="tab-page active p-4 sm:p-6"><div class="max-w-5xl mx-auto space-y-6">
          <h1 class="text-xl sm:text-2xl font-bold text-gray-800">⚙️ 更多</h1>
          <!-- 公告 -->
          <div v-if="annTitle" class="bg-pink-50 border border-pink-200 rounded-2xl p-4 text-sm text-pink-700">
            <div class="font-semibold">{{ annTitle }}</div>
            <div class="mt-1 text-xs whitespace-pre-wrap">{{ annContent }}</div>
          </div>
          <!-- GPU -->
          <GPUBar />
          <!-- 常用链接 -->
          <div class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6">
            <h2 class="text-base font-semibold mb-3 text-gray-700">🔗 常用链接</h2>
            <div class="flex flex-col gap-2 text-sm">
              <a href="https://2x.nz/posts/ai-wife" target="_blank" rel="noopener" class="text-pink-500 hover:text-pink-600 hover:underline transition-colors">📖 新手教程：从零开始造老婆</a>
              <a href="https://www.downloadmost.com/NoobAI-XL/danbooru-artist/" target="_blank" rel="noopener" class="text-pink-500 hover:text-pink-600 hover:underline transition-colors">🎨 danbooru-artist 画师库</a>
              <a href="https://www.downloadmost.com/NoobAI-XL/danbooru-character/" target="_blank" rel="noopener" class="text-pink-500 hover:text-pink-600 hover:underline transition-colors">👤 danbooru-character 角色库</a>
            </div>
          </div>
          <!-- 免责声明 -->
          <div class="bg-white/75 backdrop-blur-md border border-pink-100 rounded-3xl shadow-lg shadow-pink-100/30 p-5 sm:p-6">
            <h2 class="text-base font-semibold mb-3 text-gray-700">免责声明</h2>
            <div class="text-sm text-gray-600 leading-relaxed space-y-2">
              <p>使用本站服务即表示您同意：</p>
              <ul class="list-disc list-inside space-y-1">
                <li>本站通过 GitHub OAuth 或邮箱注册登录，<strong>仅获取您的用户名、用户ID及邮箱信息</strong>，仅用于账户识别与违规追溯，不用于其他用途</li>
                <li>您的 <strong>IP 地址将被记录</strong>，违规行为将被追溯</li>
                <li>您应对自己生成的图片内容承担<strong>全部法律责任</strong></li>
                <li>请遵守当地法律法规，<strong>不得生成违法、侵权或不当内容</strong></li>
                <li>您的作品<strong>仅自己可见</strong>，本站不会擅自公开</li>
                <li>本站有权<strong>保留违规用户的相关证据</strong>（IP、用户名、邮箱、违规内容）以保护自身合法权益</li>
                <li>本站为个人非商业项目，不提供可用性保证</li>
                <li>本站将尽力保护您的数据安全，但因不可抗力、第三方攻击或法律要求导致的数据泄露，不承担责任</li>
                <li>本站保留对违规用户进行<strong>封禁</strong>的权利</li>
              </ul>
              <p class="text-xs text-gray-500 mt-2">完整条款请查看 <a href="/privacy" target="_blank" class="text-pink-500 hover:text-pink-600 underline">用户协议与隐私政策</a></p>
            </div>
          </div>
          <!-- 来源声明 -->
          <div class="text-center text-xs text-gray-400 py-2">
            Powered by <a href="https://github.com/afoim/natureDrawImage" target="_blank" rel="noopener" class="text-gray-500 hover:text-gray-700 underline">natureDrawImage</a> (AGPLv3) | Modified by vrc-man since 2026-05 | <a href="https://github.com/vrc-man/natureDrawImage" target="_blank" rel="noopener" class="text-gray-500 hover:text-gray-700 underline">源码</a>
          </div>
        </div></div>
      </div>

      <!-- ============ TAB BAR ============ -->
      <div id="tab-bar">
        <button v-for="tab in tabs" :key="tab.key" :class="['cursor-pointer border-0 bg-transparent', {active: activeTab === tab.key}]" @click="activeTab = tab.key">
          <span class="tab-icon">{{ tab.icon }}</span>
          <span>{{ tab.label }}</span>
        </button>
      </div>

      <!-- ============ LIGHTBOX ============ -->
      <Lightbox />

      <!-- ============ GEN NOTICE MODAL ============ -->
      <Teleport to="body">
        <div v-if="showGenNoticeModal" class="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.self="cancelGenNotice">
          <div class="bg-white/95 backdrop-blur-xl border border-pink-100 rounded-3xl shadow-2xl shadow-pink-100/40 max-w-md w-full p-5 max-h-[90vh] overflow-y-auto">
            <h3 class="text-lg font-bold mb-3 text-red-500">⚠️ 生图前必读公告</h3>
            <div class="text-sm text-gray-700 leading-relaxed space-y-2 mb-4">
              <p>您了解并已知晓自己即将进行生图操作，<strong>您的 IP 将会被记录</strong>。</p>
              <p><strong>严禁生成未成年色情、成人露骨及其他违法内容</strong>，后果自负。</p>
              <p>若您恶意生图、滥用 API、生成违规内容，<strong>有可能会遭到封禁</strong>。</p>
              <p>本站<strong>有权随时将您永久禁止生图</strong>，并移除您的所有违规图片。</p>
              <p class="text-xs text-gray-500">本站有权保留违规证据（IP、用户名、邮箱、违规内容）。</p>
              <p class="text-xs text-gray-500">若用户违规行为引发法律问题，本站有义务配合执法机关提供相关证据。</p>
              <p class="text-xs text-gray-400">该弹窗仅在本次会话首次生图时提示。</p>
            </div>
            <div class="flex gap-2 justify-end">
              <button @click="cancelGenNotice" class="px-4 py-2 bg-gray-100 rounded-xl hover:bg-gray-200 text-sm text-gray-600 transition-all cursor-pointer border-0">退出</button>
              <button @click="acceptGenNotice" class="px-4 py-2 bg-red-500 text-white rounded-xl hover:bg-red-600 text-sm font-medium transition-all cursor-pointer border-0">我已知悉，继续生图</button>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- ============ SETTINGS MODAL ============ -->
      <Teleport to="body">
        <div v-if="settingsOpen" class="fixed inset-0 z-[65] bg-black/30 backdrop-blur-sm flex items-start justify-center py-8" @click.self="closeSettings">
          <div class="mx-4 w-full sm:max-w-2xl bg-white/95 backdrop-blur-xl border border-pink-100 rounded-3xl shadow-2xl shadow-pink-100/40 max-h-[85vh] overflow-y-auto p-5" @click.stop>
            <!-- === MAIN SETTINGS === -->
            <template v-if="settingsView === 'main'">
              <div class="flex items-center gap-3 pb-3 border-b border-pink-100">
                <div class="shrink-0">
                  <img v-if="userStore.currentUser?.avatar_url" :src="userStore.currentUser.avatar_url" class="w-10 h-10 rounded-full" />
                  <span v-else class="w-10 h-10 rounded-full bg-pink-100 flex items-center justify-center text-lg">{{ (userStore.currentUser?.login || '?')[0] }}</span>
                </div>
                <div class="min-w-0">
                  <div class="font-bold text-gray-700">{{ userStore.currentUser?.login }}</div>
                  <div class="text-xs text-gray-400 truncate">{{ userStore.currentUser?.email || '' }}</div>
                </div>
              </div>
              <div v-if="keyInfoHtml" id="settings-key-info" class="text-sm bg-gray-50 rounded-xl px-4 py-3 text-gray-600 mt-2" v-html="keyInfoHtml"></div>
              <div class="pt-1 space-y-1">
                <label class="flex items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-pink-50 cursor-pointer transition-all select-none">
                  <input type="checkbox" :checked="doneNotify" @change="saveDoneNotify(($event.target as HTMLInputElement).checked)" class="w-4 h-4 accent-pink-500 shrink-0" />
                  <span class="text-sm text-gray-600">🔔 任务完成提醒</span>
                </label>
                <label class="flex items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-pink-50 cursor-pointer transition-all select-none">
                  <input type="checkbox" :checked="soundNotify" @change="saveSoundNotify(($event.target as HTMLInputElement).checked);if(soundNotify)sound.play('done')" class="w-4 h-4 accent-pink-500 shrink-0" />
                  <span class="text-sm text-gray-600">🔊 声音提示</span>
                </label>
                <div v-if="soundNotify" class="space-y-1 pt-1 px-3">
                  <div v-for="s in [{type:'done',icon:'✅'},{type:'error',icon:'❌'},{type:'queued',icon:'⏳'}]" :key="s.type" class="flex items-center justify-between text-xs text-gray-400">
                    <span>{{ s.icon }} <span :id="'sound-name-'+s.type">{{ loadCustomSound(s.type).name || '未设置' }}</span></span>
                    <div class="flex gap-2 shrink-0">
                      <button @click="handleSoundUpload(s.type)" class="text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">选择音频</button>
                      <button @click="resetCustomSound(s.type)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">重置</button>
                    </div>
                  </div>
                  <div class="flex items-center gap-2 pb-2 text-xs text-gray-400">
                    <span class="shrink-0">音量</span>
                    <input type="range" min="0" max="100" :value="Math.round(soundVol*100)" @input="saveSoundVol(parseInt(($event.target as HTMLInputElement).value)/100)" @change="sound.play('done')" class="flex-1 accent-pink-500 h-1 cursor-pointer" />
                    <span class="shrink-0 w-8 text-right">{{ Math.round(soundVol*100) }}%</span>
                  </div>
                </div>
                <!-- UI 缩放 -->
                <div class="px-3 py-2">
                  <div class="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span>🔍 界面缩放</span>
                    <span>{{ Math.round(uiZoom * 100) }}%</span>
                  </div>
                  <input type="range" min="70" max="130" step="5" :value="Math.round(uiZoom * 100)" @input="setUiZoom(parseInt(($event.target as HTMLInputElement).value)/100)" class="w-full accent-pink-500 h-1 cursor-pointer" />
                </div>
                <!-- 布局密度 -->
                <label class="flex items-center justify-between px-3 py-2.5 rounded-xl hover:bg-pink-50 cursor-pointer transition-all select-none">
                  <span class="text-sm text-gray-600">📏 紧凑布局</span>
                  <input type="checkbox" :checked="compactLayout" @change="setCompactLayout(($event.target as HTMLInputElement).checked)" class="w-4 h-4 accent-pink-500 shrink-0" />
                </label>
                <button v-if="userStore.currentUser?.is_email_user" @click="settingsView='totp'" class="w-full text-left flex items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-pink-50 text-sm text-pink-500 transition-all cursor-pointer border-0 bg-transparent">🔐 两步验证</button>
                <button v-if="userStore.currentUser?.is_email_user" @click="settingsView='password'" class="w-full text-left flex items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-pink-50 text-sm text-pink-500 transition-all cursor-pointer border-0 bg-transparent">🔑 更改密码</button>
                <button @click="logout" class="w-full text-left flex items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-red-50 text-sm text-red-500 transition-all cursor-pointer border-0 bg-transparent">🚪 退出登录</button>
              </div>
            </template>

            <!-- === TOTP SETTINGS === -->
            <template v-if="settingsView === 'totp'">
              <TotpSettings @back="settingsView='main'" />
            </template>

            <!-- === PASSWORD CHANGE === -->
            <template v-if="settingsView === 'password'">
              <div class="flex items-center gap-2 pb-3 border-b border-pink-100">
                <button @click="settingsView='main'" class="text-lg text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">&larr;</button>
                <h3 class="text-base font-bold text-gray-700">🔑 更改密码</h3>
              </div>
              <div class="space-y-3 pt-2">
                <input v-model="cpOld" type="password" placeholder="当前密码" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none transition-all box-border" />
                <input v-model="cpNew" type="password" placeholder="新密码（至少6位）" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none transition-all box-border" />
                <input v-model="cpConfirm" type="password" placeholder="确认新密码" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none transition-all box-border" />
                <button @click="changePassword" class="w-full py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-sm font-semibold transition-all cursor-pointer border-0">保存</button>
                <span class="text-xs block text-center min-h-[18px]" :class="cpStatus.includes('✅')?'text-green-500':'text-red-400'">{{ cpStatus }}</span>
              </div>
            </template>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>
