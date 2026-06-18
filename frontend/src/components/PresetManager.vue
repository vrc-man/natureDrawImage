<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{ target: 'direct' | 'negative_prompt'; onFill: (text: string) => void }>()
const open = ref(false)
const editingId = ref<number | null>(null)
const checked = ref<Record<number, boolean>>({})
const view = ref<'list' | 'form'>('list')
const formName = ref('')
const formText = ref('')

const STORAGE_KEY = props.target === 'direct' ? 'presets_direct' : 'presets_neg'

function loadPresets(): any[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}
function savePresets(arr: any[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(arr))
}
const presets = ref(loadPresets())
const checkedCount = computed(() => Object.values(checked.value).filter(Boolean).length)

function openList() { open.value = true; view.value = 'list'; presets.value = loadPresets() }

function switchView(v: 'list' | 'form') { view.value = v }
function showNewForm() {
  editingId.value = null; formName.value = ''; formText.value = ''
  view.value = 'form'
}
function showEditForm(id: number) {
  const p = presets.value.find((_: any, i: number) => i === id)
  if (!p) return
  editingId.value = id; formName.value = p.name; formText.value = p.text
  view.value = 'form'
}
function saveForm() {
  if (!formName.value.trim() || !formText.value.trim()) return
  if (editingId.value !== null) {
    presets.value[editingId.value] = { name: formName.value.trim(), text: formText.value.trim() }
  } else {
    presets.value.push({ name: formName.value.trim(), text: formText.value.trim() })
  }
  savePresets(presets.value)
  view.value = 'list'
}
function deleteSelected() {
  presets.value = presets.value.filter((_: any, i: number) => !checked.value[i])
  checked.value = {}
  savePresets(presets.value)
}
function importFromBox() {
  const ta = document.getElementById(props.target) as HTMLTextAreaElement
  if (!ta || !ta.value.trim()) return
  const name = prompt('预设名称：')
  if (!name) return
  presets.value.push({ name, text: ta.value.trim() })
  savePresets(presets.value)
}
function fillPreset(id: number) {
  const p = presets.value[id]
  if (p) { props.onFill(p.text); open.value = false }
}
function exportPresets() {
  const blob = new Blob([JSON.stringify(presets.value, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = `${props.target}_presets.json`; a.click()
}
function importPresets() {
  const inp = document.createElement('input')
  inp.type = 'file'; inp.accept = '.json'
  inp.onchange = () => {
    const f = inp.files![0]; if (!f) return
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const arr = JSON.parse(e.target!.result as string)
        if (Array.isArray(arr)) { presets.value = arr; savePresets(arr) }
      } catch {}
    }
    reader.readAsText(f)
  }
  inp.click()
}
</script>

<template>
  <button class="text-[10px] text-pink-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent" @click="openList">📋 预设</button>

  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[65] bg-black/30 backdrop-blur-sm flex items-start justify-center py-8" @click.self="open = false">
      <div class="mx-4 w-full max-w-[calc(100vw_-_10px)] bg-white/95 backdrop-blur-xl border border-pink-100 rounded-3xl shadow-2xl shadow-pink-100/40 flex flex-col max-h-[calc(100vh-4rem)]" @click.stop>
        <!-- List view -->
        <template v-if="view === 'list'">
          <div class="flex items-center justify-between p-5 pb-3 border-b border-pink-100 shrink-0">
            <h3 class="text-lg font-bold text-gray-700">📋 {{ props.target === 'direct' ? '正面提示词' : '负面提示词' }} 预设</h3>
            <button @click="open = false" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">✕</button>
          </div>
          <div class="flex items-center gap-2 px-5 py-2 text-xs text-gray-400 border-b border-pink-50">
            <span>共 {{ presets.length }} 条</span>
            <button @click="exportPresets" class="text-pink-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent ml-auto">导出</button>
            <button @click="importPresets" class="text-pink-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">导入</button>
            <button @click="showNewForm" class="px-3 py-1 bg-pink-500 text-white rounded-lg hover:bg-pink-600 cursor-pointer border-0 text-[10px]">+ 新建</button>
            <button v-if="checkedCount" @click="deleteSelected" class="text-red-400 hover:text-red-500 cursor-pointer border-0 bg-transparent">删除({{ checkedCount }})</button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-1">
            <div v-for="(p, i) in presets" :key="i" class="flex items-center gap-2 py-2 px-3 rounded-xl hover:bg-pink-50 transition-all">
              <input type="checkbox" v-model="checked[i]" class="accent-pink-500 shrink-0" />
              <span class="flex-1 text-sm font-medium text-gray-700 truncate cursor-pointer min-w-0" @click="fillPreset(i)">{{ p.name || '(未命名)' }}</span>
              <button @click="fillPreset(i)" class="text-xs text-pink-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">填入</button>
              <button @click="showEditForm(i)" class="text-xs text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">编辑</button>
            </div>
          </div>
        </template>
        <!-- Form view -->
        <template v-else>
          <div class="flex items-center gap-2 p-5 pb-3 border-b border-pink-100 shrink-0">
            <button @click="view = 'list'" class="text-lg text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">&larr;</button>
            <h3 class="text-base font-bold text-gray-700">{{ editingId !== null ? '编辑预设' : '新建预设' }}</h3>
          </div>
          <div class="p-5 space-y-3">
            <input v-model="formName" placeholder="预设名称" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none transition-all box-border" />
            <textarea v-model="formText" placeholder="预设内容" rows="6" class="w-full border border-pink-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none transition-all resize-y box-border"></textarea>
            <button @click="importFromBox" class="text-xs text-pink-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">📥 从输入框导入</button>
            <div class="flex gap-2">
              <button @click="view = 'list'" class="flex-1 py-2.5 bg-gray-100 rounded-xl hover:bg-gray-200 text-sm text-gray-600 transition-all cursor-pointer border-0">取消</button>
              <button @click="saveForm" class="flex-1 py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-sm font-semibold transition-all cursor-pointer border-0">保存</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>
