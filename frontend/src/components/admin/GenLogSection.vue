<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, fmt, copyText } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([]), total = ref(0), page = ref(0), statusText = ref('')
const search = ref(''), pathSearch = ref(''), dateFrom = ref(''), dateTo = ref('')
const autoEnabled = ref(false), autoInterval = ref(30), editMode = ref(false), selected = ref<number[]>([])
const orphans = ref<any[]>([])
const scanning = ref(false)
const scanDateFrom = ref('')
const scanDateTo = ref('')
const genlogsInfo = ref<{min_date:number;max_date:number;total:number}>({min_date:0,max_date:0,total:0})
const PAGE_SIZE = 24
const totalPages = ref(0)
import { computed } from 'vue'
const pageNumbers = computed(() => {
  const tp = Math.ceil(total.value / PAGE_SIZE) || 1; totalPages.value = tp
  if (tp <= 1) return []
  const p = page.value, s = Math.max(0, p - 2), e = Math.min(tp - 1, p + 2)
  const nums: number[] = []
  if (s > 0) nums.push(-1)
  for (let i = s; i <= e; i++) nums.push(i)
  if (e < tp - 1) nums.push(-1)
  return nums
})
let timer: any = null

function toggleAuto() { autoEnabled.value = !autoEnabled.value; if (autoEnabled.value) startAuto(); else stopAuto() }
function startAuto() { stopAuto(); if (!autoEnabled.value || page.value !== 0) return; timer = setInterval(load, autoInterval.value * 1000) }
function stopAuto() { if (timer) { clearInterval(timer); timer = null } }

async function load() {
  try {
    let u = `/api/admin/gen-logs?limit=${PAGE_SIZE}&offset=${page.value * PAGE_SIZE}`
    if (search.value) u += '&login=' + encodeURIComponent(search.value)
    if (pathSearch.value) u += '&path=' + encodeURIComponent(pathSearch.value)
    if (dateFrom.value) u += '&date_from=' + (new Date(dateFrom.value + 'T00:00:00').getTime() / 1000)
    if (dateTo.value) u += '&date_to=' + (new Date(dateTo.value + 'T23:59:59').getTime() / 1000)
    const r = await api('GET', u)
    items.value = r.items || []; total.value = r.total || 0
    const s = page.value * PAGE_SIZE + 1, e = Math.min(s + items.value.length - 1, total.value)
    statusText.value = items.value.length ? `显示 ${s}-${e} / ${total.value} 条` : ''
    startAuto()
  } catch {}
}

function filter() { page.value = 0; load() }
function resetFilter() { search.value = ''; pathSearch.value = ''; dateFrom.value = ''; dateTo.value = ''; page.value = 0; load() }

function toggleEdit() { editMode.value = !editMode.value; if (!editMode.value) selected.value = [] }
function toggleAll() { selected.value = selected.value.length === items.value.length ? [] : items.value.map(i => i.id) }
function toggleItem(id: number) { selected.value.includes(id) ? selected.value = selected.value.filter(x => x !== id) : selected.value = [...selected.value, id] }

async function batchDelete() {
  if (!selected.value.length) return
  if (!confirm(`确定删除选中的 ${selected.value.length} 条生图日志？`)) return
  const i = prompt(`请输入"确认删除生图日志"以继续删除 ${selected.value.length} 条记录：`)
  if (i !== '确认删除生图日志') { alert('输入不匹配，已取消'); return }
  await api('POST', '/api/admin/gen-logs/delete', { ids: selected.value })
  selected.value = []; page.value = 0; load()
}

async function clearAll() {
  const hasDate = dateFrom.value || dateTo.value
  if (!confirm(hasDate ? '确认清空当前日期范围内的生图日志？此操作不可恢复。' : '确认清空所有生图日志？此操作不可恢复。')) return
  const i = prompt('请输入"确认删除生图日志"以继续：')
  if (i !== '确认删除生图日志') { alert('输入不匹配，已取消'); return }
  let qs = ''
  const params: string[] = []
  if (search.value) params.push('login=' + encodeURIComponent(search.value))
  if (dateFrom.value) params.push('date_from=' + (new Date(dateFrom.value + 'T00:00:00').getTime() / 1000))
  if (dateTo.value) params.push('date_to=' + (new Date(dateTo.value + 'T23:59:59').getTime() / 1000))
  if (params.length) qs = '?' + params.join('&')
  await api('DELETE', '/api/admin/gen-logs' + qs)
  statusText.value = '✓ 日志已清空'; page.value = 0; load()
}

