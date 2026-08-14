<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, fmt, fmtShort } from './useAdminApi'
import { dayStartTs, nextDayStartTs } from './dateRange'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([])
const total = ref(0)
const loaded = ref(0)
const pageSize = 30
const page = ref(0)
const selected = ref<Set<string>>(new Set())
const loading = ref(false)
const lastClickedIndex = ref(-1)
const rangePicking = ref(false)
const rangeStartIndex = ref(-1)
const editMode = ref(false)
// 请求序号：防止快速翻页/删除回退时旧请求覆盖新结果
let loadSeq = 0

const shown = computed(() => items.value.length)
const allSelected = computed(() => items.value.length > 0 && selected.value.size === items.value.length)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const pageWindow = computed(() => {
  const tp = totalPages.value
  if (tp <= 1) return []
  const p = page.value
  const s = Math.max(0, p - 2)
  const e = Math.min(tp - 1, p + 2)
  const set = new Set<number>()
  if (p > 0) set.add(p - 1)
  for (let i = s; i <= e; i++) set.add(i)
  if (p < tp - 1) set.add(p + 1)
  const items: (number | 'left' | 'right')[] = []
  const sorted = Array.from(set).sort((a, b) => a - b)
  if (!sorted.length) return items
  items.push(sorted[0])
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] - sorted[i - 1] > 1) items.push('left')
    items.push(sorted[i])
  }
  return items
})

// Filter
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterCreator = ref('')
const filtering = ref(false)
const nameSearch = ref('')

async function loadImages(reset = true) {
  const seq = ++loadSeq
  loading.value = true
  try {
    if (reset) { items.value = []; selected.value.clear(); page.value = 0; lastClickedIndex.value = -1; rangePicking.value = false; rangeStartIndex.value = -1 }
    let u = `/api/admin/images?limit=${pageSize}&offset=${page.value * pageSize}`
    if (nameSearch.value.trim()) u += '&name=' + encodeURIComponent(nameSearch.value.trim())
    const r = await api('GET', u)
    if (seq !== loadSeq) return  // 丢弃过期结果
    items.value = r.items || []
    total.value = r.total || 0
    loaded.value = items.value.length
  } catch (e: any) {
    if (reset) items.value = []
  } finally { if (seq === loadSeq) loading.value = false }
}

function goPage(p: number) {
  if (p < 0 || p >= totalPages.value || p === page.value) return
  page.value = p
  loadImages(false)
}

function searchByName() { loadImages(true) }
function resetSearch() { nameSearch.value = ''; loadImages(true) }

async function deleteByFilter() {
  const body: any = {}
  if (filterDateFrom.value) body.date_from = dayStartTs(filterDateFrom.value)
  if (filterDateTo.value) body.date_to = nextDayStartTs(filterDateTo.value)
  if (filterCreator.value.trim()) body.creator = filterCreator.value.trim()
  if (!body.date_from && !body.date_to && !body.creator) { alert('请至少设置一个筛选条件'); return }
  const desc = [body.date_from ? '日期起' : '', body.date_to ? '日期止' : '', body.creator ? '创建者: ' + body.creator : ''].filter(Boolean).join(', ')
  if (!confirm(`确定按条件删除匹配的图片？筛选条件: ${desc}`)) return
  const i = prompt(`即将删除匹配条件的图片，请输入"确认删除"以继续：`)
  if (i !== '确认删除') { alert('输入不匹配，已取消'); return }
  filtering.value = true
  try {
    const r = await api('POST', '/api/admin/images/delete-by-query', body)
    if (r.marked > 0) alert(`已标记删除 ${r.marked} 张图片`)
    else alert('没有匹配的图片')
    loadImages(true)
  } catch (e: any) { alert('操作失败: ' + e.message) }
  finally { filtering.value = false }
}

function toggleEdit() {
  editMode.value = !editMode.value
  if (!editMode.value) {
    selected.value.clear()
    lastClickedIndex.value = -1
    rangePicking.value = false
    rangeStartIndex.value = -1
  }
}

function onThumbClick(img: any, i: number, e: Event) {
  // 编辑模式：阻止冒泡，只勾选不开灯箱；非编辑模式：不处理（冒泡触发 AdminLightbox 开灯箱）
  if (editMode.value) {
    e.stopPropagation()
    toggleItem(img.path, i, (e as MouseEvent).shiftKey)
  }
}

