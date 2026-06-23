<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, fmt, copyText } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([]), total = ref(0), page = ref(0), statusText = ref('')
const search = ref(''), pathSearch = ref(''), dateFrom = ref(''), dateTo = ref('')
const autoEnabled = ref(false), autoInterval = ref(10), editMode = ref(false), selected = ref<string[]>([])
const bfRunning = ref(false)
const bfResult = ref('')
const bfTotal = ref(0)
const bfProcessed = ref(0)
const bfFilled = ref(0)
const bfSkipped = ref(0)
let bfPollTimer: ReturnType<typeof setInterval> | null = null
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
    let u = `/api/admin/deletion-log?limit=${PAGE_SIZE}&offset=${page.value * PAGE_SIZE}`
    if (search.value) u += '&search=' + encodeURIComponent(search.value)
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
function toggleAll() { selected.value = selected.value.length === items.value.length ? [] : items.value.map(d => d.path) }
function toggleItem(path: string) { selected.value.includes(path) ? selected.value = selected.value.filter(x => x !== path) : selected.value = [...selected.value, path] }

async function batchDelete() {
  if (!selected.value.length) return
  if (!confirm(`确定清理选中的 ${selected.value.length} 条删除记录？`)) return
  const i = prompt(`请输入"确认删除删除记录"以继续清理 ${selected.value.length} 条记录：`)
  if (i !== '确认删除删除记录') { alert('输入不匹配，已取消'); return }
  await api('POST', '/api/admin/deletion-log/clear', { paths: selected.value })
  selected.value = []; page.value = 0; load()
}

async function clearRecord(path: string) {
  if (!confirm('确认清理此条删除记录？')) return
  await api('POST', '/api/admin/deletion-log/clear', { path })
  load()
}

async function clearAll() {
  const hasDate = dateFrom.value || dateTo.value
  if (!confirm(hasDate ? '确认清空当前日期范围内的删除记录？' : '确认清空全部删除记录？')) return
  const i = prompt('请输入"确认删除删除记录"以继续：')
  if (i !== '确认删除删除记录') { alert('输入不匹配，已取消'); return }
  const body: any = {}
  if (dateFrom.value) body.date_from = new Date(dateFrom.value + 'T00:00:00').getTime() / 1000
  if (dateTo.value) body.date_to = new Date(dateTo.value + 'T23:59:59').getTime() / 1000
  await api('POST', '/api/admin/deletion-log/clear', body)
  page.value = 0; load()
}

async function backfillThumbs() {
  if (!confirm('将逐条检查删除记录中缺失的缩略图，存在原图则补生成，原图已不存在则跳过。确定执行？')) return
  bfRunning.value = true
  bfResult.value = ''
  bfTotal.value = 0
  bfProcessed.value = 0
  bfFilled.value = 0
  bfSkipped.value = 0
  try {
    await api('POST', '/api/admin/gc/backfill-thumbnails')
    pollBackfillStatus()
  } catch (e: any) {
    bfResult.value = '启动失败: ' + e.message
    bfRunning.value = false
  }
}
async function pollBackfillStatus() {
  if (bfPollTimer) clearInterval(bfPollTimer)
  bfPollTimer = setInterval(async () => {
    try {
      const s = await api('GET', '/api/admin/gc/backfill-thumbnails/status')
      if (s.status === 'running') {
        bfTotal.value = s.total || 0
        bfProcessed.value = s.processed || 0
        bfFilled.value = s.filled || 0
        bfSkipped.value = s.skipped || 0
      } else if (s.status === 'done') {
        if (bfPollTimer) clearInterval(bfPollTimer); bfPollTimer = null
        bfRunning.value = false
        bfTotal.value = s.total || 0
        bfFilled.value = s.filled || 0
        bfSkipped.value = s.skipped || 0
        bfResult.value = `完成：已补 ${s.filled || 0} 张，跳过 ${s.skipped || 0} 张`
        load()
      } else if (s.status === 'error') {
        if (bfPollTimer) clearInterval(bfPollTimer); bfPollTimer = null
        bfRunning.value = false
        bfResult.value = '任务失败: ' + (s.error || '未知错误')
      } else {
        if (bfPollTimer) clearInterval(bfPollTimer); bfPollTimer = null
        bfRunning.value = false
        bfResult.value = '任务已结束'
      }
    } catch { }
  }, 1500)
}

onMounted(load)
onUnmounted(() => { stopAuto(); if (bfPollTimer) clearInterval(bfPollTimer) })
</script>