const orphanSearch = ref('')
const orphanDateFrom = ref('')
const orphanDateTo = ref('')
const orphanMsg = ref('')
const orphanRange = ref<{min:number;max:number;count:number}|null>(null)
const scanDone = ref(false)
let orphanPollTimer: ReturnType<typeof setInterval> | null = null

// 补充缩略图
const backfilling = ref(false)
const backfillMsg = ref('')
let backfillPollTimer: ReturnType<typeof setInterval> | null = null
async function backfillThumbs() {
  if (backfilling.value) return
  const df = scanDateFrom.value, dt = scanDateTo.value
  const label = (df || dt) ? `区间 ${df || '不限'} ~ ${dt || '不限'}` : '全部记录'
  if (!confirm(`确定为【${label}】中「原图还在但缩略图丢失」的记录补充缩略图？`)) return
  backfilling.value = true
  backfillMsg.value = ''
  const body: any = {}
  if (df) body.date_from = new Date(df + 'T00:00:00').getTime() / 1000
  if (dt) body.date_to = new Date(dt + 'T23:59:59').getTime() / 1000
  try {
    const r = await api('POST', '/api/admin/gen-logs/backfill-thumbs', body)
    if (!r.ok) { backfilling.value = false; alert(r.error || '启动失败'); return }
    pollBackfill()
  } catch { backfilling.value = false }
}
function pollBackfill() {
  if (backfillPollTimer) clearInterval(backfillPollTimer)
  backfillPollTimer = setInterval(async () => {
    try {
      const s = await api('GET', '/api/admin/gen-logs/backfill-thumbs/status')
      if (s.status === 'running') {
        backfillMsg.value = `补充缩略图中… ${s.processed || 0}/${s.total || 0}（已补 ${s.regenerated || 0}）`
      } else if (s.status === 'done') {
        if (backfillPollTimer) clearInterval(backfillPollTimer); backfillPollTimer = null
        backfilling.value = false
        backfillMsg.value = `✓ 补充完成：新增 ${s.regenerated || 0} 张，跳过 ${s.skipped || 0}，失败 ${s.failed || 0}`
        setTimeout(() => { if (backfillMsg.value.startsWith('✓')) backfillMsg.value = '' }, 8000)
      } else if (s.status === 'error') {
        if (backfillPollTimer) clearInterval(backfillPollTimer); backfillPollTimer = null
        backfilling.value = false
        backfillMsg.value = '补充失败: ' + (s.error || '')
      } else {
        if (backfillPollTimer) clearInterval(backfillPollTimer); backfillPollTimer = null
        backfilling.value = false
      }
    } catch {}
  }, 1500)
}

function fmtDate(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}
async function loadGenlogsInfo() {
  try {
    const d = await api('GET', '/api/admin/gen-logs/info')
    genlogsInfo.value = d
  } catch {}
}
async function scanOrphans() {
  scanning.value = true
  scanDone.value = false
  orphanMsg.value = ''
  orphans.value = []
  orphanRange.value = null
  orphanSearch.value = ''
  orphanDateFrom.value = ''
  orphanDateTo.value = ''
  const body: any = {}
  if (scanDateFrom.value) body.date_from = new Date(scanDateFrom.value + 'T00:00:00').getTime() / 1000
  if (scanDateTo.value) body.date_to = new Date(scanDateTo.value + 'T23:59:59').getTime() / 1000
  try {
    const r = await api('POST', '/api/admin/gen-logs/scan-orphans', body)
    if (!r.ok) { scanning.value = false; alert(r.error || '扫描启动失败'); return }
    pollOrphanScan()
  } catch { scanning.value = false }
}

