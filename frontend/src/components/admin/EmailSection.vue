<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, fmt, fmtShort, onlineGithubIds } from './useAdminApi'

defineProps<{ visible: boolean }>()

const d = ref<any>({})
const codes = ref<any[]>([])
const genCount = ref(10)
const genMaxUses = ref(1)
const genStatus = ref('')
const hourlyIP = ref(3)
const dailyIP = ref(10)
const dailyEmail = ref(20)
const configStatus = ref('')
const rateLimits = ref<Record<string, number>>({})
const rlStatus = ref('')

const autoRefresh = ref(false)
const autoInterval = ref(30)
let autoTimer: ReturnType<typeof setInterval> | null = null
function toggleAuto() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) { stopAuto(); autoTimer = setInterval(refreshAll, autoInterval.value * 1000) }
  else stopAuto()
}
function stopAuto() { if (autoTimer !== null) { clearInterval(autoTimer); autoTimer = null } }

const emailUsers = ref<any[]>([])
const euTotal = ref(0)
const euOffset = ref(0)
const euSearch = ref('')
const euLimit = 24

const logs = ref<any[]>([])
const logTotal = ref(0)
const logOffset = ref(0)
const logSearch = ref('')
const logDateFrom = ref('')
const logDateTo = ref('')
const logLimit = 24
const logSelected = ref<Set<number>>(new Set())

const abuseIPs = ref<string[]>([])

const emailModalUser = ref<any>(null)
const emailModalSubject = ref('')
const emailModalBody = ref('')
const emailModalStatus = ref('')

async function loadAll() {
  try {
    const r = await api('GET', '/api/admin/email-dashboard')
    d.value = r; codes.value = r.invite_codes || []
    if (r.limits) { hourlyIP.value = r.limits.reg_hourly_limit_per_ip ?? hourlyIP.value; dailyIP.value = r.limits.reg_daily_limit_per_ip ?? dailyIP.value; dailyEmail.value = r.limits.reg_daily_limit_per_email ?? dailyEmail.value }
    rateLimits.value = r.rate_limits ? { ...r.rate_limits } : {}; abuseIPs.value = r.abuse_ips || []
  } catch {}
}
async function loadUsers() {
  try { const r = await api('GET', `/api/admin/email-users?limit=${euLimit}&offset=${euOffset.value}&search=${encodeURIComponent(euSearch.value)}`); emailUsers.value = r.users || []; euTotal.value = r.total || 0 } catch {}
}
async function loadLogs() {
  try {
    let u = `/api/admin/email-logs?limit=${logLimit}&offset=${logOffset.value}`
    if (logSearch.value) u += `&search=${encodeURIComponent(logSearch.value)}`
    if (logDateFrom.value) u += '&date_from=' + Math.floor(new Date(logDateFrom.value + 'T00:00:00').getTime() / 1000)
    if (logDateTo.value) u += '&date_to=' + Math.floor(new Date(logDateTo.value + 'T23:59:59').getTime() / 1000)
    const r = await api('GET', u); logs.value = r.logs || []; logTotal.value = r.total || 0
  } catch {}
}
async function refreshAll() { await Promise.all([loadAll(), loadUsers(), loadLogs()]) }

async function generateCodes() {
  if (!confirm(`生成 ${genCount.value} 个邀请码（最大使用 ${genMaxUses.value} 次）？`)) return
  genStatus.value = '生成中...'
  try { await api('POST', '/api/admin/invite-codes/generate', { count: genCount.value, max_uses: genMaxUses.value }); genStatus.value = '✅ 生成成功'; setTimeout(() => genStatus.value = '', 3000); loadAll() }
  catch (e: any) { genStatus.value = '❌ ' + e.message }
}
async function deleteCode(code: string) {
  if (!confirm('删除邀请码 ' + code + '？')) return
  if (prompt('确认删除该邀请码') !== '确认删除该邀请码') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/invite-codes/delete', { code }); loadAll() } catch (e: any) { alert('删除失败: ' + e.message) }
}
function codePct(c: any) { return Math.min(c.used_count / c.max_uses * 100, 100) }
function codeBarClass(pct: number) { return pct >= 100 ? 'bg-red-500' : pct >= 50 ? 'bg-yellow-500' : 'bg-green-500' }

