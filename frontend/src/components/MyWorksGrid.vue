<script setup lang="ts">
import { ref } from 'vue'
import { loadMyImages, deleteMyImage } from '@/api/endpoints'
import { useLightbox, type LbItem } from '@/composables/useLightbox'

const { open } = useLightbox()
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const pageSize = 30

async function load(reset = false) {
  if (loading.value) return
  loading.value = true
  try {
    if (reset) items.value = []
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
  } catch {}
}

function openLightbox(index: number) {
  const lbItems: LbItem[] = items.value.map((img: any) => ({
    url: img.url || `/api/image?filename=${encodeURIComponent(img.filename)}&type=output`,
    title: img.filename,
    path: img.path,
    filename: img.filename,
  }))
  open(lbItems, index)
}

defineExpose({ load, items, total, loadedCount: items })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs text-gray-400">共 {{ total }} 张</span>
      <button @click="load(true)" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
    </div>
    <div v-if="items.length" id="myworks-gallery" class="grid grid-cols-3 sm:grid-cols-4 gap-2">
      <div v-for="(img, i) in items" :key="img.path || i" class="relative group">
        <img :src="img.thumbnail_url || img.url" loading="lazy" class="w-full aspect-square object-cover rounded-lg border border-pink-100 bg-pink-50/30 cursor-pointer gal-img" @click="openLightbox(i)" />
        <button @click.stop="del(img.path)" class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-red-500/80 text-white text-[10px] leading-none opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-700 cursor-pointer border-0">✕</button>
      </div>
    </div>
    <div v-else-if="!loading" class="text-center text-xs text-gray-400 py-8">暂无作品</div>
    <button v-if="items.length < total" @click="load(false)" class="w-full mt-3 py-2 text-xs text-pink-500 bg-white/75 rounded-xl hover:bg-pink-50 transition-all cursor-pointer border border-pink-100">
      {{ loading ? '加载中...' : '加载更多' }}
    </button>
  </div>
</template>
