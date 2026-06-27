<script setup lang="ts">
import { ref } from 'vue'
import { loadMyImages, deleteMyImage, deleteMyImages, deleteAllMyImages } from '@/api/endpoints'
import { useLightbox, type LbItem } from '@/composables/useLightbox'

const { open } = useLightbox()
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const pageSize = 30
const selectMode = ref(false)
const selected = ref<Set<string>>(new Set())
const lastClickedIndex = ref(-1)
const rangePicking = ref(false)
const rangeStartIndex = ref(-1)

async function load(reset = false) {
  if (loading.value) return
  loading.value = true
  try {
    if (reset) { items.value = []; selected.value = new Set() }
    const d = await loadMyImages({ offset: items.value.length, limit: pageSize })
    items.value.push(...(d.items || []))
    total.value = d.total || 0
  } catch {}
  loading.value = false
}

async function del(path: string) {
  if (!confirm('确定要删除这张作品吗？')) return
  try {
    await deleteMyImage(path)
    items.value = items.value.filter((i: any) => i.path !== path)
    total.value = Math.max(0, total.value - 1)
    selected.value.delete(path)
  } catch {}
}

function toggleSelect(path: string, index: number, shiftKey = false) {
  const s = new Set(selected.value)

  // 区间选择模式（手机）：先点起点，再点终点
  if (rangePicking.value) {
    if (rangeStartIndex.value < 0) {
      rangeStartIndex.value = index
      s.add(path)
      selected.value = s
      return
    }
    const [from, to] = rangeStartIndex.value < index
      ? [rangeStartIndex.value, index]
      : [index, rangeStartIndex.value]
    for (let i = from; i <= to; i++) {
      s.add(items.value[i].path)
    }
    rangePicking.value = false
    rangeStartIndex.value = -1
    selected.value = s
    return
  }

  if (shiftKey && lastClickedIndex.value >= 0 && lastClickedIndex.value !== index) {
    const [from, to] = lastClickedIndex.value < index
      ? [lastClickedIndex.value, index]
      : [index, lastClickedIndex.value]
    for (let i = from; i <= to; i++) {
      s.add(items.value[i].path)
    }
  } else {
    s.has(path) ? s.delete(path) : s.add(path)
    lastClickedIndex.value = index
  }
  selected.value = s
}

function startRangePick() {
  rangePicking.value = true
  rangeStartIndex.value = -1
}

function toggleSelectAll() {
  if (selected.value.size === items.value.length) {
    selected.value = new Set()
  } else {
    selected.value = new Set(items.value.map((i: any) => i.path))
  }
}

async function deleteSelected() {
  if (!selected.value.size) return
  if (!confirm(`确定删除选中的 ${selected.value.size} 张作品？`)) return
  const i = prompt(`即将删除选中的 ${selected.value.size} 张图片，请输入"确认删除这些图片"以继续：`)
  if (i !== '确认删除这些图片') { alert('输入不匹配，已取消'); return }
  const paths = Array.from(selected.value)
  try { await deleteMyImages(paths) } catch {}
  items.value = items.value.filter((i: any) => !paths.includes(i.path))
  total.value = Math.max(0, total.value - paths.length)
  selected.value = new Set()
}

async function deleteAll() {
  if (!total.value) return
  if (!confirm(`确定删除全部 ${total.value} 张作品？`)) return
  const i = prompt(`即将删除全部 ${total.value} 张作品，请输入"确认全部删除图片"以继续：`)
  if (i !== '确认全部删除图片') { alert('输入不匹配，已取消'); return }
  try { await deleteAllMyImages() } catch {}
  items.value = []
  total.value = 0
  selected.value = new Set()
}

function fmtTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
function openLightbox(index: number) {
  const lbItems: LbItem[] = items.value.map((img: any) => ({
    url: img.url || `/api/output/file?path=${encodeURIComponent(img.path || '')}`,
    title: img.filename || img.path?.split('/').pop(),
    path: img.path,
    filename: img.filename || img.path?.split('/').pop(),
    time: img.time ? fmtTime(img.time) : '',
  }))
  open(lbItems, index)
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) { selected.value = new Set(); lastClickedIndex.value = -1; rangePicking.value = false; rangeStartIndex.value = -1 }
}