async function saveConfig() {
  if (!confirm('保存邮箱注册限制？')) return
  configStatus.value = '保存中...'
  try { await api('POST', '/api/admin/email-config', { REG_HOURLY_LIMIT_PER_IP: hourlyIP.value, REG_DAILY_LIMIT_PER_IP: dailyIP.value, REG_DAILY_LIMIT_PER_EMAIL: dailyEmail.value }); configStatus.value = '✅ 保存成功'; setTimeout(() => configStatus.value = '', 3000) }
  catch (e: any) { configStatus.value = '❌ ' + e.message }
}
async function saveRateLimits() {
  if (!confirm('保存频率限制（重启生效）？')) return
  rlStatus.value = '保存中...'
  try { await api('POST', '/api/admin/rate-limits', rateLimits.value); rlStatus.value = '✅ 保存成功，重启生效'; setTimeout(() => rlStatus.value = '', 3000) }
  catch (e: any) { rlStatus.value = '❌ ' + e.message }
}

function filterEU() { euOffset.value = 0; loadUsers() }
function resetEU() { euSearch.value = ''; euOffset.value = 0; loadUsers() }
function euPrev() { if (euOffset.value > 0) { euOffset.value -= euLimit; loadUsers() } }
function euNext() { if (euOffset.value + euLimit < euTotal.value) { euOffset.value += euLimit; loadUsers() } }

async function resetTOTP(user: any) {
  if (!confirm(`确认重置2FA用户 ${user.login || user.email}？`)) return
  if (prompt('确认重置2FA') !== '确认重置2FA') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/email-users/reset-totp', { github_id: user.github_id }); loadUsers() } catch (e: any) { alert('重置2FA失败: ' + e.message) }
}
async function resendVerify(user: any) {
  if (!confirm(`确认重新发送验证邮件给 ${user.login || user.email}？`)) return
  if (prompt('确认重新发送验证') !== '确认重新发送验证') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/email-users/resend-verify', { github_id: user.github_id }); loadUsers() } catch (e: any) { alert('重发验证失败: ' + e.message) }
}
async function resetPassword(user: any) {
  if (!confirm(`确认重置密码给 ${user.login || user.email}？`)) return
  if (prompt('确认重置密码') !== '确认重置密码') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/email-users/reset-password', { github_id: user.github_id }); loadUsers() } catch (e: any) { alert('重置密码失败: ' + e.message) }
}
async function banUser(user: any) {
  if (!confirm(`确认封禁用户 ${user.login || user.email}？`)) return
  if (prompt('确认封禁') !== '确认封禁') { alert('输入不匹配'); return }
  const reason = prompt('封禁原因（可选）') || ''
  try { await api('POST', '/api/admin/users/ban', { github_id: user.github_id, reason }); loadUsers() } catch (e: any) { alert('封禁失败: ' + e.message) }
}
async function unbanUser(user: any) {
  if (!confirm(`确认解封用户 ${user.login || user.email}？`)) return
  if (prompt('确认解封') !== '确认解封') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/users/unban', { github_id: user.github_id }); loadUsers() } catch (e: any) { alert('解封失败: ' + e.message) }
}
function openEmailModal(user: any) { emailModalUser.value = user; emailModalSubject.value = ''; emailModalBody.value = ''; emailModalStatus.value = '' }
function closeEmailModal() { emailModalUser.value = null }
async function sendCustomEmail() {
  if (!emailModalUser.value) return
  if (!emailModalSubject.value || !emailModalBody.value) { alert('请填写主题和内容'); return }
  if (!confirm(`确认发送邮件给 ${emailModalUser.value.email}？`)) return
  emailModalStatus.value = '发送中...'
  try { await api('POST', '/api/admin/email-users/send-custom-email', { github_id: emailModalUser.value.github_id, subject: emailModalSubject.value, message: emailModalBody.value }); emailModalStatus.value = '✅ 发送成功'; setTimeout(() => closeEmailModal(), 2000) }
  catch (e: any) { emailModalStatus.value = '❌ ' + e.message }
}