function pollOrphanScan() {
  if (orphanPollTimer) clearInterval(orphanPollTimer)
  orphanPollTimer = setInterval(async () => {
    try {
      const s = await api('GET', '/api/admin/gen-logs/scan-orphans/status')
      if (s.status === 'running') {
        // 更新进度，不显示孤儿列表
      } else if (s.status === 'done') {
        if (orphanPollTimer) clearInterval(orphanPollTimer); orphanPollTimer = null
        scanning.value = false
        scanDone.value = true
        orphanRange.value = s.date_range || null
        loadOrphanResults()
      } else if (s.status === 'error') {
        if (orphanPollTimer) clearInterval(orphanPollTimer); orphanPollTimer = null
        scanning.value = false
        alert('扫描失败: ' + (s.error || ''))
      } else {
        if (orphanPollTimer) clearInterval(orphanPollTimer); orphanPollTimer = null
        scanning.value = false
      }
    } catch {}
  }, 1500)
}

async function loadOrphanResults() {
  try {
    let url = '/api/admin/gen-logs/scan-orphans/result'
    const params: string[] = []
    if (orphanSearch.value.trim()) params.push('login=' + encodeURIComponent(orphanSearch.value.trim()))
    if (orphanDateFrom.value) params.push('date_from=' + (new Date(orphanDateFrom.value + 'T00:00:00').getTime() / 1000))
    if (orphanDateTo.value) params.push('date_to=' + (new Date(orphanDateTo.value + 'T23:59:59').getTime() / 1000))
    if (params.length) url += '?' + params.join('&')
    const d = await api('GET', url)
    orphans.value = d.orphans || []
  } catch {}
}

async function clearOrphans() {
  if (!orphans.value.length) return
  if (!confirm(`确定删除 ${orphans.value.length} 条已无原图的生图日志？`)) return
  const i = prompt(`即将删除 ${orphans.value.length} 条生图日志，请输入"确认删除"以继续：`)
  if (i !== '确认删除') { alert('输入不匹配，已取消'); return }
  try {
    await api('POST', '/api/admin/gen-logs/delete', { ids: orphans.value.map((o: any) => o.id) })
    const cnt = orphans.value.length
    orphans.value = []
    scanDone.value = false
    orphanSearch.value = ''
    orphanDateFrom.value = ''
    orphanDateTo.value = ''
    orphanMsg.value = `✓ 已清理 ${cnt} 条孤儿记录`
    setTimeout(() => { if (orphanMsg.value.startsWith('✓')) orphanMsg.value = '' }, 4000)
  } catch (e: any) { orphanMsg.value = '删除失败: ' + e.message }
}

// 按当前孤儿筛选区间清理（原图全丢的孤儿日志 + 残留缩略图）
async function clearOrphansByRange() {
  const df = orphanDateFrom.value, dt = orphanDateTo.value
  const label = (df || dt) ? `区间 ${df || '不限'} ~ ${dt || '不限'}` : '全部扫描范围'
  if (!confirm(`确定清理【${label}】内原图已全部丢失的孤儿日志 + 残留缩略图？`)) return
  if (prompt('请输入"确认清理"以继续：') !== '确认清理') { alert('输入不匹配，已取消'); return }
  const body: any = {}
  if (df) body.date_from = new Date(df + 'T00:00:00').getTime() / 1000
  if (dt) body.date_to = new Date(dt + 'T23:59:59').getTime() / 1000
  try {
    const d = await api('POST', '/api/admin/gen-logs/delete-orphans-by-range', body)
    orphanMsg.value = `✓ ${d.message || '清理完成'}`
    orphans.value = []; orphanRange.value = null
    setTimeout(() => { if (orphanMsg.value.startsWith('✓')) orphanMsg.value = '' }, 5000)
  } catch (e: any) { orphanMsg.value = '清理失败: ' + e.message }
}

