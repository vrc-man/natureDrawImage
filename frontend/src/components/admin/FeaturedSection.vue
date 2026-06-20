<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([])
const allItems = ref<any[]>([])
const total = ref(0)
const loaded = ref(24)
let dragIdx = -1

async function load() {
  try {
    const d = await api('GET', '/api/admin/featured')
    const list = (d.items || []).map((p: any) => typeof p === 'string' ? { path: p } : p)
    allItems.value = list
    items.value = list.slice(0, loaded.value)
    total.value = list.length
  } catch {}
}

function loadMore() {
  loaded.value = Math.min(loaded.value + 10, allItems.value.length)
  items.value = allItems.value.slice(0, loaded.value)
}

async function remove(path: string) {
  if (!confirm('确认移出精选？')) return
  try {
    await api('POST', '/api/admin/featured/remove', { path })
    items.value = items.value.filter((i: any) => (i.path || i) !== path)
    total.value = items.value.length
  } catch (e: any) { alert('操作失败: ' + e.message) }
}

function onDragStart(i: number) { dragIdx = i }
async function onDrop(i: number) {
  if (i === dragIdx || dragIdx < 0) return
  const item = items.value.splice(dragIdx, 1)[0]
  items.value.splice(i, 0, item)
  dragIdx = -1
  try {
    await api('POST', '/api/admin/featured/reorder', { items: items.value.map((x: any) => x.path || x) })
  } catch {}
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <div v-if="!items.length" class="text-xs text-gray-400 py-8 text-center">
      还没添加任何精选图。在下面「生图记录」里点 ☆ 加入精选。
    </div>
    <div v-else class="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2">
      <div v-for="(item, i) in items" :key="item.path || i" class="relative group"
        draggable="true"
        @dragstart="onDragStart(i)"
        @dragover.prevent
        @drop="onDrop(i)">
        <img :src="'/api/output/thumb?path=' + encodeURIComponent(item.path || '')"
          class="w-full aspect-square object-cover rounded-lg bg-gray-50" />
        <div class="absolute inset-x-0 bottom-0 bg-black/50 text-[9px] text-white px-1 truncate rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
          {{ item.path?.split('/').pop() || '' }}
        </div>
        <button @click="remove(item.path || item)"
          class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-red-500/80 text-white text-[10px] opacity-0 group-hover:opacity-100 cursor-pointer border-0 flex items-center justify-center hover:bg-red-600 transition-opacity">✕</button>
      </div>
    </div>
    <div class="mt-3 flex items-center gap-2 text-xs">
      <button @click="loadMore" class="px-3 py-1 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 cursor-pointer border-0">加载更多精选</button>
      <button @click="load" class="text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
      <span v-if="items.length" class="text-gray-400 text-[10px]">拖拽图片可排序</span>
    </div>
  </div>
</template>