defineExpose({ load, items, total })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs text-gray-400">共 {{ total }} 张</span>
      <div class="flex items-center gap-2">
        <button v-if="selectMode && selected.size" @click="deleteSelected" class="text-xs px-2 py-0.5 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0">🗑 删除选中 ({{ selected.size }})</button>
        <button v-if="total && !selectMode" @click="deleteAll" class="text-xs px-2 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0">删除全部</button>
        <button @click="toggleSelectMode" :class="['text-xs px-2 py-0.5 rounded cursor-pointer border-0', selectMode ? 'bg-blue-100 text-blue-600' : 'bg-gray-200 text-gray-600']">{{ selectMode ? '退出选择' : '选择' }}</button>
        <button @click="load(true)" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
      </div>
    </div>

    <!-- Select All Bar -->
    <div v-if="selectMode && items.length" class="flex items-center gap-2 mb-2 text-xs">
      <button @click="toggleSelectAll" class="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">{{ selected.size === items.length ? '取消全选' : '全选' }}</button>
      <button v-if="!rangePicking" @click="startRangePick" class="px-2 py-0.5 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 cursor-pointer border-0">📏 区间选择</button>
      <button v-else @click="rangePicking=false;rangeStartIndex=-1" class="px-2 py-0.5 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0">✕ 取消区间</button>
      <span v-if="rangePicking" class="text-orange-500">
        {{ rangeStartIndex < 0 ? '👉 点击第一张图' : '👉 点击最后一张图' }}
      </span>
      <span v-else class="text-gray-400">Shift+点击也可区间选择</span>
    </div>

    <div v-if="items.length" id="myworks-gallery" class="grid grid-cols-3 sm:grid-cols-4 gap-2">
      <div v-for="(img, i) in items" :key="img.path || i" class="relative group" :class="{'ring-2 ring-blue-400 rounded-lg': selected.has(img.path)}">
        <input v-if="selectMode" type="checkbox" :checked="selected.has(img.path)" @change="toggleSelect(img.path, i, $event.shiftKey)" class="absolute top-1 left-1 w-4 h-4 z-10 cursor-pointer accent-blue-500" />
        <div class="relative bg-gray-100 rounded-lg overflow-hidden">
          <div class="aspect-square flex items-center justify-center">
            <svg v-if="!img._loaded" class="animate-spin h-5 w-5 text-pink-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
          </div>
          <img :src="img.thumb || img.url || '/api/output/file?path=' + encodeURIComponent(img.path || '')" loading="lazy" class="w-full aspect-square object-cover rounded-lg border border-pink-100 bg-pink-50/30 cursor-pointer absolute inset-0 transition-opacity duration-300" :class="[selectMode ? '' : 'gal-img', img._loaded ? 'opacity-100' : 'opacity-0']" @click="selectMode ? toggleSelect(img.path, i, $event.shiftKey) : openLightbox(i)" @load="img._loaded = true" @error="img._loaded = true" />
        </div>
        <button v-if="!selectMode" @click.stop="del(img.path)" class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-red-500/80 text-white text-[10px] leading-none sm:opacity-0 sm:group-hover:opacity-100 transition-opacity hover:bg-red-700 cursor-pointer border-0">✕</button>
      </div>
    </div>
    <div v-else-if="loading" class="flex flex-col items-center justify-center py-12 gap-2">
      <svg class="animate-spin h-6 w-6 text-pink-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <span class="text-xs text-gray-400">加载中请稍后...</span>
    </div>
    <div v-else class="text-center text-xs text-gray-400 py-8">暂无作品</div>
    <button v-if="items.length < total && !selectMode" @click="load(false)" class="w-full mt-3 py-2 text-xs text-pink-500 bg-white/75 rounded-xl hover:bg-pink-50 transition-all cursor-pointer border border-pink-100">
      {{ loading ? '加载中...' : '加载更多' }}
    </button>
  </div>
</template>