<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { loadStyles, loadCharacters } from '@/api/endpoints'
import type { StyleItem, CharacterItem } from '@/api/types'

const emit = defineEmits<{ close: [] }>()
const open = ref(false)
const styles = ref<StyleItem[]>([])
const characters = ref<CharacterItem[]>([])
const styleSearch = ref('')
const charSearch = ref('')
const charCatExpanded = ref<Record<string, boolean>>({})

const filteredStyles = computed(() => {
  if (!styleSearch.value) return styles.value
  const q = styleSearch.value.toLowerCase()
  return styles.value.filter(s => (s.name || s.tags).toLowerCase().includes(q))
})
const filteredChars = computed(() => {
  if (!charSearch.value) return characters.value
  const q = charSearch.value.toLowerCase()
  return characters.value.filter(c => (c.name || c.tags).toLowerCase().includes(q))
})
const charGroups = computed(() => {
  const map: Record<string, CharacterItem[]> = {}
  for (const c of filteredChars.value) {
    const cat = c.category || '未分类'
    if (!map[cat]) map[cat] = []
    map[cat].push(c)
  }
  return map
})

const selectedStyle = ref(localStorage.getItem('currentStyle') || '')
const selectedCharsRaw = (() => { try { return JSON.parse(localStorage.getItem('currentCharacters') || '[]') } catch { return [] } })()
const selectedChars = ref<string[]>(selectedCharsRaw)

onMounted(async () => {
  try {
    const sd: any = await loadStyles()
    styles.value = Array.isArray(sd) ? sd : (sd.styles || [])
    const cd: any = await loadCharacters()
    characters.value = Array.isArray(cd) ? cd : (cd.characters || [])
    // 初始化分类展开状态：有搜索关键词或已选角色时全部展开
    const cats = [...new Set(characters.value.map(c => c.category || '未分类'))]
    const hasSearch = !!charSearch.value
    const hasSelected = selectedChars.value.length > 0
    for (const cat of cats) {
      const hasSel = characters.value.filter(c => (c.category || '未分类') === cat).some(c => selectedChars.value.includes(c.tags))
      charCatExpanded.value[cat] = hasSearch || hasSel
    }
  } catch {}
})

function toggle() { open.value = !open.value }

function selectStyle(tags: string) {
  if (selectedStyle.value === tags) {
    selectedStyle.value = ''
    localStorage.removeItem('currentStyle')
  } else {
    selectedStyle.value = tags
    localStorage.setItem('currentStyle', tags)
  }
}
function toggleChar(tags: string) {
  const idx = selectedChars.value.indexOf(tags)
  if (idx >= 0) selectedChars.value.splice(idx, 1)
  else selectedChars.value.push(tags)
  localStorage.setItem('currentCharacters', JSON.stringify(selectedChars.value))
}
function removeChar(tags: string) {
  selectedChars.value = selectedChars.value.filter(t => t !== tags)
  localStorage.setItem('currentCharacters', JSON.stringify(selectedChars.value))
}
function removeStyle() {
  selectedStyle.value = ''
  localStorage.removeItem('currentStyle')
}
function getSelectedStyleTags() { return selectedStyle.value }
function getSelectedCharTags() { return selectedChars.value.join(', ') }
</script>

