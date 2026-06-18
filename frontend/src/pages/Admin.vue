<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiRaw } from '@/api/client'

const isAdmin = ref(false)
const loading = ref(true)
const activeSection = ref<string | null>(null)

const sections = [
  { key: 'queue', icon: '📊', label: '队列管理' },
  { key: 'ann', icon: '📢', label: '公告管理' },
  { key: 'res', icon: '📐', label: '分辨率' },
  { key: 'styles', icon: '🎨', label: '画风管理' },
  { key: 'characters', icon: '🎭', label: '角色管理' },
  { key: 'wfmeta', icon: '📋', label: '工作流元数据' },
  { key: 'llm', icon: '🤖', label: 'LLM 配置' },
  { key: 'limits', icon: '⏱️', label: '限流配置' },
  { key: 'maint', icon: '🔧', label: '维护模式' },
  { key: 'chead', icon: '🧩', label: '自定义 Head' },
  { key: 'bans', icon: '🚫', label: 'IP 封禁' },
  { key: 'users', icon: '👥', label: '用户管理' },
  { key: 'email', icon: '📧', label: '邮箱管理' },
  { key: 'keys', icon: '🔑', label: '访问密钥' },
  { key: 'genlogs', icon: '📝', label: '生图日志' },
  { key: 'dellog', icon: '🗑️', label: '删除记录' },
  { key: 'reports', icon: '📮', label: '举报管理' },
  { key: 'featured', icon: '✨', label: '精选管理' },
  { key: 'recent', icon: '🕐', label: '最近生图' },
  { key: 'images', icon: '🖼️', label: '图片管理' },
  { key: 'gc', icon: '🧹', label: 'GC 系统' },
  { key: 'access', icon: '🔓', label: '入口配置' },
]

onMounted(async () => {
  try { const d = await api<any>('GET', '/api/admin/whoami'); isAdmin.value = d.is_admin } catch { isAdmin.value = false }
  loading.value = false
})

let _autoTimers: ReturnType<typeof setInterval>[] = []

function stopAutoRefresh() {
  _autoTimers.forEach(t => clearInterval(t))
  _autoTimers = []
}

function startAutoRefresh(key: string) {
  stopAutoRefresh()
  const intervals: Record<string, number> = { queue: 3, genlogs: 30, recent: 30, gc: 30, email: 30, dellog: 10 }
  const sec = intervals[key]
  if (!sec) return
  const t = setInterval(() => {
    if (key === 'queue') loadQueue()
    else if (key === 'genlogs') loadGenLogs(false)
    else if (key === 'recent') loadRecent(false)
    else if (key === 'gc') { loadGcStats(); loadGcLogs(false) }
    else if (key === 'email') loadEmailAuth()
    else if (key === 'dellog') loadDeletionLog(false)
  }, sec * 1000)
  _autoTimers.push(t)
}

function toggle(key: string) {
  stopAutoRefresh()
  activeSection.value = activeSection.value === key ? null : key
  if (key === 'queue') loadQueue()
  if (key === 'bans') loadBans()
  if (key === 'users') loadUsers()
  if (key === 'featured') loadFeatured()
  if (key === 'keys') loadAccessKeys()
  if (key === 'reports') loadReports()
  if (key === 'queue') loadQueue()
  if (key === 'ann') { loadAnn() }
  if (key === 'res') loadRes()
  if (key === 'styles') loadAdminStyles()
  if (key === 'characters') loadAdminCharacters()
  if (key === 'wfmeta') loadWfMeta()
  if (key === 'llm') loadLlm()
  if (key === 'limits') loadLimits()
  if (key === 'maint') loadMaint()
  if (key === 'chead') loadChead()
  if (key === 'email') { loadQueue(); loadEmailAuth() }
  if (key === 'genlogs') loadGenLogs(true)
  if (key === 'recent') loadRecent(true)
  if (key === 'gc') { loadGcStats(); loadGcLogs(true) }
  if (key === 'images') loadImages(true)
  if (key === 'dellog') loadDeletionLog(true)
  if (key === 'access') loadAccessConfig()
  if (key === 'reports') loadReports()
  if (activeSection.value) startAutoRefresh(key)
}

// ===== API helper =====
async function fetchJSON(url: string, method = 'GET', body?: any) {
  const opts: RequestInit = { method, headers: {} }
  if (body) { opts.headers = { 'Content-Type': 'application/json' }; opts.body = JSON.stringify(body) }
  const r = await fetch(url, opts)
  if (!r.ok) { const d = await r.json().catch(()=>({})); throw new Error(d.detail || `HTTP ${r.status}`) }
  return r.json()
}

// ===== Queue =====
const queueData = ref<any>({})
const onlineList = ref<any[]>([])
async function loadQueue() {
  try { queueData.value = await fetchJSON('/api/admin/queue'); onlineList.value = queueData.value?.online_users || [] } catch {}
}
async function cancelItem(id: number) { await fetchJSON('/api/admin/queue/cancel', 'POST', { item_id: id }); loadQueue() }
async function forceUnlock() { if (!confirm('强制解锁？')) return; await fetchJSON('/api/admin/queue/force-unlock', 'POST'); loadQueue() }

// ===== Announcement =====
const annTitle = ref(''), annContent = ref(''), annEnabled = ref(false)
async function loadAnn() { try { const d = await fetchJSON('/api/admin/announcement'); if (d?.announcement) { annTitle.value = d.announcement.title || ''; annContent.value = d.announcement.content || ''; annEnabled.value = d.announcement.enabled || false } } catch {} }
async function saveAnn() { await fetchJSON('/api/admin/announcement', 'POST', { announcement: { title: annTitle.value, content: annContent.value, enabled: annEnabled.value } }); alert('已保存') }

// ===== Resolutions =====
const adminRes = ref<any[]>([])
let resTimer: any = null
async function loadRes() { try { adminRes.value = (await fetchJSON('/api/admin/resolutions')).presets || [] } catch {} }
async function saveRes() { await fetchJSON('/api/admin/resolutions', 'POST', { presets: adminRes.value }); loadRes() }
function autoSaveRes() { window.clearTimeout(resTimer); resTimer = window.setTimeout(saveRes, 800) }
function addRes() { adminRes.value.push({ w: 512, h: 512, label: '' }); autoSaveRes() }
function delRes(i: number) { adminRes.value.splice(i, 1); autoSaveRes() }
function moveRes(i: number, dir: number) { const j = i + dir; if (j < 0 || j >= adminRes.value.length) return; [adminRes.value[i], adminRes.value[j]] = [adminRes.value[j], adminRes.value[i]]; autoSaveRes() }

// ===== Styles & Characters =====
const adminStyles = ref<any[]>([])
const adminCharacters = ref<any[]>([])
let stylesTimer: any = null, charsTimer: any = null
async function loadAdminStyles() { try { adminStyles.value = (await fetchJSON('/api/admin/styles')).styles || [] } catch {} }
async function loadAdminCharacters() { try { adminCharacters.value = (await fetchJSON('/api/admin/characters')).characters || [] } catch {} }
async function saveStyles() { await fetchJSON('/api/admin/styles', 'POST', { styles: adminStyles.value }); loadAdminStyles() }
async function saveCharacters() { await fetchJSON('/api/admin/characters', 'POST', { characters: adminCharacters.value }); loadAdminCharacters() }
function addStyle() { adminStyles.value.push({ name: '', tags: '', thumb: '' }); debounceStyles() }
function debounceStyles() { window.clearTimeout(stylesTimer); stylesTimer = window.setTimeout(saveStyles, 800) }
function moveStyle(i: number, dir: number) { const j = i + dir; if (j < 0 || j >= adminStyles.value.length) return; [adminStyles.value[i], adminStyles.value[j]] = [adminStyles.value[j], adminStyles.value[i]]; saveStyles() }
function addChar() { adminCharacters.value.push({ name: '', tags: '', thumb: '', category: '' }); debounceChars() }
function debounceChars() { window.clearTimeout(charsTimer); charsTimer = window.setTimeout(saveCharacters, 800) }
function moveChar(i: number, dir: number) { const j = i + dir; if (j < 0 || j >= adminCharacters.value.length) return; [adminCharacters.value[i], adminCharacters.value[j]] = [adminCharacters.value[j], adminCharacters.value[i]]; saveCharacters() }
async function scanThumbnails(type: string) { try { await fetchJSON('/api/admin/scan-thumbnails', 'POST', { type }); alert('缩略图扫描完成'); type === 'styles' ? loadAdminStyles() : loadAdminCharacters() } catch (e: any) { alert('扫描失败: ' + e.message) } }
async function uploadStyleThumb(idx: number) {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'
  inp.onchange = async () => {
    const f = inp.files![0]; if (!f) return
    const fd = new FormData(); fd.append('file', f)
    const r = await fetch('/api/admin/style_thumbnail?name=' + encodeURIComponent(adminStyles.value[idx].name), { method: 'POST', body: fd })
    if (r.ok) loadAdminStyles()
  }
  inp.click()
}
async function uploadCharThumb(idx: number) {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'
  inp.onchange = async () => {
    const f = inp.files![0]; if (!f) return
    const fd = new FormData(); fd.append('file', f)
    const r = await fetch('/api/admin/character_thumbnail?name=' + encodeURIComponent(adminCharacters.value[idx].name), { method: 'POST', body: fd })
    if (r.ok) loadAdminCharacters()
  }
  inp.click()
}

