<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { loadFeatured } from '@/api/endpoints'
import { useLightbox, type LbItem } from '@/composables/useLightbox'

const { open } = useLightbox()
const items = ref<any[]>([])

onMounted(load)

async function load() {
  try {
    const d = await loadFeatured()
    items.value = d || []
  } catch {}
}

function openLightbox(index: number) {
  const lbItems: LbItem[] = items.value.map((img: any) => ({
    url: `/api/output/file?path=${encodeURIComponent(img.path || '')}`,
    title: img.filename,
    path: img.path,
    filename: img.filename,
  }))
  open(lbItems, index)
}
</script>

<template>
  <div>
    <div v-if="items.length" id="featured-gallery" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      <div v-for="(img, i) in items" :key="img.path || i" class="gal-img cursor-pointer overflow-hidden" @click="openLightbox(i)">
        <img :src="img.thumb || '/api/output/file?path=' + encodeURIComponent(img.path || '')" loading="lazy" class="w-full aspect-square object-cover" />
      </div>
    </div>
    <div v-else class="text-center text-xs text-gray-400 py-8">暂无精选图片</div>
  </div>
</template>