<template>
  <div>
    <!-- Trigger area -->
    <div class="flex items-center gap-2 px-4 py-2 bg-white/75 backdrop-blur rounded-2xl border border-pink-100 shadow-sm cursor-pointer hover:bg-pink-50/50 transition-all select-none" @click="toggle">
      <span class="text-xs text-gray-400 font-medium">🎭</span>
      <span class="flex-1 text-xs text-gray-400">角色 / 画风</span>
      <span v-if="selectedStyle || selectedChars.length" class="text-xs text-pink-500 truncate max-w-[120px]">
        {{ selectedStyle ? '🎨 ' + selectedStyle.split(',')[0] : '' }}{{ selectedChars.length ? '👥 ' + selectedChars.length + '个角色' : '' }}
      </span>
      <span class="text-pink-300 text-xl leading-none">▾</span>
    </div>

    <!-- Selected tags display -->
    <div v-if="selectedStyle || selectedChars.length" class="flex flex-wrap gap-1 mt-1">
      <span v-if="selectedStyle" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-pink-100 text-pink-700 text-[10px] font-medium pick-label-btn cursor-pointer hover:line-through" @click="removeStyle">🖌️ ✕ {{ selectedStyle.split(',')[0] }}</span>
      <span v-for="t in selectedChars" :key="t" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-pink-100 text-pink-700 text-[10px] font-medium pick-label-btn cursor-pointer hover:line-through" @click="removeChar(t)">🎭 ✕ {{ t.split(',')[0] }}</span>
    </div>

    <!-- Picker modal -->
    <Teleport to="body">
      <div v-if="open" class="fixed inset-0 z-[65] bg-black/30 backdrop-blur-sm flex items-start justify-center py-8" @click.self="open = false">
        <div class="mx-4 w-full max-w-[calc(100vw-3rem)] bg-white/95 backdrop-blur-xl border border-pink-100 rounded-3xl shadow-2xl shadow-pink-100/40 flex flex-col max-h-[calc(100vh-4rem)]">
          <div class="flex items-center justify-between p-5 pb-3 border-b border-pink-100 shrink-0">
            <h3 class="text-lg font-bold text-gray-700">🎭 选择角色 & 画风</h3>
            <button @click="open = false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">✕</button>
          </div>
          <div class="flex gap-4 p-5 flex-col sm:flex-row">
            <!-- Characters -->
            <div class="char-picker-col">
              <h4 class="text-sm font-bold text-gray-700 mb-1.5">🎭 角色</h4>
              <input v-model="charSearch" placeholder="搜索角色..." class="w-full border border-pink-200 rounded-xl px-3 py-1.5 text-xs outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 box-border" />
              <div class="char-picker-grid flex flex-wrap gap-1 mt-2 max-h-[40vh] overflow-y-auto">
                <template v-for="(items, cat) in charGroups" :key="cat">
                  <div class="wf-cat-title flex items-center gap-1 cursor-pointer select-none text-xs font-semibold text-gray-400 mt-2 mb-1 w-full" @click="charCatExpanded[cat] = !charCatExpanded[cat]">
                    <span>{{ charCatExpanded[cat] !== false ? '▾' : '▸' }}</span>
                    {{ cat }}
                  </div>
                  <div v-show="charCatExpanded[cat] !== false" class="flex flex-wrap gap-1 w-full">
                    <div v-for="c in items" :key="c.tags" :class="['style-card', { selected: selectedChars.includes(c.tags) }]" @click="toggleChar(c.tags)">
                      <img v-if="c.image" :src="'/api/character_thumbnail?name=' + encodeURIComponent(c.image)" class="style-thumb" loading="lazy" />
                      <div v-else class="style-thumb flex items-center justify-center text-gray-300 text-base">🎭</div>
                      <span class="style-label">{{ c.name || c.tags }}</span>
                    </div>
                  </div>
                </template>
              </div>
            </div>
            <!-- Styles -->
            <div class="char-picker-col">
              <h4 class="text-sm font-bold text-gray-700 mb-1.5">🖌️ 画风</h4>
              <input v-model="styleSearch" placeholder="搜索画风..." class="w-full border border-pink-200 rounded-xl px-3 py-1.5 text-xs outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 box-border" />
              <div class="char-picker-grid flex flex-wrap gap-1 mt-2 max-h-[40vh] overflow-y-auto">
                <div v-for="s in filteredStyles" :key="s.tags" :class="['style-card', { selected: selectedStyle === s.tags }]" @click="selectStyle(s.tags)">
                  <img v-if="s.image" :src="'/api/style_thumbnail?name=' + encodeURIComponent(s.image)" class="style-thumb" loading="lazy" />
                  <div v-else class="style-thumb flex items-center justify-center text-gray-300 text-base">🖌️</div>
                  <span class="style-label">{{ s.name || s.tags }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