// ===== Workflow Metadata =====
const adminWfMeta = ref<any[]>([])
const wfCategories = ref<string[]>([])
async function loadWfMeta() { try { adminWfMeta.value = (await fetchJSON('/api/admin/workflow_meta')).meta || []; wfCategories.value = (await fetchJSON('/api/admin/workflow_meta')).categories || [] } catch {} }
async function saveWfMeta() { await fetchJSON('/api/admin/workflow_meta', 'POST', { meta: adminWfMeta.value, categories: wfCategories.value }) }
function addWfCat() { const v = prompt('分类名称：'); if (v && !wfCategories.value.includes(v)) { wfCategories.value.push(v); saveWfMeta() } }

// ===== LLM =====
const llmConfig = ref<any>({ provider: 'local', local_endpoint: '', google_api_key: '', custom_endpoint: '', custom_api_key: '', custom_model: '' })
const llmTestResult = ref('')
const llmModels = ref<string[]>([])
async function loadLlm() { try { const d = await fetchJSON('/api/admin/llm'); llmConfig.value = d.llm || d } catch {} }
async function saveLlm() { await fetchJSON('/api/admin/llm', 'POST', { llm: llmConfig.value }); alert('已保存') }
async function testLlm() { llmTestResult.value = '测试中...'; try { const d = await fetchJSON('/api/admin/llm/test', 'POST', { llm: llmConfig.value }); llmTestResult.value = d.reply || d.result || '连接成功' } catch (e: any) { llmTestResult.value = e.message } }
async function detectModels() { try { const d = await fetchJSON('/api/admin/llm/models', 'POST', { llm: llmConfig.value }); llmModels.value = (d.models || []).map((m: any) => m.id || m) } catch (e: any) { llmModels.value = [e.message] } }

// ===== Limits =====
const limits = ref<any>({})
async function loadLimits() { try { limits.value = await fetchJSON('/api/admin/limits') } catch {} }
async function saveLimits() { await fetchJSON('/api/admin/limits', 'POST', limits.value); alert('已保存') }

// ===== Bans =====
const bans = ref<any[]>([]), whitelist = ref<any[]>([])
const banInput = ref(''), wlInput = ref('')
async function loadBans() {
  try { bans.value = (await fetchJSON('/api/admin/bans')).banned || []; whitelist.value = (await fetchJSON('/api/admin/ip-whitelist')).whitelist || [] } catch {}
}
async function banIP() { if (!banInput.value.trim()) return; await fetchJSON('/api/admin/ban', 'POST', { ip: banInput.value.trim() }); banInput.value = ''; loadBans() }
async function unbanIP(ip: string) { if (!confirm(`解封 ${ip}?`)) return; await fetchJSON('/api/admin/unban', 'POST', { ip }); loadBans() }
async function addWL() { if (!wlInput.value.trim()) return; if (prompt(`确认添加 ${wlInput.value.trim()}? 输入"确认添加"`) !== '确认添加') return; await fetchJSON('/api/admin/ip-whitelist/add', 'POST', { ip: wlInput.value.trim() }); wlInput.value = ''; loadBans() }
async function removeWL(ip: string) { if (!confirm(`移除白名单 ${ip}?`)) return; await fetchJSON('/api/admin/ip-whitelist/remove', 'POST', { ip }); loadBans() }

// ===== Users =====
const users = ref<any[]>([])
async function loadUsers() { try { users.value = (await fetchJSON('/api/admin/users')).users || [] } catch {} }
async function toggleBan(githubId: string, banned: boolean) {
  const action = banned ? '解封' : '封禁'
  if (!confirm(`确定${action}用户 ${githubId} ？`)) return
  if (prompt(`输入"确认${action}"`) !== `确认${action}`) return
  await fetchJSON(`/api/admin/users/${banned ? 'unban' : 'ban'}`, 'POST', { github_id: githubId }); loadUsers()
}

// ===== Features =====
let dragFeaturedIdx = -1
const featured = ref<any[]>([])
async function reorderFeatured(to: number, from: number) {
  if (to === from || to < 0 || from < 0) return
  const item = featured.value.splice(from, 1)[0]
  featured.value.splice(to, 0, item)
  try { await fetchJSON('/api/admin/featured/reorder', 'POST', { items: featured.value.map((i: any) => i.path || i) }) } catch {}
}
async function loadFeatured() { try { const d = await fetchJSON('/api/admin/featured'); featured.value = (d.items || []).map((p: any) => typeof p === 'string' ? { path: p } : p) } catch {} }
async function removeFeatured(path: string) { await fetchJSON('/api/admin/featured/remove', 'POST', { path }); loadFeatured() }

// ===== Access Keys =====
const accessKeys = ref<any[]>([])
async function loadAccessKeys() { try { accessKeys.value = (await fetchJSON('/api/admin/access-keys')).items || [] } catch {} }
async function genKeys() {
  const type = prompt('密钥类型：normal(普通) / time(按时间) / count(按次数) / both(时间+次数)', 'normal') || 'normal'
  if (!['normal','time','count','both'].includes(type)) return
  const count = parseInt(prompt('生成数量？', '1') || '1')
  if (!count || count < 1) return
  const extra: any = {}
  if (type === 'time' || type === 'both') {
    extra.days = parseInt(prompt('有效期（天）：', '30') || '30')
    extra.hours = 0
    extra.mins = 0
  }
  if (type === 'count' || type === 'both') {
    const maxUses = parseInt(prompt('最大使用次数：', '100') || '100')
    extra.max_uses = maxUses
  }
  try {
    const d = await fetchJSON('/api/admin/access-keys/generate', 'POST', { count, type, ...extra })
    const keys = d.items || d.keys || []
    if (keys.length > 0) {
      const txt = keys.map((k: any) => k.full_key || k.key || k).join('\n')
      await navigator.clipboard.writeText(txt)
      alert(`生成了 ${keys.length} 个密钥，已复制到剪贴板`)
    } else { alert('生成失败：未返回密钥') }
    loadAccessKeys()
  } catch (e: any) { alert(e.message) }
}
async function delKey(k: string) { if (!confirm('禁用此密钥？')) return; await fetchJSON('/api/admin/access-keys/delete', 'POST', { key: k }); loadAccessKeys() }
async function enableKey(k: string) { await fetchJSON('/api/admin/access-keys/enable', 'POST', { key: k }); loadAccessKeys() }
async function removeKey(k: string) { if (!confirm('彻底删除此密钥？不可恢复！')) return; if (prompt('输入"确认删除"') !== '确认删除') return; await fetchJSON('/api/admin/access-keys/remove', 'POST', { key: k }); loadAccessKeys() }
async function cleanupKeys() { if (!confirm('清理所有过期/耗尽/禁用的密钥？')) return; await fetchJSON('/api/admin/access-keys/cleanup', 'POST'); loadAccessKeys() }
function keyStatusBadge(k: any): string {
  if (k.expires_at && Date.now() > k.expires_at * 1000) return '<span class="text-red-500">已过期</span>'
  if (k.max_uses && k.used_count >= k.max_uses) return '<span class="text-amber-500">次数用尽</span>'
  if (k.disabled_at) return '<span class="text-gray-400">已禁用</span>'
  return '<span class="text-green-500">可用</span>'
}
function keyTypeLabel(k: any): string {
  if (k.expires_at && k.max_uses) return '时间+次数'
  if (k.expires_at) return '按时间'
  if (k.max_uses) return '按次数'
  return '基础版'
}

// ===== Gen Logs =====
const genLogs = ref<any[]>([])
const glPage = ref(0), glTotal = ref(0)
const glQ = ref('')
const glDateFrom = ref(''), glDateTo = ref('')
const glEditMode = ref(false)
const glSelected = ref<Set<string>>(new Set())
async function loadGenLogs(reset = false) {
  if (reset) { glPage.value = 0; glSelected.value = new Set() }
  try {
    let url = `/api/admin/gen-logs?offset=${glPage.value * 24}&limit=24`
    if (glQ.value) url += '&login=' + encodeURIComponent(glQ.value)
    if (glDateFrom.value) url += '&date_from=' + encodeURIComponent(new Date(glDateFrom.value).getTime() / 1000)
    if (glDateTo.value) url += '&date_to=' + encodeURIComponent(new Date(glDateTo.value).setHours(23,59,59) / 1000)
    const d = await fetchJSON(url); genLogs.value = d.items || []; glTotal.value = d.total || 0
  } catch {}
}
function glToggleSelect(id: string) {
  const s = new Set(glSelected.value)
  s.has(id) ? s.delete(id) : s.add(id)
  glSelected.value = s
}
function glSelectAll() {
  glSelected.value = new Set(genLogs.value.map((g: any) => g.id ?? g.log_id))
}
async function glDeleteSelected() {
  if (!glSelected.value.size) return
  if (!confirm(`删除 ${glSelected.value.size} 条日志？`)) return
  try { await fetchJSON('/api/admin/gen-logs/delete', 'POST', { ids: Array.from(glSelected.value) }); loadGenLogs(true) } catch {}
}

