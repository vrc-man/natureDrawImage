<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { loadGallery } from '@/api/endpoints'
import { useLightbox, type LbItem } from '@/composables/useLightbox'

const { open } = useLightbox()
const images = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const pageSize = 30
const page = ref(0)
const galleryDir = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const pageWindow = computed(() => {
  const tp = totalPages.value
  if (tp <= 1) return []
  const p = page.value
  const s = Math.max(0, p - 2)
  const e = Math.min(tp - 1, p + 2)
  const items: (number | 'left' | 'right')[] = []
  if (p > 0) items.push(p - 1)
  if (s > 0) items.push('left')
  for (let i = s; i <= e; i++) items.push(i)
  if (e < tp - 1) items.push('right')
  if (p < tp - 1) items.push(p + 1)
  return items
})

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
    if (reset) { images.value = []; page.value = 0 }
    const d = await loadGallery({ offset: page.value * pageSize, limit: pageSize })
    images.value = d.items || []
    galleryDir.value = d.output_dir || ''
    total.value = d.total || 0
  } catch {}
  loading.value = false
}

function goPage(p: number) {
  if (p < 0 || p >= totalPages.value || p === page.value) return
  page.value = p
  load(false)
  window.scrollTo({ top: 0, behavior: 'smooth' })
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

defineExpose({ load, images, total })
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
    <!-- 翻页 -->
    <div v-if="images.length && totalPages > 1" class="flex items-center justify-center gap-2 mt-3 text-xs">
      <button @click="goPage(page - 1)" :disabled="page <= 0"
        class="px-2.5 py-1 bg-white/75 border border-pink-100 rounded-lg text-pink-500 hover:bg-pink-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">上一页</button>
      <template v-for="item in pageWindow" :key="typeof item === 'number' ? item : item">
        <span v-if="item === 'left' || item === 'right'" class="text-gray-400 px-1">...</span>
        <button v-else @click="goPage(item as number)" :disabled="item === page"
          :class="['px-2.5 py-1 rounded-lg cursor-pointer border', item === page ? 'bg-pink-500 text-white border-pink-500' : 'bg-white/75 border-pink-100 text-gray-600 hover:bg-pink-50']">{{ (item as number) + 1 }}</button>
      </template>
      <button @click="goPage(page + 1)" :disabled="page >= totalPages - 1"
        class="px-2.5 py-1 bg-white/75 border border-pink-100 rounded-lg text-pink-500 hover:bg-pink-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">下一页</button>
      <span class="text-gray-400 ml-1">{{ page + 1 }} / {{ totalPages }} 页 · 共 {{ total }} 张</span>
    </div>
  </div>
</template>