// 一键清理一周前的孤儿日志（仅原图全丢的）
async function clearOrphansWeekAgo() {
  if (!confirm('确定清理「一周前 且 原图已全部丢失」的孤儿日志 + 残留缩略图？一周内的、原图还在的记录都会保留。')) return
  if (prompt('请输入"确认清理"以继续：') !== '确认清理') { alert('输入不匹配，已取消'); return }
  try {
    const d = await api('POST', '/api/admin/gen-logs/delete-orphans-week-ago')
    orphanMsg.value = `✓ ${d.message || '清理完成'}`
    orphans.value = []; orphanRange.value = null
    loadGenlogsInfo()
    setTimeout(() => { if (orphanMsg.value.startsWith('✓')) orphanMsg.value = '' }, 5000)
  } catch (e: any) { orphanMsg.value = '清理失败: ' + e.message }
}

onMounted(() => { load(); loadGenlogsInfo() })
onUnmounted(() => { stopAuto(); if (orphanPollTimer) clearInterval(orphanPollTimer); if (backfillPollTimer) clearInterval(backfillPollTimer) })
</script>

<template>
  <div v-if="visible">
    <div class="flex flex-wrap gap-2 mb-2 items-center text-xs">
      <input v-model="search" type="text" placeholder="用户名搜索" class="border rounded px-2 py-1 text-xs w-full sm:w-24 outline-none" @keyup.enter="filter" />
      <input v-model="pathSearch" type="text" placeholder="文件名搜索" class="border rounded px-2 py-1 text-xs w-full sm:w-28 outline-none" @keyup.enter="filter" />
      <label class="text-gray-500 hidden sm:inline">日期:</label>
      <input v-model="dateFrom" type="date" class="border rounded px-2 py-1 text-xs w-full sm:w-auto outline-none" />
      <span class="text-gray-400">—</span>
      <input v-model="dateTo" type="date" class="border rounded px-2 py-1 text-xs w-full sm:w-auto outline-none" />
      <button @click="filter" class="px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs cursor-pointer border-0">筛选</button>
      <button @click="resetFilter" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">重置</button>
      <button @click="page=0;load()" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">刷新</button>
      <button @click="toggleAuto" :class="['px-2 py-1 rounded text-xs cursor-pointer border-0', autoEnabled ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-600']">自动刷新{{ autoEnabled ? '' : ': 关' }}</button>
      <input v-model.number="autoInterval" @change="stopAuto();startAuto()" type="number" min="5" max="300" class="w-12 text-xs text-center border rounded py-1 outline-none" title="刷新间隔(秒)" />
      <button @click="clearAll" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs cursor-pointer border-0">清空全部</button>
    </div>

    <!-- Orphan scan section -->
    <div class="flex flex-wrap items-center gap-2 mb-2 text-xs">
      <span class="text-gray-500 font-medium">🔍 孤儿扫描</span>
      <span v-if="genlogsInfo.min_date" class="text-gray-400">(记录范围: {{ fmtDate(genlogsInfo.min_date) }} ~ {{ fmtDate(genlogsInfo.max_date) }}, 共 {{ genlogsInfo.total }} 条)</span>
      <input v-model="scanDateFrom" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
      <span class="text-gray-400">—</span>
      <input v-model="scanDateTo" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
      <span class="text-gray-400 text-[10px]">不填=全扫</span>
      <button @click="scanOrphans" :disabled="scanning" class="px-2 py-1 bg-purple-500 text-white rounded hover:bg-purple-600 disabled:opacity-40 text-xs cursor-pointer border-0">{{ scanning ? '扫描中…' : '开始扫描' }}</button>
      <button @click="backfillThumbs" :disabled="backfilling" class="px-2 py-1 bg-teal-500 text-white rounded hover:bg-teal-600 disabled:opacity-40 text-xs cursor-pointer border-0" title="为原图还在但缩略图丢失的记录重新生成缩略图（用上方日期框限定范围，不填=全量）">{{ backfilling ? '补充中…' : '🖼 补充缩略图' }}</button>
      <button @click="clearOrphansWeekAgo" class="px-2 py-1 bg-rose-500 text-white rounded hover:bg-rose-600 text-xs cursor-pointer border-0" title="一键清理一周前且原图全丢的孤儿日志">🗓 清理一周前孤儿</button>
    </div>

    <div v-if="backfillMsg" class="mb-2 text-xs" :class="backfillMsg.startsWith('✓')?'text-green-600':(backfillMsg.startsWith('补充失败')?'text-red-500':'text-teal-600')">{{ backfillMsg }}</div>

    <div v-if="scanning" class="mb-2 text-xs text-purple-600">扫描中，请稍候…</div>
    <div v-if="orphanMsg" class="mb-2 text-xs" :class="orphanMsg.startsWith('✓')?'text-green-600':'text-red-500'">{{ orphanMsg }}</div>

    <!-- 扫描完成但无孤儿时的反馈 -->
    <div v-if="scanDone && !scanning && !orphans.length && !orphanMsg" class="mb-2 p-2 bg-green-50 border border-green-200 rounded-lg text-xs text-green-700">
      ✓ 扫描完成，未发现原图已丢失的孤儿日志
      <span v-if="orphanRange && orphanRange.count" class="text-green-600 ml-1">(分布: {{ fmtDate(orphanRange.min) }} ~ {{ fmtDate(orphanRange.max) }}，共 {{ orphanRange.count }} 条，但当前筛选下无结果)</span>
    </div>

    <!-- Orphan results -->
    <div v-if="orphans.length" class="mb-2 p-2 bg-amber-50 border border-amber-200 rounded-lg text-xs">
      <div class="flex items-center justify-between mb-2">
        <span class="text-amber-800">
          发现 <strong>{{ orphans.length }}</strong> 条已无原图的生图日志
          <span v-if="orphanRange" class="text-amber-600 ml-1">(分布: {{ fmtDate(orphanRange.min) }} ~ {{ fmtDate(orphanRange.max) }})</span>
        </span>
        <div class="flex gap-1">
          <input v-model="orphanSearch" type="text" placeholder="用户筛选" class="border rounded px-1.5 py-0.5 text-[10px] w-20 outline-none" @keyup.enter="loadOrphanResults" />
          <input v-model="orphanDateFrom" type="date" class="border rounded px-1.5 py-0.5 text-[10px] w-28 outline-none" />
          <span class="text-gray-400 self-center">—</span>
          <input v-model="orphanDateTo" type="date" class="border rounded px-1.5 py-0.5 text-[10px] w-28 outline-none" />
          <button @click="loadOrphanResults" class="px-1.5 py-0.5 bg-blue-500 text-white rounded hover:bg-blue-600 text-[10px] cursor-pointer border-0">筛选</button>
        </div>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-amber-700 text-[10px]">扫描结果缓存在内存中，刷新页面后需重新扫描</span>
        <div class="flex gap-1 shrink-0">
          <button @click="clearOrphansByRange" class="px-2 py-1 bg-orange-500 text-white rounded hover:bg-orange-600 text-xs cursor-pointer border-0" title="按上方日期区间清理原图全丢的孤儿+残留缩略图">🗂 清理此区间</button>
          <button @click="clearOrphans" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs cursor-pointer border-0">🗑 删除这些</button>
        </div>
      </div>
      <div class="mt-2 max-h-48 overflow-y-auto space-y-1">
        <div v-for="o in orphans" :key="o.id" class="flex items-center gap-2 text-[10px] bg-white/60 rounded px-2 py-1 border border-amber-100">
          <span class="text-gray-500 shrink-0">{{ fmt(o.created_at) }}</span>
          <span class="text-gray-700 shrink-0">👤 {{ o.login || '?' }}</span>
          <span class="text-gray-400 truncate">{{ (o.file_paths || []).join(', ') }}</span>
        </div>
      </div>
    </div>

    <div v-if="editMode && selected.length" class="flex gap-2 mb-2 items-center text-xs">
      <button @click="toggleAll" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">全选</button>
      <button @click="batchDelete" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs cursor-pointer border-0">🗑 删除选中 ({{ selected.length }})</button>
    </div>

    <div class="text-sm max-h-96 overflow-y-auto" :class="editMode ? '' : 'gl-log-preview'">
      <div v-if="!items.length" class="text-gray-400 text-xs py-4">暂无日志</div>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div v-for="it in items" :key="it.id" class="border border-gray-200 rounded p-2 sm:p-1 text-[10px] relative flex gap-1.5 sm:gap-1 bg-white" :class="{'bg-blue-50/30': selected.includes(it.id)}">
          <input v-if="editMode" type="checkbox" :checked="selected.includes(it.id)" @change="toggleItem(it.id)" class="absolute top-0.5 left-0.5 w-3 h-3 cursor-pointer z-10 accent-blue-500" />
          <div class="flex-1 min-w-0">
            <div class="flex justify-between items-center text-gray-400 gap-1">
              <div class="flex items-center gap-1 flex-wrap">
                <span>{{ it.created_at ? fmt(it.created_at) : '' }}</span>
                <button :data-copy-text="it.prompt||''" class="text-[8px] px-1 py-0.5 bg-pink-50 hover:bg-pink-100 text-pink-500 rounded whitespace-nowrap cursor-pointer border-0" @click="copyText(it.prompt||'', $event.target as HTMLElement)">📋正面</button>
                <button v-if="it.negative_prompt" :data-copy-text="it.negative_prompt" class="text-[8px] px-1 py-0.5 bg-rose-50 hover:bg-rose-100 text-rose-500 rounded whitespace-nowrap cursor-pointer border-0" @click="copyText(it.negative_prompt||'', $event.target as HTMLElement)">📋负面</button>
              </div>
              <span :class="it.status==='success'?'text-green-600':'text-red-600'" class="shrink-0">{{ it.status==='success'?'✓':'✗' }}</span>
            </div>
            <div class="flex justify-between gap-1">
              <span class="text-gray-700 truncate">👤 {{ it.login || it.github_id || '?' }}</span>
              <span class="text-gray-400 shrink-0 truncate">📁 {{ (it.workflow||'').split('/').pop() || '-' }}</span>
            </div>
            <div class="text-gray-500 truncate">💬 {{ (it.prompt||'').substring(0, 80) }}</div>
            <div v-if="it.negative_prompt" class="text-gray-500 truncate">⚠️ {{ it.negative_prompt.substring(0, 80) }}</div>
            <div v-if="it.status!=='success' && it.error_reason" class="flex items-center gap-1 text-red-500 truncate"><span class="truncate">❗ {{ it.error_reason }}</span><button class="text-[8px] px-1 py-0.5 bg-red-50 hover:bg-red-100 text-red-500 rounded shrink-0 cursor-pointer border-0" @click="copyText(it.error_reason||'', $event.target as HTMLElement)">📋</button></div>
          </div>
          <a v-if="it.images && it.images[0]" :href="it.images[0]" class="lb-thumb flex-shrink-0 self-stretch w-16 sm:w-14" data-genlog="1"
            :data-path="it.file_paths?.[0] || ''" :data-mtime="it.created_at || 0" :data-ip="it.client_ip || ''" :data-author="it.login || it.github_id || ''">
            <img :src="it.images[0]" loading="lazy" class="h-full w-full object-cover rounded border border-gray-200 hover:ring-1 hover:ring-blue-400" />
          </a>
        </div>
      </div>
    </div>

    <div class="flex items-center gap-2 mt-2 text-xs">
      <span class="text-gray-500">{{ statusText }}</span>
      <span class="text-gray-400 ml-auto flex items-center gap-1">
        <button @click="page--;load()" :disabled="page<=0" class="text-blue-600 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent text-xs">上一页</button>
        <span v-for="p in pageNumbers" :key="p">
          <span v-if="p===-1" class="mx-1 text-gray-400">...</span>
          <button v-else @click="page=p;load()" :class="['mx-1 text-xs cursor-pointer border-0 bg-transparent', p===page ? 'font-bold text-gray-800' : 'text-blue-600 hover:underline']">{{ p+1 }}</button>
        </span>
        <button @click="page++;load()" :disabled="page>=totalPages-1" class="text-blue-600 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent text-xs">下一页</button>
      </span>
    </div>
  </div>
</template>