// ===== Deletion Log =====
const delLog = ref<any[]>([]), delPage = ref(0), delTotal = ref(0)
const delDateFrom = ref(''), delDateTo = ref('')
const delEditMode = ref(false)
const delSelected = ref<Set<string>>(new Set())
async function loadDeletionLog(reset = false) {
  if (reset) { delPage.value = 0; delSelected.value = new Set() }
  try {
    let url = `/api/admin/deletion-log?offset=${delPage.value * 24}&limit=24`
    if (delDateFrom.value) url += '&date_from=' + encodeURIComponent(new Date(delDateFrom.value).getTime() / 1000)
    if (delDateTo.value) url += '&date_to=' + encodeURIComponent(new Date(delDateTo.value).setHours(23,59,59) / 1000)
    const d = await fetchJSON(url); delLog.value = d.items || []; delTotal.value = d.total || 0
  } catch {}
}
function delToggleSelect(path: string) {
  const s = new Set(delSelected.value); s.has(path) ? s.delete(path) : s.add(path); delSelected.value = s
}
async function delClearSingle(path: string) {
  if (!confirm(`清理记录 ${path}?`)) return
  try { await fetchJSON('/api/admin/deletion-log/clear', 'POST', { paths: [path] }); loadDeletionLog(false) } catch {}
}
async function delClearSelected() {
  if (!delSelected.value.size) return
  if (!confirm(`清理 ${delSelected.value.size} 条记录？`)) return
  try { await fetchJSON('/api/admin/deletion-log/clear', 'POST', { paths: Array.from(delSelected.value) }); loadDeletionLog(true) } catch {}
}

// ===== Reports =====
const reports = ref<any[]>([])
async function loadReports() { try { reports.value = (await fetchJSON('/api/admin/reports')).reports || [] } catch {} }
async function resolveReport(id: number, action: string) {
  const actMap: Record<string, string> = { ignore: 'dismiss', delete: 'delete', ban_creator: 'ban_creator', ban_reporter: 'ban_reporter' }
  await fetchJSON('/api/admin/report/resolve', 'POST', { report_id: id, action: actMap[action] || action }); loadReports()
}

// ===== Recent =====
const recentImages = ref<any[]>([]), recentPage = ref(0), recentTotal = ref(0)
async function loadRecent(reset = false) {
  if (reset) recentPage.value = 0
  try { const d = await fetchJSON(`/api/admin/recent?offset=${recentPage.value * 30}&limit=30`); recentImages.value = d.items || []; recentTotal.value = d.total || 0 } catch {}
}
async function delRecentImage(path: string) { await fetchJSON('/api/admin/delete', 'POST', { path }); loadRecent(false) }
async function banIPFromRecent(ip: string) { if (!ip || !confirm(`封禁 IP ${ip}?`)) return; await fetchJSON('/api/admin/ban', 'POST', { ip }); }
async function addFeaturedFromRecent(path: string) { try { await fetchJSON('/api/admin/featured/add', 'POST', { path }); loadFeatured() } catch {} }

// ===== Images =====
const adminImages = ref<any[]>([]), imgPage = ref(0), imgTotal = ref(0), imgSelected = ref<Set<string>>(new Set())
async function loadImages(reset = false) {
  if (reset) { imgPage.value = 0; imgSelected.value = new Set() }
  try { const d = await fetchJSON(`/api/admin/images?offset=${imgPage.value * 30}&limit=30`); adminImages.value = (d.items || []).map((i: any) => i.path || i); imgTotal.value = d.total || 0 } catch {}
}
async function batchDeleteImages() {
  if (!imgSelected.value.size) return
  if (!confirm(`删除 ${imgSelected.value.size} 张图片？`)) return
  await fetchJSON('/api/admin/mark_delete_batch', 'POST', { paths: Array.from(imgSelected.value) })
  imgSelected.value = new Set(); loadImages(true)
}

// ===== GC =====
const gcStats = ref<any>({}), gcLogs = ref<any[]>([]), gcPage = ref(0), gcTotal = ref(0)
const gcDateFrom = ref(''), gcDateTo = ref('')
async function loadGcStats() { try { gcStats.value = await fetchJSON('/api/admin/gc/stats') } catch {} }
async function loadGcLogs(reset = false) {
  if (reset) { gcPage.value = 0; gcDateFrom.value = ''; gcDateTo.value = '' }
  try {
    let url = `/api/admin/gc/logs?offset=${gcPage.value * 20}&limit=20`
    if (gcDateFrom.value) url += '&date_from=' + encodeURIComponent(new Date(gcDateFrom.value).getTime() / 1000)
    if (gcDateTo.value) url += '&date_to=' + encodeURIComponent(new Date(gcDateTo.value).setHours(23,59,59) / 1000)
    const d = await fetchJSON(url); gcLogs.value = d.items || []; gcTotal.value = d.total || 0
  } catch {}
}
async function triggerGc(backup = true) { if (!confirm(`执行 GC${backup ? '(备份)' : ''}?`)) return; await fetchJSON('/api/admin/gc', 'POST', { backup }); loadGcStats(); loadGcLogs(true) }

// ===== Access Config (rate limits, email config) =====
const accessConfig = ref<any>({})
async function loadAccessConfig() { try { accessConfig.value = await fetchJSON('/api/admin/limits') } catch {} }

// ===== Generic fetch helper =====
async function fetchAn(url: string) { try { const d = await fetchJSON(url); if (d) { if (d.title !== undefined) annTitle.value = d.title; if (d.content !== undefined) annContent.value = d.content; if (d.enabled !== undefined) annEnabled.value = d.enabled } } catch {} }

// ===== Maintenance =====
const maintEnabled = ref(false)
const maintMessage = ref('')
async function loadMaint() { try { const d = await fetchJSON('/api/admin/maintenance'); const c = d.config || d; maintEnabled.value = c.enabled || false; maintMessage.value = c.message || '' } catch {} }
async function saveMaint() { await fetchJSON('/api/admin/maintenance', 'POST', { config: { enabled: maintEnabled.value, message: maintMessage.value } }); alert('已保存') }

// ===== Custom Head =====
const cheadEnabled = ref(false)
const cheadHtml = ref('')
async function loadChead() { try { const d = await fetchJSON('/api/admin/custom_head'); const c = d.config || d; cheadEnabled.value = c.enabled || false; cheadHtml.value = c.html || '' } catch {} }
async function saveChead() { await fetchJSON('/api/admin/custom_head', 'POST', { config: { enabled: cheadEnabled.value, html: cheadHtml.value } }); alert('已保存') }

// ===== Email Management =====
const emailDashboard = ref<any>({})
const inviteCodes = ref<any[]>([])
const emailUsersList = ref<any[]>([])
const emailLogsList = ref<any[]>([])
const abuseIps = ref<any[]>([])
const rateLimits = ref<any>({})
const euPage = ref(0), euTotal = ref(0)
const elPage = ref(0), elTotal = ref(0)
const elSearch = ref('')
const elDateFrom = ref(''), elDateTo = ref('')
const elSelected = ref<Set<string>>(new Set())
const elEditMode = ref(false)