<template>
  <div v-if="visible">
    <p class="text-xs text-gray-500 mb-2">用户或管理员删除的图片存档，可查看缩略图确认后清理。最多保留 100000 条。</p>

    <div class="flex flex-wrap gap-2 mb-2 items-center text-xs">
      <input v-model="search" type="text" placeholder="用户名搜索" class="border rounded px-2 py-1 text-xs w-28 outline-none" @keyup.enter="filter" />
      <input v-model="pathSearch" type="text" placeholder="图片名搜索" class="border rounded px-2 py-1 text-xs w-28 outline-none" @keyup.enter="filter" />
      <label class="text-gray-500">日期:</label>
      <input v-model="dateFrom" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
      <span class="text-gray-400">—</span>
      <input v-model="dateTo" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
      <button @click="filter" class="px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs cursor-pointer border-0">筛选</button>
      <button @click="resetFilter" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">重置</button>
      <button @click="page=0;load()" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">刷新</button>
      <button @click="toggleAuto" :class="['px-2 py-1 rounded text-xs cursor-pointer border-0', autoEnabled ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-600']">自动刷新{{ autoEnabled ? '' : ': 关' }}</button>
      <input v-model.number="autoInterval" @change="stopAuto();startAuto()" type="number" min="2" max="300" class="w-12 text-xs text-center border rounded py-1 outline-none" title="刷新间隔(秒)" />
      <button @click="toggleEdit" :class="['px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0', editMode ? 'bg-orange-500 text-white' : '']">{{ editMode ? '退出编辑' : '编辑' }}</button>
      <button @click="clearAll" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs cursor-pointer border-0">清空全部</button>
      <button @click="backfillThumbs" :disabled="bfRunning" class="px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-40 text-xs cursor-pointer border-0">🔍 补缩略图</button>
      <span v-if="bfRunning && bfTotal" class="text-blue-500">{{ bfProcessed }}/{{ bfTotal }} 已补{{ bfFilled }} 跳过{{ bfSkipped }}</span>
      <span v-if="bfRunning && !bfTotal" class="text-blue-500">启动中…</span>
      <span v-if="bfResult" class="text-xs" :class="bfResult.startsWith('完成')?'text-green-600':'text-red-500'">{{ bfResult }}</span>
    </div>

    <div v-if="editMode && selected.length" class="flex gap-2 mb-2 items-center text-xs">
      <button @click="toggleAll" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">全选</button>
      <button @click="batchDelete" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs cursor-pointer border-0">🗑 删除选中 ({{ selected.length }})</button>
    </div>

    <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2" :class="editMode ? '' : 'del-log-preview'">
      <div v-if="!items.length" class="text-gray-400 text-xs col-span-full">暂无删除记录</div>
      <div v-for="d in items" :key="d.path" class="border rounded p-1 bg-red-50 relative">
        <input v-if="editMode" type="checkbox" :checked="selected.includes(d.path)" @change="toggleItem(d.path)" class="absolute top-0.5 left-0.5 w-3 h-3 cursor-pointer z-10 accent-blue-500" />
        <img v-if="d.thumb_url" :src="d.thumb_url" loading="lazy" class="lb-thumb w-full aspect-square object-cover rounded bg-gray-100 cursor-pointer"
          :data-path="d.path" :data-del-thumb="d.thumb_url" :data-mtime="d.deleted_at || 0" :data-ip="d.creator_ip || ''" :data-author="d.creator_login || d.deleted_by_login || ''" />
        <div v-else class="w-full aspect-square rounded bg-gray-200 flex items-center justify-center text-gray-400 text-xs">无缩略图</div>
        <div class="text-[9px] mt-1 text-gray-500">👤 删除: {{ d.deleted_by_login || d.login || '?' }}</div>
        <div v-if="d.creator_login || d.creator_ip" class="text-[9px] text-gray-500">🎨 {{ d.creator_login ? d.creator_login + (d.creator_ip ? ' ('+d.creator_ip+')' : '') : 'IP: '+d.creator_ip }}</div>
        <div class="text-[9px] text-gray-400">{{ d.deleted_at ? fmt(d.deleted_at) : d.time ? fmt(d.time) : '' }}</div>
        <div class="text-[9px] text-gray-400 truncate">📁 {{ d.path?.split('/').pop() || d.path }}</div>
        <button v-if="!editMode" @click="clearRecord(d.path)" class="mt-1 w-full text-[10px] bg-white border border-red-300 text-red-500 rounded px-1 py-0.5 hover:bg-red-100 cursor-pointer">清理记录</button>
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