function toggleLog(id: number) { logSelected.value.has(id) ? logSelected.value.delete(id) : logSelected.value.add(id) }
function toggleAllLogs() { logSelected.value.size === logs.value.length ? logSelected.value.clear() : logSelected.value = new Set(logs.value.map(l => l.id)) }
function filterLogs() { logOffset.value = 0; loadLogs() }
function resetLogs() { logSearch.value = ''; logDateFrom.value = ''; logDateTo.value = ''; logOffset.value = 0; loadLogs() }
function logPrev() { if (logOffset.value > 0) { logOffset.value -= logLimit; loadLogs() } }
function logNext() { if (logOffset.value + logLimit < logTotal.value) { logOffset.value += logLimit; loadLogs() } }
async function deleteSelectedLogs() {
  if (!logSelected.value.size) return
  if (!confirm(`删除 ${logSelected.value.size} 条记录？`)) return
  try { await api('POST', '/api/admin/email-logs/clear', { ids: Array.from(logSelected.value) }); logSelected.value.clear(); loadLogs() } catch (e: any) { alert('删除失败: ' + e.message) }
}
async function deleteLog(id: number) {
  if (!confirm('删除此记录？')) return
  try { await api('POST', '/api/admin/email-logs/clear', { ids: [id] }); loadLogs() } catch (e: any) { alert('删除失败: ' + e.message) }
}
async function clearAllLogs() {
  if (!confirm('清空所有邮件日志？')) return
  if (prompt('确认清空全部日志') !== '确认清空全部日志') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/email-logs/clear', {}); logSelected.value.clear(); loadLogs() } catch (e: any) { alert('清空失败: ' + e.message) }
}
function logStatusClass(s: string) { return s === 'ok' || s === 'sent' || s === 'success' ? 'bg-green-100 text-green-600' : s === 'rate_limited' ? 'bg-yellow-100 text-yellow-600' : 'bg-red-100 text-red-600' }
function logStatusText(s: string) { return s === 'ok' || s === 'sent' || s === 'success' ? '成功' : s === 'rate_limited' ? '限流' : '失败' }

async function removeAbuseIP(ip: string) {
  if (!confirm('移除此IP：' + ip + '？')) return
  try { await api('POST', '/api/admin/email-abuse-ips/clear', { ip }); abuseIPs.value = abuseIPs.value.filter(i => i !== ip) } catch (e: any) { alert('操作失败: ' + e.message) }
}
async function clearAllAbuseIPs() {
  if (!confirm('清空所有滥用IP？')) return
  if (prompt('确认清空全部滥用IP') !== '确认清空全部滥用IP') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/email-abuse-ips/clear', {}); abuseIPs.value = [] } catch (e: any) { alert('清空失败: ' + e.message) }
}

const euPage = computed(() => Math.floor(euOffset.value / euLimit) + 1)
const euTotalPages = computed(() => Math.ceil(euTotal.value / euLimit) || 1)
const logPage = computed(() => Math.floor(logOffset.value / logLimit) + 1)
const logTotalPages = computed(() => Math.ceil(logTotal.value / logLimit) || 1)

