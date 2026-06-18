<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { loadWorkflows } from '@/api/endpoints'
import type { WorkflowItem } from '@/api/types'

const emit = defineEmits<{ select: [path: string, name: string] }>()
const props = defineProps<{ mode: 'txt2img' | 'img2img' }>()

const open = ref(false)
const selectedName = ref(localStorage.getItem('currentWorkflowName') || '')
const allWorkflows = ref<WorkflowItem[]>([])
const search = ref('')
const catExpanded = ref<Record<string, boolean>>({})
const txt2imgDir = ref('')
const img2imgDir = ref('')

const workflows = computed(() => {
  const dir = props.mode === 'img2img' ? img2imgDir.value : txt2imgDir.value
  if (!dir) return allWorkflows.value
  return allWorkflows.value.filter(w => w.path && w.path.startsWith(dir))
})

const filtered = computed(() => {
  if (!search.value) return workflows.value
  const q = search.value.toLowerCase()
  return workflows.value.filter(w => (w.name || w.path).toLowerCase().includes(q))
})

const grouped = computed(() => {
  const map: Record<string, WorkflowItem[]> = {}
  for (const w of filtered.value) {
    const cat = w.category || '未分类'
    if (!map[cat]) map[cat] = []
    map[cat].push(w)
  }
  return map
})

async function loadAll() {
  try {
    const d = await loadWorkflows()
    allWorkflows.value = d.workflows || d.all || []
    txt2imgDir.value = d.txt2img_dir || ''
    img2imgDir.value = d.img2img_dir || ''
  } catch {}
}

onMounted(loadAll)

function toggle() { open.value = !open.value }
function select(w: WorkflowItem) {
  localStorage.setItem('currentWorkflow', w.path)
  selectedName.value = w.name || w.path
  localStorage.setItem('currentWorkflowName', selectedName.value)
  emit('select', w.path, w.name || w.path)
  open.value = false
}

function _highlight(text: string, q: string) {
  if (!q) return text
  const idx = text.toLowerCase().indexOf(q.toLowerCase())
  if (idx === -1) return text
  return text.slice(0, idx) + '<mark class="bg-pink-200 rounded px-0.5">' + text.slice(idx, idx + q.length) + '</mark>' + text.slice(idx + q.length)
}
</script>

<template>
  <!-- Trigger -->
  <div class="flex items-center gap-2 px-4 py-2.5 bg-white/75 backdrop-blur rounded-2xl border border-pink-100 shadow-sm cursor-pointer hover:bg-pink-50/50 transition-all select-none" @click="toggle">
    <span class="text-xs text-gray-400 font-medium">📋</span>
    <span class="flex-1 text-xs text-gray-600 truncate">{{ selectedName || '选择工作流' }}</span>
    <span class="text-pink-300 text-xl leading-none">▾</span>
  </div>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[65] bg-black/30 backdrop-blur-sm flex items-start justify-center py-8" @click.self="open = false">
      <div class="mx-4 w-full max-w-[calc(100vw_-_10px)] bg-white/95 backdrop-blur-xl border border-pink-100 rounded-3xl shadow-2xl shadow-pink-100/40 flex flex-col max-h-[calc(100vh-4rem)]">
        <div class="flex items-center justify-between p-5 pb-3 border-b border-pink-100 shrink-0">
          <h3 class="text-lg font-bold text-gray-700">📋 选择工作流</h3>
          <button @click="open = false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">✕</button>
        </div>
        <div class="px-5 pt-2 pb-1">
          <input v-model="search" placeholder="搜索工作流..." class="w-full border border-pink-200 rounded-xl px-4 py-2 text-sm outline-none focus:border-pink-400 focus:ring-2 focus:ring-pink-200 transition-all box-border" />
        </div>
        <div class="wf-scroll flex-1 p-5 pt-2 space-y-1">
          <div v-for="(items, cat) in grouped" :key="cat">
            <div class="wf-cat-title flex items-center gap-1 cursor-pointer select-none text-xs font-semibold text-gray-400 mt-3 mb-2" @click="catExpanded[cat] = !catExpanded[cat]">
              <span>{{ catExpanded[cat] === false ? '▸' : '▾' }}</span>
              {{ cat }}
            </div>
            <div v-show="catExpanded[cat] !== false" class="wf-grid flex flex-wrap gap-1.5">
              <div v-for="w in items" :key="w.path" class="wf-card" :title="w.name || w.path" @click="select(w)">
                <img v-if="w.thumbnail" :src="'/api/thumbnail?path=' + encodeURIComponent(w.path)" class="wf-thumb" loading="lazy" />
                <div v-else class="wf-thumb flex items-center justify-center text-gray-300 text-lg">📄</div>
                <span class="wf-label" v-html="_highlight(w.name || w.path, search)"></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