function toggleItem(path: string, index?: number, shiftKey = false) {
  const s = new Set(selected.value)
  if (rangePicking.value) {
    if (rangeStartIndex.value < 0) {
      rangeStartIndex.value = index ?? 0
      s.add(path)
      selected.value = s
      return
    }
    const [from, to] = rangeStartIndex.value < (index ?? 0)
      ? [rangeStartIndex.value, index ?? 0]
      : [index ?? 0, rangeStartIndex.value]
    for (let i = from; i <= to; i++) {
      s.add(items.value[i].path)
    }
    rangePicking.value = false
    rangeStartIndex.value = -1
    selected.value = s
    return
  }

  if (shiftKey && lastClickedIndex.value >= 0 && index !== undefined && lastClickedIndex.value !== index) {
    const [from, to] = lastClickedIndex.value < index
      ? [lastClickedIndex.value, index]
      : [index, lastClickedIndex.value]
    for (let i = from; i <= to; i++) {
      s.add(items.value[i].path)
    }
  } else {
    if (s.has(path)) s.delete(path); else s.add(path)
    if (index !== undefined) lastClickedIndex.value = index
  }
  selected.value = s
}

function toggleAll() {
  if (allSelected.value) { selected.value.clear(); lastClickedIndex.value = -1; rangePicking.value = false; rangeStartIndex.value = -1 }
  else selected.value = new Set(items.value.map(i => i.path))
}

function startRangePick() {
  rangePicking.value = true
  rangeStartIndex.value = -1
}

async function deleteSelected() {
  if (!selected.value.size) return
  if (!confirm(`确定删除选中的 ${selected.value.size} 张图片？`)) return
  const paths = Array.from(selected.value)
  try {
    const r = await api('POST', '/api/admin/mark_delete_batch', { paths })
    const marked = r.marked ?? paths.length
    const failed = Math.max(0, paths.length - marked)
    const pathSet = new Set(paths)
    items.value = items.value.filter(i => !pathSet.has(i.path))
    selected.value.clear()
    lastClickedIndex.value = -1
    rangePicking.value = false
    rangeStartIndex.value = -1
    total.value = Math.max(0, total.value - paths.length)
    loaded.value = items.value.length
    // 翻页后：当前页删空且非第一页则回退一页；否则刷新当前页（页码可能因总数减少超界）
    if (!items.value.length && page.value > 0) {
      page.value = Math.min(page.value - 1, Math.max(0, Math.ceil(total.value / pageSize) - 1))
      await loadImages(false)
    } else if (page.value >= totalPages.value && page.value > 0) {
      page.value = totalPages.value - 1
      await loadImages(false)
    } else {
      await loadImages(false)
    }
    alert(`删除完成：成功标记 ${marked} 张，失败 ${failed} 张`)
  } catch (e: any) { alert('删除失败: ' + e.message) }
}

function creatorInfo(item: any): string {
  return [item.creator_ip, item.creator_login, item.creator_email].filter(Boolean).join(' | ')
}

onMounted(() => loadImages(true))
</script>