onMounted(() => { loadAll(); loadUsers(); loadLogs() })
onUnmounted(() => stopAuto())
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-sm font-bold text-gray-700">📧 邮箱认证管理</h2>
      <div class="flex items-center gap-2 text-xs">
        <button @click="refreshAll" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">刷新</button>
        <button @click="toggleAuto" :class="autoRefresh ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-600'" class="px-2 py-1 rounded hover:opacity-80 cursor-pointer border-0">自动刷新: {{ autoRefresh ? '开' : '关' }}</button>
        <input type="number" v-model.number="autoInterval" min="5" max="300" class="w-12 border border-gray-200 rounded px-1 py-0.5 text-xs text-center" />
        <span class="text-gray-400">秒</span>
      </div>
    </div>

    <!-- 1. 邀请码 -->
    <div class="mb-5">
      <div class="flex items-center gap-2 mb-2 text-xs">
        <span class="text-gray-600">生成</span>
        <input type="number" v-model.number="genCount" min="1" max="20" class="w-14 border border-gray-200 rounded px-1 py-0.5 text-xs" />
        <span class="text-gray-500">个，可用</span>
        <input type="number" v-model.number="genMaxUses" min="1" max="9999" class="w-14 border border-gray-200 rounded px-1 py-0.5 text-xs" />
        <span class="text-gray-500">次</span>
        <button @click="generateCodes" class="px-2 py-0.5 bg-green-500 text-white rounded hover:bg-green-600 cursor-pointer border-0 text-xs">生成</button>
        <span class="text-gray-500">{{ genStatus }}</span>
      </div>
      <div v-if="codes.length" class="space-y-1 text-xs">
        <div v-for="c in codes" :key="c.code" class="flex items-center gap-2 bg-gray-50 rounded px-2 py-1">
          <span class="font-mono text-gray-700 flex-1 truncate">{{ c.code }}</span>
          <div class="w-20 bg-gray-200 rounded-full h-1.5 overflow-hidden shrink-0">
            <div class="h-full rounded-full" :class="codeBarClass(codePct(c))" :style="{ width: codePct(c) + '%' }"></div>
          </div>
          <span class="text-gray-500 w-16 text-right shrink-0">{{ c.used_count }}/{{ c.max_uses }}</span>
          <span class="text-gray-400 shrink-0">{{ fmtShort(c.created_at) }}</span>
          <button @click="deleteCode(c.code)" class="text-red-500 hover:text-red-600 cursor-pointer border-0 bg-transparent text-[10px] shrink-0">删除</button>
        </div>
      </div>
    </div>

    <!-- 2. 注册限流 -->
    <div class="mb-5">
      <div class="flex items-center gap-2 mb-2">
        <h3 class="text-xs font-semibold text-gray-600">⏱ 注册限流</h3>
        <button @click="saveConfig" class="px-2 py-0.5 bg-pink-500 text-white rounded hover:bg-pink-600 cursor-pointer border-0 text-xs">保存</button>
        <span class="text-xs text-gray-500">{{ configStatus }}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-xs">
        <label class="flex items-center gap-1">每小时IP：<input type="number" v-model.number="hourlyIP" min="0" max="999" class="w-full border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
        <label class="flex items-center gap-1">每天IP：<input type="number" v-model.number="dailyIP" min="0" max="9999" class="w-full border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
        <label class="flex items-center gap-1">每天邮箱：<input type="number" v-model.number="dailyEmail" min="0" max="999" class="w-full border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
      </div>
    </div>

    <!-- 3. 邮箱注册用户 -->
    <div class="mb-5">
      <div class="flex items-center gap-2 mb-2 text-xs">
        <input v-model="euSearch" placeholder="邮箱/用户名搜索" class="border border-gray-200 rounded px-2 py-1 text-xs w-48" @keyup.enter="filterEU" />
        <button @click="filterEU" class="px-2 py-1 bg-pink-500 text-white rounded hover:bg-pink-600 cursor-pointer border-0 text-xs">筛选</button>
        <button @click="resetEU" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0 text-xs">重置</button>
      </div>
      <div class="overflow-x-auto text-xs">
        <table class="w-full">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-100">
              <th class="py-1 pr-2"></th>
              <th class="py-1 pr-2">登录名</th>
              <th class="py-1 pr-2">邮箱</th>
              <th class="py-1 pr-2">角色</th>
              <th class="py-1 pr-2">注册时间</th>
              <th class="py-1">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in emailUsers" :key="u.github_id" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-1 pr-2"><span class="w-2 h-2 rounded-full inline-block" :class="onlineGithubIds.has(u.github_id) ? 'bg-green-500' : 'bg-gray-300'"></span></td>
              <td class="py-1 pr-2">{{ u.login }}</td>
              <td class="py-1 pr-2">{{ u.email || '-' }}</td>
              <td class="py-1 pr-2">
                <span class="px-1.5 py-0.5 rounded text-[10px]" :class="u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'">{{ u.role }}</span>
              </td>
              <td class="py-1 pr-2 text-gray-500">{{ fmt(u.created_at) }}</td>
              <td class="py-1">
                <div class="flex flex-wrap gap-1">
                  <button v-if="u.totp_enabled" @click="resetTOTP(u)" class="px-1.5 py-0.5 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0 text-[10px]">重置2FA</button>
                  <span v-if="u.role === 'admin'" class="text-[10px] text-gray-400">不可封禁</span>
                  <button v-else-if="u.banned" @click="unbanUser(u)" class="px-1.5 py-0.5 bg-emerald-100 text-emerald-600 rounded hover:bg-emerald-200 cursor-pointer border-0 text-[10px]">解封</button>
                  <button v-else @click="banUser(u)" class="px-1.5 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px]">封禁</button>
                  <button v-if="!u.verified" @click="resendVerify(u)" class="px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 cursor-pointer border-0 text-[10px]">重发验证</button>
                  <button @click="resetPassword(u)" class="px-1.5 py-0.5 bg-yellow-100 text-yellow-600 rounded hover:bg-yellow-200 cursor-pointer border-0 text-[10px]">重置密码</button>
                  <button @click="openEmailModal(u)" class="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 cursor-pointer border-0 text-[10px]">📧</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!emailUsers.length" class="text-gray-400 text-[10px] py-2 text-center">无用户</div>
      </div>
      <div class="flex items-center gap-2 mt-2 text-xs text-gray-500">
        <span>共 {{ euTotal }} 条，第 {{ euPage }}/{{ euTotalPages }} 页</span>
        <button @click="euPrev" :disabled="euOffset <= 0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
        <button @click="euNext" :disabled="euOffset + euLimit >= euTotal" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
      </div>
    </div>

    <!-- 4. 速率限制 -->
    <div class="mb-5">
      <div class="flex items-center gap-2 mb-2">
        <h3 class="text-xs font-semibold text-gray-600">⚙️ 速率限制</h3>
        <button @click="saveRateLimits" class="px-2 py-0.5 bg-pink-500 text-white rounded hover:bg-pink-600 cursor-pointer border-0 text-xs">保存（重启生效）</button>
        <span class="text-xs text-gray-500">{{ rlStatus }}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-xs">
        <label v-for="(v, k) in rateLimits" :key="k" class="flex items-center gap-1">
          <span class="text-gray-500">{{ k }}:</span>
          <input type="number" v-model.number="rateLimits[k]" class="w-full border border-gray-200 rounded px-1 py-0.5 text-xs" />
        </label>
      </div>
    </div>

    <!-- 5. 发信日志 -->
    <div class="mb-5">
      <div class="flex items-center gap-2 mb-2 text-xs flex-wrap">
        <input type="date" v-model="logDateFrom" class="border border-gray-200 rounded px-1 py-0.5 text-xs" />
        <span class="text-gray-400">~</span>
        <input type="date" v-model="logDateTo" class="border border-gray-200 rounded px-1 py-0.5 text-xs" />
        <input v-model="logSearch" placeholder="搜索" class="border border-gray-200 rounded px-2 py-0.5 text-xs w-28" @keyup.enter="filterLogs" />
        <button @click="filterLogs" class="px-2 py-0.5 bg-pink-500 text-white rounded hover:bg-pink-600 cursor-pointer border-0 text-xs">筛选</button>
        <button @click="resetLogs" class="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0 text-xs">重置</button>
        <button @click="loadLogs" class="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0 text-xs">刷新</button>
        <button @click="deleteSelectedLogs" :disabled="!logSelected.size" class="px-2 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-xs disabled:opacity-50">删除选中</button>
        <button @click="clearAllLogs" class="px-2 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-xs">清空</button>
      </div>
      <div class="overflow-x-auto text-xs">
        <table class="w-full">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-100">
              <th class="py-1 pr-2"><input type="checkbox" :checked="logs.length > 0 && logSelected.size === logs.length" @change="toggleAllLogs" class="accent-pink-500" /></th>
              <th class="py-1 pr-2">时间</th>
              <th class="py-1 pr-2">收件人</th>
              <th class="py-1 pr-2">主题</th>
              <th class="py-1 pr-2">状态</th>
              <th class="py-1">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-1 pr-2"><input type="checkbox" :checked="logSelected.has(log.id)" @change="toggleLog(log.id)" class="accent-pink-500" /></td>
              <td class="py-1 pr-2 text-gray-500 whitespace-nowrap">{{ fmt(log.created_at || log.timestamp) }}</td>
              <td class="py-1 pr-2">{{ log.recipient || log.email || '-' }}</td>
              <td class="py-1 pr-2 max-w-[200px] truncate">{{ log.subject || '-' }}</td>
              <td class="py-1 pr-2"><span class="px-1 py-0.5 rounded text-[10px]" :class="logStatusClass(log.status)">{{ logStatusText(log.status) }}</span></td>
              <td class="py-1"><button @click="deleteLog(log.id)" class="text-red-500 hover:text-red-700 cursor-pointer border-0 bg-transparent text-xs font-bold">&times;</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="!logs.length" class="text-gray-400 text-[10px] py-2 text-center">无日志</div>
      </div>
      <div class="flex items-center gap-2 mt-2 text-xs text-gray-500">
        <span>共 {{ logTotal }} 条，第 {{ logPage }}/{{ logTotalPages }} 页</span>
        <button @click="logPrev" :disabled="logOffset <= 0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
        <button @click="logNext" :disabled="logOffset + logLimit >= logTotal" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
      </div>
    </div>

    <!-- 6. 恶意IP -->
    <div v-if="abuseIPs.length" class="flex items-center gap-1 text-xs flex-wrap">
      <span class="text-gray-700 font-medium">🚫 恶意IP：</span>
      <span v-for="ip in abuseIPs" :key="ip" class="inline-flex items-center gap-1 bg-red-50 text-red-600 px-2 py-0.5 rounded">
        {{ ip }}
        <button @click="removeAbuseIP(ip)" class="text-red-500 hover:text-red-700 cursor-pointer border-0 bg-transparent text-xs font-bold">&times;</button>
      </span>
      <button @click="clearAllAbuseIPs" class="px-2 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-xs">清空全部</button>
    </div>
  </div>

  <!-- Custom Email Modal -->
  <Teleport to="body">
    <div v-if="emailModalUser" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.self="closeEmailModal">
      <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-4">
        <h3 class="text-sm font-bold text-gray-700 mb-3">📧 发送邮件给 {{ emailModalUser.email }}</h3>
        <input v-model="emailModalSubject" placeholder="主题" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs mb-3 outline-none focus:border-pink-400" />
        <textarea v-model="emailModalBody" placeholder="内容" rows="5" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs mb-3 outline-none focus:border-pink-400 resize-none"></textarea>
        <div class="flex items-center gap-2">
          <button @click="sendCustomEmail" class="px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">发送</button>
          <button @click="closeEmailModal" class="px-4 py-1.5 bg-gray-200 text-gray-600 rounded-lg text-xs hover:bg-gray-300 cursor-pointer border-0">取消</button>
          <span class="text-xs text-gray-500">{{ emailModalStatus }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>
