<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const allItems = ref<any[]>([])
const total = ref(0)
const loaded = ref(24)
const loading = ref(false)
const errorMsg = ref('')
const nameSearch = ref('')
let dragIdx = -1

// 按图片名过滤后的列表（前端实时过滤，不调接口）
const filteredAll = computed(() => {
  const q = nameSearch.value.trim().toLowerCase()
  if (!q) return allItems.value
  return allItems.value.filter((it: any) => (it.path || '').toLowerCase().includes(q))
})
const displayItems = computed(() => filteredAll.value.slice(0, loaded.value))

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const d = await api('GET', '/api/admin/featured')
    const list = (d.items || []).map((p: any) => typeof p === 'string' ? { path: p } : p)
    allItems.value = list
    total.value = list.length
  } catch (e: any) {
    errorMsg.value = '加载失败: ' + (e?.message || e || '未知错误')
  } finally {
    loading.value = false
  }
}

function loadMore() {
  loaded.value = Math.min(loaded.value + 10, filteredAll.value.length)
}

async function remove(path: string) {
  if (!confirm('确认移出精选？')) return
  try {
    const d = await api('POST', '/api/admin/featured/remove', { path })
    // 以后端返回的最新列表为准，同步 allItems（displayItems 为 computed 会自动更新）
    const list = (d.items || []).map((p: any) => typeof p === 'string' ? { path: p } : p)
    allItems.value = list
    loaded.value = Math.min(loaded.value, list.length || 24)
    total.value = list.length
  } catch (e: any) { alert('操作失败: ' + e.message) }
}

function onDragStart(i: number) { dragIdx = i }
async function onDrop(i: number) {
  if (nameSearch.value.trim()) return  // 搜索过滤状态下不支持拖拽排序（索引会错乱）
  if (i === dragIdx || dragIdx < 0) return
  // 非搜索态：displayItems = allItems 前 loaded 条，直接在 allItems 上重排
  const arr = allItems.value.slice()
  const item = arr.splice(dragIdx, 1)[0]
  arr.splice(i, 0, item)
  allItems.value = arr
  dragIdx = -1
  try {
    await api('POST', '/api/admin/featured/reorder', { items: allItems.value.map((x: any) => x.path || x) })
  } catch {}
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <div class="flex items-center gap-2 mb-3 text-xs flex-wrap">
      <span class="font-semibold text-gray-600">⭐ 精选管理</span>
      <span class="text-gray-400">({{ total }})</span>
      <input v-model="nameSearch" type="text" placeholder="图片名搜索" class="border rounded px-2 py-1 text-xs w-32 outline-none" />
      <button v-if="nameSearch" @click="nameSearch=''" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">清除</button>
      <span v-if="displayItems.length && !nameSearch" class="text-gray-400 text-[10px]">拖拽卡片可排序 · 点图看大图</span>
      <span v-if="nameSearch" class="text-gray-400 text-[10px]">搜索中（{{ filteredAll.length }} 条匹配，搜索时不可拖拽排序）</span>
      <button @click="load" :disabled="loading" class="ml-auto px-2 py-1 bg-pink-50 text-pink-500 rounded-lg hover:bg-pink-100 disabled:opacity-40 cursor-pointer border-0">{{ loading ? '加载中…' : '🔄 刷新' }}</button>
    </div>

    <div v-if="errorMsg" class="text-xs text-red-500 py-3 text-center">{{ errorMsg }}</div>

    <div v-if="!displayItems.length && !loading && !errorMsg" class="text-xs text-gray-400 py-8 text-center">
      {{ nameSearch ? '没有匹配的精选图。' : '还没添加任何精选图。在「生图记录」里点 ☆ 加入精选。' }}
    </div>

    <div v-else-if="displayItems.length" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
      <div v-for="(item, i) in displayItems" :key="item.path || i"
        class="border rounded p-1 bg-amber-50"
        :class="nameSearch ? '' : 'cursor-move'"
        :draggable="!nameSearch"
        @dragstart="onDragStart(i)"
        @dragover.prevent
        @drop="onDrop(i)">
        <img :src="'/api/output/thumb?path=' + encodeURIComponent(item.path || '')"
          class="lb-thumb w-full aspect-square object-cover rounded bg-white cursor-pointer"
          loading="lazy"
          :data-path="item.path || ''" :data-mtime="item.mtime || ''" />
        <div class="text-[10px] mt-1 break-all text-gray-600">{{ item.path?.split('/').pop() || item.path || '' }}</div>
        <button @click.stop="remove(item.path || item)"
          class="mt-1 w-full text-[10px] bg-amber-500 text-white rounded px-1 py-0.5 hover:bg-amber-600 cursor-pointer border-0">移出精选</button>
      </div>
    </div>

    <div class="mt-3 flex items-center gap-2 text-xs">
      <button v-if="loaded < filteredAll.length" @click="loadMore" class="px-3 py-1 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 cursor-pointer border-0">加载更多精选</button>
    </div>
  </div>
</template>
