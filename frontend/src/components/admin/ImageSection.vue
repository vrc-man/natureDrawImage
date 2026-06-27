<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, fmt, fmtShort } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([])
const total = ref(0)
const loaded = ref(0)
const pageSize = 30
const selected = ref<Set<string>>(new Set())
const loading = ref(false)
const lastClickedIndex = ref(-1)
const rangePicking = ref(false)
const rangeStartIndex = ref(-1)

const shown = computed(() => items.value.length)
const allSelected = computed(() => items.value.length > 0 && selected.value.size === items.value.length)

// Filter
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterCreator = ref('')
const filtering = ref(false)
const nameSearch = ref('')

async function loadImages(reset = true) {
  if (loading.value && !reset) return
  loading.value = true
  try {
    if (reset) { items.value = []; selected.value.clear(); loaded.value = 0; lastClickedIndex.value = -1; rangePicking.value = false; rangeStartIndex.value = -1 }
    let u = `/api/admin/images?limit=${pageSize}&offset=${loaded.value}`
    if (nameSearch.value.trim()) u += '&name=' + encodeURIComponent(nameSearch.value.trim())
    const r = await api('GET', u)
    const newItems = r.items || []
    items.value.push(...newItems)
    total.value = r.total || 0
    loaded.value = items.value.length
  } catch (e: any) {
    if (reset) items.value = []
  } finally { loading.value = false }
}

function searchByName() { loadImages(true) }
function resetSearch() { nameSearch.value = ''; loadImages(true) }

async function deleteByFilter() {
  const body: any = {}
  if (filterDateFrom.value) body.date_from = new Date(filterDateFrom.value + 'T00:00:00').getTime() / 1000
  if (filterDateTo.value) body.date_to = new Date(filterDateTo.value + 'T23:59:59').getTime() / 1000
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

function toggleItem(path: string, index?: number, shiftKey = false) {
  const s = new Set(selected.value)

  // 区间选择模式
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
    await api('POST', '/api/admin/mark_delete_batch', { paths })
    const pathSet = new Set(paths)
    items.value = items.value.filter(i => !pathSet.has(i.path))
    selected.value.clear()
    lastClickedIndex.value = -1
    rangePicking.value = false
    rangeStartIndex.value = -1
    total.value = Math.max(0, total.value - paths.length)
    loaded.value = items.value.length
    if (!items.value.length && loaded.value < pageSize && loaded.value < total.value && total.value > 0) await loadImages(false)
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
        <button @click="toggleAll" class="text-xs px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0">{{ allSelected ? '取消全选' : '全选' }}</button>
        <button v-if="!rangePicking" @click="startRangePick" class="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 cursor-pointer border-0">📏 区间选择</button>
        <button v-else @click="rangePicking=false;rangeStartIndex=-1" class="text-xs px-2 py-1 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0">✕ 取消区间</button>
        <button v-if="selected.size > 0" @click="deleteSelected" class="text-xs px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0">&#x1F5D1; 删除选中 ({{ selected.size }})</button>
        <button @click="loadImages(true)" class="text-xs px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0">刷新</button>
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
          <input type="checkbox" :checked="selected.has(img.path)" @change="toggleItem(img.path, i, $event.shiftKey)" class="absolute top-0.5 left-0.5 w-4 h-4 cursor-pointer z-10" />
          <img :src="'/api/output/thumb?path=' + encodeURIComponent(img.path || '')" loading="lazy" decoding="async"
            class="lb-thumb w-full aspect-square object-cover rounded bg-white cursor-pointer" @click="toggleItem(img.path, i, $event.shiftKey)"
            :data-path="img.path" :data-mtime="img.mtime || ''" :data-ip="img.creator_ip || ''" />
          <div class="text-[9px] text-gray-500 mt-0.5 truncate" :title="img.path">{{ img.path.split('/').pop() }}</div>
          <div class="text-[8px] text-gray-400 truncate">{{ creatorInfo(img) || '\u00A0' }}</div>
          <div class="text-[8px] text-gray-400" v-if="img.mtime">{{ fmt(img.mtime) }}</div>
        </div>
      </div>
      <div class="mt-3 text-center">
        <button v-if="loaded < total" @click="loadImages(false)" :disabled="loading"
          class="text-sm px-4 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 cursor-pointer border-0 disabled:opacity-50">
          {{ loading ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </div>
  </div>
</template>