async function loadEmailAuth() {
  try { emailDashboard.value = await fetchJSON('/api/admin/email-dashboard') } catch {}
  try {
    const dash = await fetchJSON('/api/admin/email-dashboard')
    inviteCodes.value = dash.invite_codes || []
    if (dash.rate_limits) rateLimits.value = dash.rate_limits
    if (dash.limits) Object.assign(rateLimits.value, dash.limits)
    if (dash.abuse_ips) abuseIps.value = dash.abuse_ips
  } catch {}
  try { let euUrl = `/api/admin/email-users?offset=${euPage.value * 24}&limit=24`; if (euSearch.value) euUrl += '&search=' + encodeURIComponent(euSearch.value); const d = await fetchJSON(euUrl); emailUsersList.value = d.users || []; euTotal.value = d.total || 0 } catch {}
  try {
    let elUrl = `/api/admin/email-logs?offset=${elPage.value * 24}&limit=24`
    if (elSearch.value) elUrl += '&search=' + encodeURIComponent(elSearch.value)
    if (elDateFrom.value) elUrl += '&date_from=' + encodeURIComponent(elDateFrom.value)
    if (elDateTo.value) elUrl += '&date_to=' + encodeURIComponent(elDateTo.value)
    const d = await fetchJSON(elUrl); emailLogsList.value = d.logs || d.items || []; elTotal.value = d.total || 0
  } catch {}
  try { const d = await fetchJSON('/api/admin/email-abuse-ips'); abuseIps.value = d.ips || [] } catch {}
  try { rateLimits.value = await fetchJSON('/api/admin/email-config') } catch {}
}
function elToggleSelect(id: string) {
  const s = new Set(elSelected.value); s.has(id) ? s.delete(id) : s.add(id); elSelected.value = s
}
function elSelectAll() {
  elSelected.value = new Set(emailLogsList.value.map((l: any) => String(l.id ?? l.log_id)))
}
async function elDeleteSelected() {
  if (!elSelected.value.size) return
  if (!confirm(`删除 ${elSelected.value.size} 条日志？`)) return
  try { await fetchJSON('/api/admin/email-logs/clear', 'POST', { ids: Array.from(elSelected.value) }); loadEmailAuth() } catch {}
}
async function genInviteCode() {
  try { const d = await fetchJSON('/api/admin/invite-codes/generate', 'POST', { count: 1 }); alert(`生成成功: ${d.code || d.codes?.[0] || ''}`); loadEmailAuth() } catch (e: any) { alert(e.message) }
}
async function delInviteCode(code: string) { if (!confirm('删除邀请码？')) return; await fetchJSON('/api/admin/invite-codes/delete', 'POST', { code }); loadEmailAuth() }
async function toggleEmailBan(githubId: string, banned: boolean) {
  const action = banned ? '解封' : '封禁'
  if (!confirm(`确定${action}用户？`)) return
  await fetchJSON(`/api/admin/email-users/${banned ? 'unban' : 'ban'}`, 'POST', { github_id: githubId }); loadEmailAuth()
}
async function resetTotp(githubId: string) { await fetchJSON('/api/admin/email-users/reset-totp', 'POST', { github_id: githubId }); alert('TOTP 已重置') }
async function resendVerify(githubId: string) { await fetchJSON('/api/admin/email-users/resend-verify', 'POST', { github_id: githubId }); alert('验证邮件已发送') }
async function saveRateLimits() { await fetchJSON('/api/admin/email-config', 'POST', rateLimits.value); alert('已保存') }
async function clearAbuseIps() { await fetchJSON('/api/admin/email-abuse-ips/clear', 'POST'); loadEmailAuth() }
async function removeAbuseIp(ip: string) { if (!confirm(`移除恶意 IP ${ip}?`)) return; const i = prompt('输入"确认移除"'); if (i !== '确认移除') return; await fetchJSON('/api/admin/email-abuse-ips/clear', 'POST', { ip }); loadEmailAuth() }
async function sendPasswordResetLink(githubId: string) {
  if (!confirm('确定发送密码重置链接到该用户邮箱？')) return
  try { const d = await fetchJSON('/api/admin/email-users/reset-password', 'POST', { github_id: githubId }); if (d.link) { const copy = confirm('邮件发送可能失败，是否复制重置链接？'); if (copy) copyText(d.link) } else { alert('重置链接已发送') } } catch (e: any) { alert(e.message) }
}
const sendEmailGid = ref('')
const sendEmailTo = ref('')
const sendEmailSubject = ref('')
const sendEmailBody = ref('')
const sendEmailStatus = ref('')
const euSearch = ref('')
function openSendEmailModal(email: string, gid: string) { sendEmailTo.value = email; sendEmailGid.value = gid; sendEmailSubject.value = ''; sendEmailBody.value = ''; sendEmailStatus.value = '' }
async function doSendEmail() {
  if (!sendEmailSubject.value.trim() || !sendEmailBody.value.trim()) { sendEmailStatus.value = '请填写主题和正文'; return }
  sendEmailStatus.value = '发送中...'
  try { await fetchJSON('/api/admin/email-users/send-custom-email', 'POST', { github_id: sendEmailGid.value, subject: sendEmailSubject.value, message: sendEmailBody.value }); sendEmailStatus.value = '✅ 已发送' } catch (e: any) { sendEmailStatus.value = '发送失败: ' + e.message }
}

const rateLimitLabels: Record<string, string> = {
  gen_cooldown_sec: '生图冷却(秒)', image_rate_window: '图片限流窗口(秒)', image_rate_max: '图片限流上限',
  report_window: '举报窗口(秒)', report_max: '举报上限', report_pending_min: '举报最少待处理',
  gpu_poll_interval: 'GPU轮询间隔(秒)', gpu_cache_ttl: 'GPU缓存(秒)', gc_interval_min: 'GC间隔(分钟)',
  featured_tip: '精选提示', login_max_per_email_per_min: '登录/min/邮箱',
  login_max_per_ip_per_min: '登录/min/IP', register_max_per_email_per_day: '注册/天/邮箱',
  register_max_per_ip_per_day: '注册/天/IP', register_cool_down: '注册冷却(秒)',
  email_verify_expire: '验证过期(秒)', invite_code_max_uses: '邀请码最大使用次数',
}

// ===== Restart =====
async function restartServer() {
  if (!confirm('确定强制重启？所有任务中断。')) return
  if (prompt('输入"确认重启服务"') !== '确认重启服务') return
  await fetchJSON('/api/admin/force-restart', 'POST')
}
async function gracefulRestart() {
  if (!confirm('优雅重启将等待当前任务完成后重启。确定？')) return
  if (prompt('输入"确认重启服务"') !== '确认重启服务') return
  await fetchJSON('/api/admin/graceful-restart', 'POST')
}

