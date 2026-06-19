<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, fmt, copyText } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([]), total = ref(0), page = ref(0), statusText = ref('')
const search = ref(''), dateFrom = ref(''), dateTo = ref('')
const autoEnabled = ref(false), autoInterval = ref(30), editMode = ref(false), selected = ref<number[]>([])
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
function resetFilter() { search.value = ''; dateFrom.value = ''; dateTo.value = ''; page.value = 0; load() }

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

onMounted(load)
onUnmounted(() => stopAuto())
</script>

<template>
  <div v-if="visible">
    <div class="flex flex-wrap gap-2 mb-2 items-center text-xs">
      <input v-model="search" type="text" placeholder="用户名搜索" class="border rounded px-2 py-1 text-xs w-28 outline-none" @keyup.enter="filter" />
      <label class="text-gray-500">日期:</label>
      <input v-model="dateFrom" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
      <span class="text-gray-400">—</span>
      <input v-model="dateTo" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
      <button @click="filter" class="px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs cursor-pointer border-0">筛选</button>
      <button @click="resetFilter" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">重置</button>
      <button @click="toggleAuto" :class="['px-2 py-1 rounded text-xs cursor-pointer border-0', autoEnabled ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-600']">自动刷新{{ autoEnabled ? '' : ': 关' }}</button>
      <input v-model.number="autoInterval" @change="stopAuto();startAuto()" type="number" min="5" max="300" class="w-12 text-xs text-center border rounded py-1 outline-none" title="刷新间隔(秒)" />
    </div>

    <div v-if="editMode && selected.length" class="flex gap-2 mb-2 items-center text-xs">
      <button @click="toggleAll" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">全选</button>
      <button @click="batchDelete" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs cursor-pointer border-0">🗑 删除选中 ({{ selected.length }})</button>
    </div>

    <div class="text-sm max-h-96 overflow-y-auto" :class="editMode ? '' : 'gl-log-preview'">
      <div v-if="!items.length" class="text-gray-400 text-xs py-4">暂无日志</div>
      <div v-else class="grid grid-cols-2 gap-2">
        <div v-for="it in items" :key="it.id" class="border border-gray-200 rounded p-1 text-[10px] relative flex gap-1 bg-white" :class="{'bg-blue-50/30': selected.includes(it.id)}">
          <input v-if="editMode" type="checkbox" :checked="selected.includes(it.id)" @change="toggleItem(it.id)" class="absolute top-0.5 left-0.5 w-3 h-3 cursor-pointer z-10 accent-blue-500" />
          <div class="flex-1 min-w-0">
            <div class="flex justify-between items-center text-gray-400">
              <div class="flex items-center gap-1">
                <span>{{ it.created_at ? fmt(it.created_at) : '' }}</span>
                <button :data-copy-text="it.prompt||''" class="text-[8px] px-1 py-0.5 bg-pink-50 hover:bg-pink-100 text-pink-500 rounded whitespace-nowrap cursor-pointer border-0" @click="copyText(it.prompt||'', $event.target as HTMLElement)">📋正面</button>
                <button v-if="it.negative_prompt" :data-copy-text="it.negative_prompt" class="text-[8px] px-1 py-0.5 bg-rose-50 hover:bg-rose-100 text-rose-500 rounded whitespace-nowrap cursor-pointer border-0" @click="copyText(it.negative_prompt||'', $event.target as HTMLElement)">📋负面</button>
              </div>
              <span :class="it.status==='success'?'text-green-600':'text-red-600'" class="shrink-0">{{ it.status==='success'?'✓':'✗' }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-700">👤 {{ it.login || it.github_id || '?' }}</span>
              <span class="text-gray-400 shrink-0">📁 {{ (it.workflow||'').split('/').pop() || '-' }}</span>
            </div>
            <div class="text-gray-500 truncate">💬 {{ (it.prompt||'').substring(0, 80) }}</div>
            <div v-if="it.negative_prompt" class="text-gray-500 truncate">⚠️ {{ it.negative_prompt.substring(0, 80) }}</div>
            <div v-if="it.status!=='success' && it.error_reason" class="flex items-center gap-1 text-red-500 truncate"><span>❗ {{ it.error_reason }}</span><button class="text-[8px] px-1 py-0.5 bg-red-50 hover:bg-red-100 text-red-500 rounded shrink-0 cursor-pointer border-0" @click="copyText(it.error_reason||'', $event.target as HTMLElement)">📋</button></div>
          </div>
          <a v-if="it.images && it.images[0]" :href="it.images[0]" class="lb-thumb flex-shrink-0 self-stretch w-14" data-genlog="1">
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