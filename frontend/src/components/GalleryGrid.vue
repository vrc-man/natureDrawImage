<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { loadGallery } from '@/api/endpoints'
import { useLightbox, type LbItem } from '@/composables/useLightbox'

const { open } = useLightbox()
const images = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const pageSize = 30
const loadedCount = ref(0)
const galleryDir = ref('')

onMounted(async () => {
  try {
    const r = await fetch('/api/workflows/current')
    const d = await r.json()
    if (d.output_dir) galleryDir.value = d.output_dir
  } catch {}
})

async function load(reset = false) {
  if (loading.value) return
  loading.value = true
  try {
    if (reset) { images.value = []; loadedCount.value = 0 }
    const d = await loadGallery({ offset: loadedCount.value, limit: pageSize })
    images.value.push(...(d.items || []))
    galleryDir.value = d.output_dir || ''
    total.value = d.total || 0
    loadedCount.value = images.value.length
  } catch {}
  loading.value = false
}

function fmtTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
function openLightbox(index: number) {
  const items: LbItem[] = images.value.map((img: any) => ({
    url: `/api/output/file?path=${encodeURIComponent(img.path || '')}`,
    title: img.filename || img.path?.split('/').pop(),
    path: img.path,
    filename: img.filename || img.path?.split('/').pop(),
    time: img.mtime ? fmtTime(img.mtime) : '',
  }))
  open(items, index)
}

defineExpose({ load, images, total, loadedCount })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs text-gray-400 truncate max-w-[60%]" :title="galleryDir">{{ galleryDir || '目录' }} · 已显示 {{ images.length }} / {{ total }}</span>
      <button @click="load(true)" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
    </div>
    <div v-if="images.length" id="gallery" class="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2">
      <div v-for="(img, i) in images" :key="img.path || i" class="gal-img cursor-pointer overflow-hidden relative bg-gray-100 rounded-lg" @click="openLightbox(i)">
        <div class="aspect-square flex items-center justify-center bg-gray-100 rounded-lg">
          <svg v-if="!img._loaded" class="animate-spin h-5 w-5 text-pink-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
        </div>
        <img :src="img.thumb || '/api/output/file?path=' + encodeURIComponent(img.path || '')" loading="lazy" class="w-full aspect-square object-cover absolute inset-0 transition-opacity duration-300" :class="img._loaded ? 'opacity-100' : 'opacity-0'" @load="img._loaded = true" @error="img._loaded = true" />
      </div>
    </div>
    <div v-else-if="loading" class="flex flex-col items-center justify-center py-12 gap-2">
      <svg class="animate-spin h-6 w-6 text-pink-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <span class="text-xs text-gray-400">加载中请稍后...</span>
    </div>
    <div v-else class="text-center text-xs text-gray-400 py-8">暂无图片</div>
    <button v-if="images.length < total" @click="load(false)" class="w-full mt-3 py-2 text-xs text-pink-500 bg-white/75 rounded-xl hover:bg-pink-50 transition-all cursor-pointer border border-pink-100">
      {{ loading ? '加载中...' : '加载更多' }}
    </button>
  </div>
</template>