// ===== Copy text =====
function copyText(text: string) { navigator.clipboard.writeText(text) }
function clipText(text: string) { navigator.clipboard.writeText(text) }
function esc(s: string) { return String(s).replace(/[&<>"']/g, (c: string) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c] || c) }
</script>

<template>
  <div class="min-h-screen bg-gray-100">
    <div class="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
      <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <h1 class="text-lg font-bold text-gray-800">🛠️ 管理后台</h1>
        <div class="flex items-center gap-3">
          <a href="/" class="text-sm text-pink-500 hover:underline no-underline">← 返回首页</a>
          <button @click="restartServer" class="text-xs px-2 py-1 bg-red-50 text-red-500 rounded-lg hover:bg-red-100 transition-all cursor-pointer border-0">强制重启</button>
          <button @click="gracefulRestart" class="text-xs px-2 py-1 bg-amber-50 text-amber-600 rounded-lg hover:bg-amber-100 transition-all cursor-pointer border-0">优雅重启</button>
        </div>
      </div>
    </div>

    <div v-if="!isAdmin && !loading" class="max-w-md mx-auto mt-20 text-center p-8 bg-white rounded-2xl shadow-sm">
      <p class="text-4xl mb-4">🔒</p>
      <p class="text-gray-500">需要管理员权限</p>
    </div>

    <div v-else class="max-w-7xl mx-auto p-4">
      <div class="flex flex-wrap gap-1.5 mb-4">
        <button v-for="s in sections" :key="s.key" @click="toggle(s.key)"
          :class="['text-xs px-3 py-1.5 rounded-full transition-all cursor-pointer border-0', activeSection === s.key ? 'bg-pink-500 text-white shadow-md' : 'bg-white text-gray-600 hover:bg-pink-50 shadow-sm']">
          {{ s.icon }} {{ s.label }}
        </button>
      </div>

      <!-- QUEUE -->
      <div v-if="activeSection === 'queue'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📊 队列管理</h2>
        <!-- Current Task -->
        <div v-if="queueData.current" class="bg-amber-50 rounded-xl p-3 mb-3 text-xs">
          <div class="font-semibold text-amber-700 mb-1">⚡ 当前任务</div>
          <div class="text-amber-600 space-y-0.5">
            <div>用户：{{ queueData.current.github_id || '未知' }}</div>
            <div>工作流：{{ queueData.current.workflow || '未知' }}</div>
            <div>开始于：{{ queueData.current.started_at ? new Date(queueData.current.started_at * 1000).toLocaleTimeString() : '未知' }}</div>
            <div>IP：{{ queueData.current.client_ip || '' }}</div>
          </div>
          <button @click="cancelItem(queueData.current.id)" class="mt-1 text-red-500 hover:underline cursor-pointer border-0 bg-transparent text-xs">取消当前任务</button>
        </div>
        <!-- Queue List -->
        <div v-for="q in (queueData.queue || [])" :key="q.id" class="flex items-center justify-between py-1.5 border-b border-gray-50 text-xs text-gray-600">
          <span>#{{ q.id }} <span :class="q.status==='running'?'text-blue-500':q.status==='waiting'?'text-amber-500':q.status==='failed'?'text-red-500':'text-gray-500'">{{ q.status }}</span> {{ q.github_id }}</span>
          <button @click="cancelItem(q.id)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-xs">取消</button>
        </div>
        <!-- Online Users -->
        <div v-if="onlineList.length" class="mt-3 pt-3 border-t border-gray-100">
          <div class="text-xs font-semibold text-gray-500 mb-1">在线用户 ({{ onlineList.length }})</div>
          <div class="flex flex-wrap gap-1">
            <span v-for="u in onlineList" :key="u" class="inline-flex items-center gap-1 bg-green-50 text-green-700 px-2 py-0.5 rounded-full text-[10px]"><span class="w-1.5 h-1.5 rounded-full bg-green-500 inline-block"></span>{{ u }}</span>
          </div>
        </div>
        <div class="mt-2 flex gap-2">
          <button @click="forceUnlock" class="text-xs text-red-500 hover:underline cursor-pointer border-0 bg-transparent">强制解锁</button>
          <button @click="loadQueue" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
        </div>
      </div>

      <!-- ANNOUNCEMENT -->
      <div v-if="activeSection === 'ann'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📢 公告管理</h2>
        <input v-model="annTitle" placeholder="标题" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm mb-2 outline-none focus:border-pink-400 box-border" />
        <textarea v-model="annContent" placeholder="内容" rows="4" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm mb-2 outline-none focus:border-pink-400 box-border resize-y"></textarea>
        <button @click="saveAnn" class="px-4 py-2 bg-pink-500 text-white rounded-xl text-sm hover:bg-pink-600 transition-all cursor-pointer border-0">保存</button>
      </div>

      <!-- RESOLUTIONS -->
      <div v-if="activeSection === 'res'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📐 分辨率管理</h2>
        <div class="space-y-1 mb-3">
          <div v-for="(r, i) in adminRes" :key="i" class="flex items-center gap-2 text-xs">
            <input v-model="r.w" @input="autoSaveRes" type="number" class="w-20 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" placeholder="宽" />
            <span>×</span>
            <input v-model="r.h" @input="autoSaveRes" type="number" class="w-20 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" placeholder="高" />
            <input v-model="r.label" @input="autoSaveRes" class="flex-1 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" placeholder="标签(可选)" />
            <button @click="moveRes(i, -1)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">↑</button>
            <button @click="moveRes(i, 1)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">↓</button>
            <button @click="delRes(i)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent">✕</button>
          </div>
        </div>
        <button @click="addRes" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">+ 添加</button>
      </div>

      <!-- STYLES -->
      <div v-if="activeSection === 'styles'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🎨 画风管理</h2>
        <div class="space-y-2">
          <div v-for="(s, i) in adminStyles" :key="i" class="flex items-center gap-2 text-xs">
            <input v-model="s.name" @input="debounceStyles()" placeholder="名称" class="w-28 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" />
            <input v-model="s.tags" @input="debounceStyles()" placeholder="标签" class="flex-1 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" />
            <button @click="moveStyle(i,-1)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">↑</button>
            <button @click="moveStyle(i,1)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">↓</button>
            <button @click="uploadStyleThumb(i)" class="text-pink-400 hover:text-pink-600 cursor-pointer border-0 bg-transparent">📷</button>
            <button @click="adminStyles.splice(i,1);saveStyles()" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent">✕</button>
          </div>
        </div>
        <button @click="addStyle" class="mt-2 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">+ 添加</button>
        <button @click="scanThumbnails('styles')" class="ml-2 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">📁 扫描缩略图</button>
      </div>

      <!-- CHARACTERS -->
      <div v-if="activeSection === 'characters'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🎭 角色管理</h2>
        <div class="space-y-2">
          <div v-for="(c, i) in adminCharacters" :key="i" class="flex items-center gap-2 text-xs">
            <input v-model="c.name" @input="debounceChars()" placeholder="名称" class="w-24 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" />
            <input v-model="c.category" @input="debounceChars()" placeholder="分类" class="w-20 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" />
            <input v-model="c.tags" @input="debounceChars()" placeholder="标签" class="flex-1 border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400" />
            <button @click="moveChar(i,-1)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">↑</button>
            <button @click="moveChar(i,1)" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">↓</button>
            <button @click="uploadCharThumb(i)" class="text-pink-400 hover:text-pink-600 cursor-pointer border-0 bg-transparent">📷</button>
            <button @click="adminCharacters.splice(i,1);saveCharacters()" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent">✕</button>
          </div>
        </div>
        <button @click="addChar" class="mt-2 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">+ 添加</button>
        <button @click="scanThumbnails('characters')" class="ml-2 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">📁 扫描缩略图</button>
      </div>

      <!-- WORKFLOW META -->
      <div v-if="activeSection === 'wfmeta'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📋 工作流元数据</h2>
        <div class="flex items-center gap-2 mb-3 flex-wrap">
          <span v-for="cat in wfCategories" :key="cat" class="inline-flex items-center gap-1 bg-pink-50 text-pink-700 px-2 py-0.5 rounded-full text-xs">
            {{ cat }}
            <button @click="wfCategories = wfCategories.filter(c => c !== cat); saveWfMeta()" class="cursor-pointer border-0 bg-transparent text-pink-400 hover:text-pink-600">&times;</button>
          </span>
          <button @click="addWfCat" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">+ 分类</button>
        </div>
        <div class="text-xs text-gray-400">工作流列表</div>
        <div v-for="w in adminWfMeta" :key="w.path" class="flex items-center gap-2 py-1 text-xs text-gray-600 border-b border-gray-50">
          <span class="flex-1 truncate">{{ w.path }}</span>
          <span class="text-gray-400">{{ w.category }}</span>
        </div>
        <button @click="loadWfMeta" class="mt-2 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
      </div>

      <!-- LLM -->
      <div v-if="activeSection === 'llm'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🤖 LLM 配置</h2>
        <div class="space-y-2 text-sm">
          <label class="flex items-center gap-2"><input type="radio" v-model="llmConfig.provider" value="local" /> 本地 (LM Studio)</label>
          <label class="flex items-center gap-2"><input type="radio" v-model="llmConfig.provider" value="google" /> Google AI Studio</label>
          <label class="flex items-center gap-2"><input type="radio" v-model="llmConfig.provider" value="custom" /> 自定义 OpenAI 兼容</label>
          <div v-if="llmConfig.provider === 'local'">
            <label class="text-xs text-gray-500">本地端点：</label>
            <input v-model="llmConfig.local_endpoint" class="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400 box-border" />
          </div>
          <div v-if="llmConfig.provider === 'google'">
            <label class="text-xs text-gray-500">Google API Key：</label>
            <input v-model="llmConfig.google_api_key" type="password" class="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400 box-border" />
          </div>
          <div v-if="llmConfig.provider === 'custom'">
            <label class="text-xs text-gray-500">端点：</label>
            <input v-model="llmConfig.custom_endpoint" class="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400 box-border" />
            <label class="text-xs text-gray-500">API Key：</label>
            <input v-model="llmConfig.custom_api_key" type="password" class="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400 box-border" />
            <label class="text-xs text-gray-500">模型：</label>
            <input v-model="llmConfig.custom_model" class="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400 box-border" />
          </div>
          <div class="flex gap-2">
            <button @click="saveLlm" class="px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">保存</button>
            <button @click="testLlm" class="px-4 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs hover:bg-gray-200 cursor-pointer border-0">测试</button>
            <button @click="detectModels" class="px-4 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs hover:bg-gray-200 cursor-pointer border-0">探测模型</button>
          </div>
          <div v-if="llmTestResult" class="text-xs" :class="llmTestResult.includes('失败')?'text-red-400':'text-green-500'">{{ llmTestResult }}</div>
          <div v-if="llmModels.length" class="text-xs text-gray-500 space-y-0.5"><div v-for="m in llmModels" :key="m" class="cursor-pointer hover:text-pink-500" @click="llmConfig.custom_model = m">{{ m }}</div></div>
        </div>
      </div>

      <!-- LIMITS -->
      <div v-if="activeSection === 'limits'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">⏱️ 限流配置</h2>
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div v-for="(v, k) in limits" :key="k"><label class="text-gray-500 block mb-0.5">{{ k }}</label><input v-model="limits[k]" class="w-full border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400 box-border" /></div>
        </div>
        <button @click="saveLimits" class="mt-3 px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">保存</button>
      </div>

      <!-- BANS -->
      <div v-if="activeSection === 'bans'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🚫 IP 封禁管理</h2>
        <div class="flex gap-2 mb-3"><input v-model="banInput" @keydown.enter="banIP" placeholder="IP 地址" class="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400" /><button @click="banIP" class="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs hover:bg-red-600 cursor-pointer border-0">封禁</button></div>
        <div class="text-xs space-y-1 mb-3">
          <div v-for="b in bans" :key="b" class="flex justify-between py-1"><span>{{ b }}</span><button @click="unbanIP(b)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-xs">解封</button></div>
          <div class="text-gray-400" v-if="!bans.length">无封禁 IP</div>
        </div>
        <div class="flex gap-2 mb-3"><input v-model="wlInput" placeholder="白名单 IP" class="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-pink-400" /><button @click="addWL" class="px-3 py-1.5 bg-emerald-500 text-white rounded-lg text-xs hover:bg-emerald-600 cursor-pointer border-0">添加</button></div>
        <div class="text-xs space-y-1">
          <div v-for="ip in whitelist" :key="ip" class="flex justify-between py-1"><span>{{ ip }}</span><button @click="removeWL(ip)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-xs">移除</button></div>
        </div>
      </div>

      <!-- USERS -->
      <div v-if="activeSection === 'users'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">👥 用户管理</h2>
        <div class="text-xs space-y-1">
          <div v-for="u in users" :key="u.github_id" class="flex justify-between py-1.5 border-b border-gray-50 items-center">
            <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full inline-block" :class="u.banned?'bg-red-500':'bg-green-500'"></span>{{ u.login || u.github_id }}</span>
            <button @click="toggleBan(u.github_id, u.banned)" :class="[u.banned?'text-emerald-500':'text-red-400','hover:underline cursor-pointer border-0 bg-transparent text-xs']">{{ u.banned ? '解封' : '封禁' }}</button>
          </div>
        </div>
      </div>

      <!-- KEYS -->
      <div v-if="activeSection === 'keys'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🔑 访问密钥</h2>
        <div class="flex gap-2 mb-3">
          <button @click="genKeys" class="px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">生成密钥</button>
          <button @click="cleanupKeys" class="px-4 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs hover:bg-gray-200 cursor-pointer border-0">清理失效</button>
        </div>
        <div class="text-xs space-y-1">
          <div v-for="k in accessKeys" :key="k.key" class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 border-b border-gray-50">
            <div class="flex items-center gap-1.5 min-w-0">
              <span class="font-mono text-[10px]">{{ (k.key || '').slice(0,12) }}...</span>
              <span v-html="keyStatusBadge(k)"></span>
              <span class="text-gray-400 text-[10px]">[{{ keyTypeLabel(k) }}]</span>
            </div>
            <div class="text-gray-400 text-[10px]">
              使用 {{ k.used_count||0 }}/{{ k.max_uses||'∞' }}
              <span v-if="k.expires_at">· 到期 {{ new Date(k.expires_at * 1000).toLocaleDateString() }}</span>
              <span v-if="k.created_at">· 创建 {{ new Date(k.created_at * 1000).toLocaleDateString() }}</span>
            </div>
            <div class="flex gap-2 ml-auto">
              <button @click="copyText(k.key)" class="text-pink-400 hover:text-pink-600 cursor-pointer border-0 bg-transparent text-[10px]">复制</button>
              <button v-if="k.disabled_at" @click="enableKey(k.key)" class="text-emerald-400 hover:text-emerald-600 cursor-pointer border-0 bg-transparent text-[10px]">启用</button>
              <button v-else @click="delKey(k.key)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-[10px]">禁用</button>
              <button @click="removeKey(k.key)" class="text-red-500 hover:text-red-700 cursor-pointer border-0 bg-transparent text-[10px]">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- FEATURED -->
      <div v-if="activeSection === 'featured'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">✨ 精选管理</h2>
        <div class="grid grid-cols-4 sm:grid-cols-6 gap-2">
          <div v-for="(item, i) in featured" :key="i" class="relative group" draggable="true"
            @dragstart="dragFeaturedIdx=i" @dragover.prevent @drop="reorderFeatured(i, dragFeaturedIdx)">
            <img :src="'/api/output/thumb?path=' + encodeURIComponent(typeof item === 'string' ? item : (item.path||''))" class="w-full aspect-square object-cover rounded-lg" />
            <button @click="removeFeatured(typeof item === 'string' ? item : item.path)" class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-red-500/80 text-white text-[10px] opacity-0 group-hover:opacity-100 cursor-pointer border-0">✕</button>
          </div>
        </div>
        <div class="mt-2 text-xs text-gray-400">拖拽图片可排序</div>
      </div>

      <!-- GEN LOGS -->
      <div v-if="activeSection === 'genlogs'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📝 生图日志</h2>
        <div class="flex gap-1.5 mb-3 flex-wrap">
          <input v-model="glQ" @keydown.enter="loadGenLogs(true)" placeholder="搜索用户..." class="flex-1 min-w-[100px] border border-gray-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-pink-400" />
          <input v-model="glDateFrom" type="date" class="border border-gray-200 rounded-lg px-2 py-1.5 text-[10px] outline-none focus:border-pink-400 w-[130px]" title="开始日期" />
          <input v-model="glDateTo" type="date" class="border border-gray-200 rounded-lg px-2 py-1.5 text-[10px] outline-none focus:border-pink-400 w-[130px]" title="结束日期" />
          <button @click="loadGenLogs(true)" class="px-2 py-1.5 bg-pink-500 text-white rounded-lg text-xs cursor-pointer border-0">搜索</button>
          <button @click="glQ='';glDateFrom='';glDateTo='';loadGenLogs(true)" class="px-2 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs cursor-pointer border-0">重置</button>
          <button @click="glEditMode=!glEditMode;if(!glEditMode)glSelected=new Set()" :class="['px-2 py-1.5 rounded-lg text-xs cursor-pointer border-0', glEditMode?'bg-pink-100 text-pink-600':'bg-gray-100 text-gray-600']">{{ glEditMode ? '退出' : '编辑' }}</button>
          <button v-if="glEditMode && glSelected.size" @click="glDeleteSelected" class="px-2 py-1.5 bg-red-500 text-white rounded-lg text-xs cursor-pointer border-0">删除({{ glSelected.size }})</button>
          <button v-if="glEditMode" @click="glSelectAll" class="px-2 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs cursor-pointer border-0">全选</button>
        </div>
        <div class="text-xs space-y-1 max-h-96 overflow-y-auto">
          <div v-for="g in genLogs" :key="g.log_id" class="py-1.5 border-b border-gray-50" :class="{'bg-pink-50/50': glSelected.has(g.log_id)}">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 min-w-0">
                <input v-if="glEditMode" type="checkbox" :checked="glSelected.has(g.id ?? g.log_id)" @change="glToggleSelect(g.id ?? g.log_id)" class="accent-pink-500 shrink-0" />
                <span class="font-mono text-gray-400 text-[10px] shrink-0">{{ (g.id || g.log_id || '').toString().slice(0,8) }}</span>
                <span :class="g.status==='success'?'text-green-500':'text-red-400'" class="shrink-0">{{ g.status }}</span>
                <span class="truncate">{{ g.login || g.github_id }}</span>
              </div>
              <div class="flex gap-1 shrink-0">
                <button v-if="g.prompt" @click="clipText(g.prompt)" class="text-gray-300 hover:text-pink-400 cursor-pointer border-0 bg-transparent text-[10px]" title="复制正面提示词">📋</button>
                <button v-if="g.negative_prompt" @click="clipText(g.negative_prompt)" class="text-gray-300 hover:text-pink-400 cursor-pointer border-0 bg-transparent text-[10px]" title="复制负面提示词">🚫</button>
              </div>
            </div>
            <div class="text-[10px] text-gray-400 truncate pl-5">{{ g.prompt?.slice(0,120) }}</div>
            <div v-if="g.error_reason" class="text-[10px] text-red-400 pl-5">❌ {{ g.error_reason }}</div>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-2 text-xs">
          <button @click="glPage--;loadGenLogs()" :disabled="glPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
          <span>{{ glPage + 1 }}</span>
          <button @click="glPage++;loadGenLogs()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
          <button @click="loadGenLogs(false)" class="ml-auto text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
        </div>
      </div>

      <!-- DELETION LOG -->
      <div v-if="activeSection === 'dellog'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🗑️ 删除记录</h2>
        <div class="flex flex-wrap gap-1.5 mb-2">
          <input v-model="delDateFrom" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400" title="开始日期" />
          <input v-model="delDateTo" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400" title="结束日期" />
          <button @click="delPage=0;loadDeletionLog()" class="px-2 py-1 bg-pink-500 text-white rounded-lg text-[10px] cursor-pointer border-0">搜索</button>
          <button @click="delDateFrom='';delDateTo='';delPage=0;loadDeletionLog()" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] cursor-pointer border-0">重置</button>
          <button @click="delEditMode=!delEditMode;if(!delEditMode)delSelected=new Set()" :class="['px-2 py-1 rounded-lg text-[10px] cursor-pointer border-0', delEditMode?'bg-pink-100 text-pink-600':'bg-gray-100 text-gray-600']">{{ delEditMode ? '退出' : '编辑' }}</button>
          <button v-if="delEditMode && delSelected.size" @click="delClearSelected" class="px-2 py-1 bg-red-500 text-white rounded-lg text-[10px] cursor-pointer border-0">清理({{ delSelected.size }})</button>
        </div>
        <div class="text-xs space-y-1 max-h-96 overflow-y-auto">
          <div v-for="d in delLog" :key="d.path" class="flex items-center gap-2 py-1 border-b border-gray-50 text-gray-600">
            <input v-if="delEditMode" type="checkbox" :checked="delSelected.has(d.path)" @change="delToggleSelect(d.path)" class="accent-pink-500 shrink-0" />
            <img v-if="d.thumb_url" :src="'/api/output/thumb?path=' + encodeURIComponent(d.path||'')" class="w-8 h-8 rounded object-cover shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="truncate text-[10px]">{{ d.path }}</div>
              <div class="text-[10px] text-gray-400">{{ new Date((d.deleted_at||d.time||0)*1000).toLocaleString() }} {{ d.deleted_by_login || d.login ? 'by ' + (d.deleted_by_login || d.login) : '' }}</div>
            </div>
            <button v-if="!delEditMode" @click="delClearSingle(d.path)" class="px-1.5 py-0.5 bg-red-50 text-red-500 rounded hover:bg-red-100 cursor-pointer border-0 text-[10px] shrink-0">清理</button>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-2 text-xs"><button @click="delPage--;loadDeletionLog()" :disabled="delPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button><span>{{ delPage + 1 }}</span><button @click="delPage++;loadDeletionLog()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button></div>
      </div>

      <!-- REPORTS -->
      <div v-if="activeSection === 'reports'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📮 举报管理</h2>
        <div v-for="r in reports" :key="r.id" class="border-b border-gray-50 py-2 text-xs">
          <div class="flex items-center gap-2">
            <img v-if="r.path" :src="'/api/output/thumb?path=' + encodeURIComponent(r.path||'')" class="w-10 h-10 rounded object-cover shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="text-gray-600 truncate">{{ r.image_path }} <span class="text-gray-400">by {{ r.reporter }}</span></div>
              <div v-if="r.reporter_ip" class="text-[10px] text-gray-400">IP: {{ r.reporter_ip }} {{ r.creator_ip ? '/ 创建者: ' + r.creator_ip : '' }}</div>
              <div class="text-gray-500">{{ r.reason }}</div>
            </div>
          </div>
          <div class="flex gap-2 mt-1 ml-12"><button @click="resolveReport(r.id,'ignore')" class="text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent text-[10px]">忽略</button><button @click="resolveReport(r.id,'delete')" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-[10px]">删图</button><button @click="resolveReport(r.id,'ban_creator')" class="text-red-500 hover:text-red-700 cursor-pointer border-0 bg-transparent text-[10px]">封禁创建者</button><button @click="resolveReport(r.id,'ban_reporter')" class="text-red-500 hover:text-red-700 cursor-pointer border-0 bg-transparent text-[10px]">封禁举报者</button></div>
        </div>
        <div v-if="!reports.length" class="text-xs text-gray-400 py-4 text-center">暂无举报</div>
        <button @click="loadReports" class="mt-2 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
      </div>

      <!-- RECENT -->
      <div v-if="activeSection === 'recent'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🕐 最近生图</h2>
        <div class="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2">
          <div v-for="img in recentImages" :key="img.path" class="relative group">
            <img :src="'/api/output/thumb?path=' + encodeURIComponent(img.path||'')" class="w-full aspect-square object-cover rounded-lg" />
            <div class="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-0.5 bg-black/40 rounded-lg">
              <button @click="delRecentImage(img.path)" class="text-[10px] px-2 py-0.5 bg-red-500/80 text-white rounded hover:bg-red-600 cursor-pointer border-0">删除</button>
              <button @click="banIPFromRecent(img.ip || img.client_ip)" class="text-[10px] px-2 py-0.5 bg-red-500/80 text-white rounded hover:bg-red-600 cursor-pointer border-0">封禁IP</button>
              <button @click="addFeaturedFromRecent(img.path)" class="text-[10px] px-2 py-0.5 bg-amber-500/80 text-white rounded hover:bg-amber-600 cursor-pointer border-0">精选</button>
            </div>
            <div class="absolute bottom-0 left-0 right-0 bg-black/50 text-[9px] text-white px-1 truncate">{{ img.ip || img.client_ip || img.creator_login || img.login || '' }}</div>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-2 text-xs">
          <button @click="recentPage--;loadRecent()" :disabled="recentPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
          <span>{{ recentPage + 1 }}</span>
          <button @click="recentPage++;loadRecent()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
          <button @click="loadRecent(true)" class="ml-auto text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
        </div>
      </div>

      <!-- IMAGES -->
      <div v-if="activeSection === 'images'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🖼️ 图片管理</h2>
        <div v-if="imgSelected.size" class="mb-2"><button @click="batchDeleteImages" class="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs cursor-pointer border-0">删除选中({{ imgSelected.size }})</button></div>
        <div class="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2">
          <div v-for="img in adminImages" :key="img" class="relative group cursor-pointer" @click="imgSelected.has(img)?imgSelected.delete(img):imgSelected.add(img);imgSelected=new Set(imgSelected)">
            <img :src="'/api/output/thumb?path=' + encodeURIComponent(img)" class="w-full aspect-square object-cover rounded-lg" :class="{'ring-2 ring-pink-500':imgSelected.has(img)}" />
          </div>
        </div>
        <div class="flex items-center gap-2 mt-2 text-xs"><button @click="imgPage--;loadImages()" :disabled="imgPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button><span>{{ imgPage + 1 }}</span><button @click="imgPage++;loadImages()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button></div>
      </div>

      <!-- GC -->
      <div v-if="activeSection === 'gc'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🧹 GC 系统</h2>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3 text-xs">
          <div class="bg-gray-50 rounded-xl p-3"><div class="text-gray-400">已清理文件</div><div class="text-lg font-bold text-gray-700">{{ gcStats.total_cleaned || 0 }}</div></div>
          <div class="bg-gray-50 rounded-xl p-3"><div class="text-gray-400">累计生图</div><div class="text-lg font-bold text-gray-700">{{ gcStats.total_images || gcStats.total_generated || 0 }}</div></div>
          <div class="bg-gray-50 rounded-xl p-3"><div class="text-gray-400">重启次数</div><div class="text-lg font-bold text-gray-700">{{ gcStats.restart_count || 0 }}</div></div>
          <div class="bg-gray-50 rounded-xl p-3"><div class="text-gray-400">上次 GC</div><div class="text-lg font-bold text-gray-700">{{ gcStats.last_gc_time ? new Date(gcStats.last_gc_time * 1000).toLocaleDateString() : gcStats.last_gc ? new Date(gcStats.last_gc * 1000).toLocaleDateString() : '从未' }}</div></div>
        </div>
        <div class="flex gap-2 mb-3"><button @click="triggerGc(true)" class="px-4 py-1.5 bg-orange-500 text-white rounded-lg text-xs hover:bg-orange-600 cursor-pointer border-0">GC (备份)</button><button @click="triggerGc(false)" class="px-4 py-1.5 bg-red-500 text-white rounded-lg text-xs hover:bg-red-600 cursor-pointer border-0">GC (直接)</button></div>
        <div class="flex gap-1.5 mb-2 flex-wrap">
          <input v-model="gcDateFrom" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400 w-[130px]" title="开始日期" />
          <input v-model="gcDateTo" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400 w-[130px]" title="结束日期" />
          <button @click="gcPage=0;loadGcLogs()" class="px-2 py-1 bg-pink-500 text-white rounded-lg text-[10px] cursor-pointer border-0">搜索</button>
          <button @click="gcDateFrom='';gcDateTo='';gcPage=0;loadGcLogs()" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] cursor-pointer border-0">重置</button>
        </div>
        <div class="text-xs space-y-1 max-h-48 overflow-y-auto">
          <div v-for="g in gcLogs" :key="g.id || g.timestamp" class="py-1 border-b border-gray-50 text-gray-600"><span class="text-gray-400">{{ g.timestamp ? new Date(g.timestamp * 1000).toLocaleString() : new Date((g.created_at||0)*1000).toLocaleString() }}</span> {{ g.message || (g.cleaned ? '清理了 ' + JSON.stringify(g.cleaned) : '') }}</div>
        </div>
        <div class="flex items-center gap-2 mt-2 text-xs">
          <button @click="gcPage--;loadGcLogs()" :disabled="gcPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
          <span class="text-gray-400">{{ gcPage + 1 }}</span>
          <button @click="gcPage++;loadGcLogs()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
          <button @click="loadGcStats" class="ml-2 text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
        </div>
      </div>

      <!-- ACCESS CONFIG -->
      <div v-if="activeSection === 'access'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🔓 入口配置</h2>
        <p class="text-xs text-gray-400">限流等配置请在「限流配置」板块中修改。</p>
      </div>

      <!-- MAINTENANCE -->
      <div v-if="activeSection === 'maint'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🔧 维护模式</h2>
        <label class="flex items-center gap-2 text-sm mb-3 cursor-pointer">
          <input type="checkbox" v-model="maintEnabled" class="accent-pink-500" />
          <span :class="maintEnabled?'text-red-500 font-medium':'text-gray-600'">{{ maintEnabled ? '⚠️ 维护中' : '正常运行' }}</span>
        </label>
        <textarea v-model="maintMessage" placeholder="维护公告内容（支持 Markdown 格式）" rows="4" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm mb-2 outline-none focus:border-pink-400 box-border resize-y"></textarea>
        <button @click="saveMaint" class="px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">保存</button>
      </div>

      <!-- CUSTOM HEAD -->
      <div v-if="activeSection === 'chead'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">🧩 自定义 Head</h2>
        <label class="flex items-center gap-2 text-sm mb-3 cursor-pointer">
          <input type="checkbox" v-model="cheadEnabled" class="accent-pink-500" />
          <span :class="cheadEnabled?'text-green-500':'text-gray-500'">{{ cheadEnabled ? '已启用' : '已禁用' }}</span>
        </label>
        <textarea v-model="cheadHtml" placeholder="插入到 &lt;head&gt; 中的 HTML 代码（如统计脚本、额外 CSS 等）" rows="6" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm font-mono text-xs mb-2 outline-none focus:border-pink-400 box-border resize-y"></textarea>
        <button @click="saveChead" class="px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">保存</button>
      </div>

      <!-- EMAIL MANAGEMENT -->
      <div v-if="activeSection === 'email'" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
        <h2 class="text-sm font-bold text-gray-700 mb-3">📧 邮箱管理</h2>

        <!-- Invite Codes -->
        <div class="mb-4">
          <h3 class="text-xs font-semibold text-gray-500 mb-2">邀请码</h3>
          <button @click="genInviteCode" class="mb-2 px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">生成邀请码</button>
          <div class="text-xs space-y-1">
            <div v-for="c in inviteCodes" :key="c.code" class="flex justify-between py-1 border-b border-gray-50">
              <span class="font-mono">{{ c.code }}</span>
              <button @click="delInviteCode(c.code)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-xs">删除</button>
            </div>
          </div>
        </div>

        <!-- Email Users -->
        <div class="mb-4">
          <h3 class="text-xs font-semibold text-gray-500 mb-2">邮箱用户 <span v-if="euTotal" class="text-gray-400 font-normal">({{ euTotal }} 人)</span></h3>
          <div class="flex gap-1.5 mb-2">
            <input v-model="euSearch" @keydown.enter="euPage=0;loadEmailAuth()" placeholder="搜索邮箱/用户名..." class="flex-1 min-w-[100px] border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400" />
            <button @click="euPage=0;loadEmailAuth()" class="px-2 py-1 bg-pink-500 text-white rounded-lg text-[10px] cursor-pointer border-0">搜索</button>
            <button @click="euSearch='';euPage=0;loadEmailAuth()" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] cursor-pointer border-0">重置</button>
          </div>
          <div class="text-xs space-y-1 max-h-48 overflow-y-auto">
            <div v-for="u in emailUsersList" :key="u.github_id" class="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5 border-b border-gray-50">
              <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="onlineList.includes(u.login||u.github_id)?'bg-green-500':'bg-gray-300'"></span>
              <span class="font-medium text-[10px]">{{ u.login || u.email }}</span>
              <span v-if="u.role === 'admin'" class="text-[9px] bg-purple-100 text-purple-700 px-1 rounded">admin</span>
              <span class="text-gray-400 text-[10px] truncate flex-1 min-w-0">{{ u.email }}</span>
              <div class="flex gap-1 shrink-0">
                <button @click="resendVerify(u.github_id)" class="text-pink-400 hover:text-pink-600 cursor-pointer border-0 bg-transparent text-[10px]">重发验证</button>
                <button @click="resetTotp(u.github_id)" class="text-amber-400 hover:text-amber-600 cursor-pointer border-0 bg-transparent text-[10px]">重置 2FA</button>
                <button @click="sendPasswordResetLink(u.github_id)" class="text-blue-400 hover:text-blue-600 cursor-pointer border-0 bg-transparent text-[10px]">重置密码</button>
                <button @click="openSendEmailModal(u.email, u.github_id)" class="text-green-400 hover:text-green-600 cursor-pointer border-0 bg-transparent text-[10px]">📧</button>
                <button @click="toggleEmailBan(u.github_id, u.banned)" :class="[u.banned?'text-emerald-400':'text-red-400','hover:underline cursor-pointer border-0 bg-transparent text-[10px]']">{{ u.banned ? '解封' : '封禁' }}</button>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-1 text-[10px]">
            <button @click="euPage--;loadEmailAuth()" :disabled="euPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
            <span class="text-gray-400">{{ euPage + 1 }}</span>
            <button @click="euPage++;loadEmailAuth()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
          </div>
        </div>

        <!-- Email Logs -->
        <div class="mb-4">
          <h3 class="text-xs font-semibold text-gray-500 mb-2">发信日志</h3>
          <div class="flex flex-wrap gap-1.5 mb-2">
            <input v-model="elSearch" placeholder="搜索邮箱..." class="flex-1 min-w-[100px] border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400" />
            <input v-model="elDateFrom" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400 w-[120px]" title="开始日期" />
            <input v-model="elDateTo" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400 w-[120px]" title="结束日期" />
            <button @click="elPage=0;loadEmailAuth()" class="px-2 py-1 bg-pink-500 text-white rounded-lg text-[10px] cursor-pointer border-0">搜索</button>
            <button @click="elSearch='';elDateFrom='';elDateTo='';elPage=0;loadEmailAuth()" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] cursor-pointer border-0">重置</button>
            <button @click="elEditMode=!elEditMode;if(!elEditMode)elSelected=new Set()" :class="['px-2 py-1 rounded-lg text-[10px] cursor-pointer border-0', elEditMode?'bg-pink-100 text-pink-600':'bg-gray-100 text-gray-600']">{{ elEditMode ? '编辑' : '预览' }}</button>
            <button v-if="elEditMode" @click="elSelectAll" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] cursor-pointer border-0">全选</button>
            <button v-if="elEditMode && elSelected.size" @click="elDeleteSelected" class="px-2 py-1 bg-red-500 text-white rounded-lg text-[10px] cursor-pointer border-0">删除({{ elSelected.size }})</button>
            <button v-if="!elEditMode" @click="elPage=0;elSearch='';elDateFrom='';elDateTo='';elEditMode=false;fetchJSON('/api/admin/email-logs/clear','POST',{all:true});loadEmailAuth()" class="px-2 py-1 bg-red-500 text-white rounded-lg text-[10px] cursor-pointer border-0">清空全部</button>
          </div>
          <div class="text-xs space-y-1 max-h-48 overflow-y-auto">
            <div v-for="log in emailLogsList" :key="log.id" class="py-1 border-b border-gray-50 text-gray-600 flex items-center gap-2">
              <input v-if="elEditMode" type="checkbox" :checked="elSelected.has(String(log.id))" @change="elToggleSelect(String(log.id))" class="accent-pink-500 shrink-0" />
              <span class="text-[10px] text-gray-400 shrink-0">{{ new Date((log.created_at||0)*1000).toLocaleString() }}</span>
              <span class="flex-1 truncate">{{ log.recipient || log.email }}</span>
              <span :class="log.success || log.status==='ok'?'text-green-500':'text-red-400'">{{ log.success || log.status==='ok' ? '✓' : '✗' }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-1 text-[10px]">
            <button @click="elPage--;loadEmailAuth()" :disabled="elPage<=0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
            <span class="text-gray-400">{{ elPage + 1 }}</span>
            <button @click="elPage++;loadEmailAuth()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
          </div>
        </div>

        <!-- Rate Limits -->
        <div class="mb-4">
          <h3 class="text-xs font-semibold text-gray-500 mb-2">速率限制</h3>
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div v-for="(v, k) in rateLimits" :key="k">
              <label class="text-gray-500 block mb-0.5">{{ rateLimitLabels[k] || k }}</label>
              <input v-model="rateLimits[k]" class="w-full border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400 box-border" />
            </div>
          </div>
          <button @click="saveRateLimits" class="mt-2 px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">保存</button>
        </div>

        <!-- Abuse IPs -->
        <div>
          <h3 class="text-xs font-semibold text-gray-500 mb-2">恶意 IP</h3>
          <button @click="clearAbuseIps" class="mb-2 px-4 py-1.5 bg-red-500 text-white rounded-lg text-xs hover:bg-red-600 cursor-pointer border-0">清空全部</button>
          <div class="text-xs space-y-1 max-h-32 overflow-y-auto">
            <div v-for="ip in abuseIps" :key="ip" class="flex justify-between py-1 border-b border-gray-50 text-gray-600">
              <span>{{ ip }}</span>
              <button @click="removeAbuseIp(ip)" class="text-red-400 hover:text-red-600 cursor-pointer border-0 bg-transparent text-[10px]">✕</button>
            </div>
          </div>
        </div>

        <button @click="loadEmailAuth" class="mt-3 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
      </div>

      <!-- Send Email Modal -->
      <Teleport to="body">
        <div v-if="sendEmailTo" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.self="sendEmailTo=''">
          <div class="bg-white rounded-2xl shadow-xl max-w-sm w-full p-5">
            <h3 class="text-base font-bold text-gray-700 mb-3">📧 发送邮件至 {{ sendEmailTo }}</h3>
            <input v-model="sendEmailSubject" placeholder="主题" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm mb-2 outline-none focus:border-pink-400 box-border" />
            <textarea v-model="sendEmailBody" placeholder="邮件正文" rows="4" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm mb-2 outline-none focus:border-pink-400 resize-y box-border"></textarea>
            <div class="flex gap-2">
              <button @click="sendEmailTo=''" class="flex-1 py-2 bg-gray-100 rounded-xl hover:bg-gray-200 text-sm text-gray-600 transition-all cursor-pointer border-0">取消</button>
              <button @click="doSendEmail" class="flex-1 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-sm font-semibold transition-all cursor-pointer border-0">发送</button>
            </div>
            <span v-if="sendEmailStatus" class="text-xs mt-2 block text-center" :class="sendEmailStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ sendEmailStatus }}</span>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>
