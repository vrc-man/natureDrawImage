<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { loadFeatured } from '@/api/endpoints'
import { useLightbox, type LbItem } from '@/composables/useLightbox'

const { open } = useLightbox()
const items = ref<any[]>([])
const loading = ref(false)
const errorMsg = ref('')

onMounted(load)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const d = await loadFeatured()
    items.value = d.items || []
  } catch (e: any) {
    // 不再静默吞错：暴露原因，便于排查空白问题
    errorMsg.value = '精选加载失败: ' + (e?.message || e || '未知错误')
    console.error('[featured] load failed:', e)
  } finally {
    loading.value = false
  }
}

function fmtTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
function openLightbox(index: number) {
  const lbItems: LbItem[] = items.value.map((img: any) => ({
    url: `/api/output/file?path=${encodeURIComponent(img.path || '')}`,
    title: img.filename || img.path?.split('/').pop() || '',
    path: img.path,
    filename: img.filename || img.path?.split('/').pop() || '',
    time: img.mtime ? fmtTime(img.mtime) : '',
  }))
  open(lbItems, index)
}
</script>

<template>
  <div>
    <!-- 顶部工具条：刷新 + 计数 -->
    <div class="flex items-center gap-2 mb-3">
      <span class="text-sm font-semibold text-gray-600">⭐ 精选展示</span>
      <span class="text-xs text-gray-400">({{ items.length }})</span>
      <button @click="load" :disabled="loading"
        class="ml-auto px-2 py-1 text-xs bg-pink-50 text-pink-500 rounded-lg hover:bg-pink-100 disabled:opacity-40 cursor-pointer border-0">
        {{ loading ? '加载中…' : '🔄 刷新' }}
      </button>
    </div>

    <div v-if="errorMsg" class="text-center text-xs text-red-500 py-4">{{ errorMsg }}</div>

    <div v-if="items.length" id="featured-gallery" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      <div v-for="(img, i) in items" :key="img.path || i" class="gal-img cursor-pointer overflow-hidden" @click="openLightbox(i)">
        <img :src="img.thumb || '/api/output/file?path=' + encodeURIComponent(img.path || '')" loading="lazy" class="w-full aspect-square object-cover" />
      </div>
    </div>
    <div v-else-if="!loading && !errorMsg" class="text-center text-xs text-gray-400 py-8">暂无精选图片</div>
  </div>
</template>