<template>
  <div v-if="visible" class="bg-white rounded shadow p-4 mb-4">
    <div class="flex items-center justify-between mb-2 gap-2 flex-wrap">
      <div class="flex items-center gap-1">
        <input v-model="nameSearch" type="text" placeholder="图片名搜索" class="border rounded px-2 py-1 text-xs w-32 outline-none" @keyup.enter="searchByName" />
        <button @click="searchByName" class="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 cursor-pointer border-0">搜索</button>
        <button @click="resetSearch" class="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">重置</button>
      </div>
      <div class="flex gap-2">
        <button @click="toggleEdit" :class="['px-2 py-1 rounded cursor-pointer border-0 text-xs', editMode ? 'bg-orange-500 text-white' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">{{ editMode ? '✕ 退出编辑' : '☑ 编辑' }}</button>
        <button v-if="editMode" @click="toggleAll" class="px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0 text-xs">{{ allSelected ? '取消全选' : '全选' }}</button>
        <button v-if="editMode && !rangePicking" @click="startRangePick" class="px-2 py-1 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 cursor-pointer border-0 text-xs">📏 区间选择</button>
        <button v-else-if="editMode && rangePicking" @click="rangePicking=false;rangeStartIndex=-1" class="px-2 py-1 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0 text-xs">✕ 取消区间</button>
        <button v-if="editMode && selected.size > 0" @click="deleteSelected" class="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0 text-xs">&#x1F5D1; 删除选中 ({{ selected.size }})</button>
        <button @click="loadImages(true)" class="px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0 text-xs">刷新</button>
      </div>
    </div>

    <!-- Range Pick Hint -->
    <div v-if="rangePicking" class="text-xs text-orange-500 mb-2">
      {{ rangeStartIndex < 0 ? '👉 点击第一张图' : '👉 点击最后一张图' }}
    </div>

    <!-- Filter Bar -->
    <div class="flex flex-wrap items-center gap-2 mb-3 p-2 bg-gray-50 rounded text-xs">
      <span class="text-gray-500">筛选删除:</span>
      <input v-model="filterDateFrom" type="date" class="border rounded px-1 py-0.5 text-xs outline-none" title="起始日期" />
      <span class="text-gray-400">~</span>
      <input v-model="filterDateTo" type="date" class="border rounded px-1 py-0.5 text-xs outline-none" title="截止日期" />
      <input v-model="filterCreator" type="text" placeholder="创建者(login/IP/email)" class="border rounded px-2 py-0.5 text-xs w-40 outline-none" />
      <button @click="deleteByFilter" :disabled="filtering" class="px-2 py-0.5 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0 text-xs disabled:opacity-50">{{ filtering ? '处理中...' : '&#x1F5D1; 删除匹配' }}</button>
    </div>

    <div>
      <div v-if="!items.length" class="text-center text-gray-400 text-sm py-8">暂无图片</div>
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
        <div v-for="(img, i) in items" :key="img.path" class="relative border rounded p-1 bg-gray-50" :class="{'ring-2 ring-blue-400': selected.has(img.path)}">
          <input v-if="editMode" type="checkbox" :checked="selected.has(img.path)" @change="toggleItem(img.path, i, ($event as MouseEvent).shiftKey)" @click.stop class="absolute top-0.5 left-0.5 w-4 h-4 cursor-pointer z-10" />
          <img :src="'/api/output/thumb?path=' + encodeURIComponent(img.path || '')" loading="lazy" decoding="async"
            class="lb-thumb w-full aspect-square object-cover rounded bg-white cursor-pointer"
            :class="editMode ? '' : 'cursor-zoom-in'"
            :data-path="img.path" :data-mtime="img.mtime || ''" :data-ip="img.creator_ip || ''"
            @click="onThumbClick(img, i, $event)" />
          <div class="text-[9px] text-gray-500 mt-0.5 truncate" :title="img.path">{{ img.path.split('/').pop() }}</div>
          <div class="text-[8px] text-gray-400 truncate">{{ creatorInfo(img) || '\u00A0' }}</div>
          <div class="text-[8px] text-gray-400" v-if="img.mtime">{{ fmt(img.mtime) }}</div>
        </div>
      </div>
      <!-- 翻页 -->
      <div v-if="items.length && totalPages > 1 && !editMode" class="flex items-center justify-center gap-2 mt-3 text-xs">
        <button @click="goPage(page - 1)" :disabled="page <= 0"
          class="px-2.5 py-1 bg-gray-100 border border-gray-200 rounded text-gray-600 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">上一页</button>
        <template v-for="item in pageWindow" :key="typeof item === 'number' ? item : item">
          <span v-if="item === 'left' || item === 'right'" class="text-gray-400 px-1">...</span>
          <button v-else @click="goPage(item as number)" :disabled="item === page"
            :class="['px-2.5 py-1 rounded cursor-pointer border', item === page ? 'bg-blue-500 text-white border-blue-500' : 'bg-gray-100 border-gray-200 text-gray-600 hover:bg-gray-200']">{{ (item as number) + 1 }}</button>
        </template>
        <button @click="goPage(page + 1)" :disabled="page >= totalPages - 1"
          class="px-2.5 py-1 bg-gray-100 border border-gray-200 rounded text-gray-600 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">下一页</button>
        <span class="text-gray-400 ml-1">{{ page + 1 }} / {{ totalPages }} 页 · 共 {{ total }} 张</span>
      </div>
    </div>
  </div>
</template>