<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, resizeImage, scanThumbnails, fmt } from './useAdminApi'

defineProps<{ visible: boolean }>()

interface WfEntry {
  workflow: string
  thumbnail: string
  lora_link: string
  category: string
}

const wfCategories = ref<string[]>([])
const wfMeta = ref<WfEntry[]>([])
const catInput = ref('')
const status = ref('')
const scanResult = ref('')

let saveTimer: ReturnType<typeof setTimeout> | null = null

async function load() {
  try {
    const [filesRes, metaRes, limitsRes] = await Promise.all([
      api('GET', '/api/admin/workflow_files'),
      api('GET', '/api/admin/workflow_meta'),
      api('GET', '/api/admin/limits'),
    ])
    const files: string[] = filesRes.files || []
    const meta: any[] = metaRes.workflow_meta || []
    wfCategories.value = [...((limitsRes.limits || {}).wf_categories || [])]
    const metaMap = new Map(meta.map((m: any) => [m.workflow, { thumbnail: m.thumbnail || '', lora_link: m.lora_link || '', category: m.category || '' }]))
    wfMeta.value = files.map(f => {
      const m = metaMap.get(f)
      return { workflow: f, thumbnail: (m?.thumbnail || ''), lora_link: (m?.lora_link || ''), category: (m?.category || '') }
    }).sort((a, b) => a.workflow.localeCompare(b.workflow))
    status.value = ''
  } catch (e: any) { status.value = '加载失败: ' + e.message }
}

async function saveWfMeta() {
  status.value = '保存中…'
  try {
    const d = await api('POST', '/api/admin/workflow_meta', { workflow_meta: wfMeta.value.map(w => ({ workflow: w.workflow, thumbnail: w.thumbnail || '', lora_link: w.lora_link || '', category: w.category || '' })) })
    wfMeta.value = (d.workflow_meta || []).map((m: any) => ({ workflow: m.workflow || '', thumbnail: m.thumbnail || '', lora_link: m.lora_link || '', category: m.category || '' }))
    status.value = '✓ 已保存'
    setTimeout(() => { if (status.value === '✓ 已保存') status.value = '' }, 2000)
  } catch (e: any) { status.value = '保存失败: ' + e.message }
}

function autoSaveWfMeta() {
  if (saveTimer) clearTimeout(saveTimer)
  status.value = '保存中…'
  saveTimer = setTimeout(saveWfMeta, 600)
}

async function addCategory() {
  const v = catInput.value.trim()
  if (!v || wfCategories.value.includes(v)) return
  wfCategories.value.push(v)
  catInput.value = ''
  try {
    await api('POST', '/api/admin/limits', { wf_categories: wfCategories.value })
  } catch (e: any) { status.value = '分类保存失败: ' + e.message }
}

async function removeCategory(cat: string) {
  wfCategories.value = wfCategories.value.filter(c => c !== cat)
  wfMeta.value.forEach(m => { if (m.category === cat) m.category = '' })
  try {
    await api('POST', '/api/admin/limits', { wf_categories: wfCategories.value })
  } catch (e: any) { status.value = '分类保存失败: ' + e.message }
  autoSaveWfMeta()
}

async function onRename(w: WfEntry, e: Event) {
  const input = e.target as HTMLInputElement
  const oldFull = w.workflow
  const newStem = input.value.trim()
  const newFull = newStem ? newStem + '.json' : ''
  if (!newStem || newFull === oldFull) { input.value = oldFull.replace(/\.json$/i, ''); return }
  status.value = '重命名中…'
  try {
    await api('POST', '/api/admin/workflow_rename', { old: oldFull, new: newFull })
    w.workflow = newFull
    status.value = '✓ 已重命名'
    setTimeout(() => { if (status.value === '✓ 已重命名') status.value = '' }, 2000)
  } catch (e: any) {
    input.value = oldFull.replace(/\.json$/i, '')
    status.value = '重命名失败: ' + e.message
  }
}

async function uploadThumb(w: WfEntry) {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'
  inp.onchange = async () => {
    const f = inp.files![0]; if (!f) return
    try {
      const compressed = await resizeImage(f); const fd = new FormData(); fd.append('file', compressed)
      const r = await fetch('/api/admin/wf_thumbnail', { method: 'POST', body: fd })
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText) }
      const d = await r.json()
      w.thumbnail = d.filename
      clearTimeout(saveTimer!)
      await saveWfMeta()
    } catch (e: any) { status.value = '上传失败: ' + e.message }
  }; inp.click()
}

async function scan() {
  scanResult.value = ''
  try {
    const d = await api('POST', '/api/admin/scan-thumbnails', { type: 'workflows' })
    const r = d.workflows || {}
    const parts = []
    if (r.matched > 0) parts.push(`✓ ${r.matched} 匹配`)
    if (r.missing > 0) parts.push(`⚠ ${r.missing} 缺失`)
    scanResult.value = parts.length ? parts.join('，') + `（共 ${r.total} 条）` : '无需处理'
    load()
  } catch (e: any) { scanResult.value = '扫描失败: ' + e.message }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded shadow p-4 mb-4">
    <div class="flex items-center justify-between mb-2">
      <h2 class="text-lg font-semibold">
        🔗 工作流缩略图 & Lora 链接
        <span class="ml-2 text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">{{ wfMeta.length }}</span>
      </h2>
      <button @click="load" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer">刷新</button>
    </div>
    <div>
      <p class="text-xs text-gray-500 mb-2">自动从 ComfyUI 工作流目录扫描。为每个工作流配置缩略图、Lora 链接和分类，修改后自动保存。</p>

      <div class="mb-3 border rounded p-3 bg-blue-50">
        <div class="text-sm font-semibold mb-2">📁 分类标签管理</div>
        <div class="flex flex-wrap gap-1 mb-2">
          <span v-for="cat in wfCategories" :key="cat" class="inline-flex items-center text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">
            {{ cat }}
            <button @click="removeCategory(cat)" class="ml-1 text-[10px] opacity-60 hover:opacity-100 border-0 bg-transparent cursor-pointer">✕</button>
          </span>
        </div>
        <div class="flex gap-2">
          <input v-model="catInput" @keydown.enter="addCategory" type="text" placeholder="输入新分类名称" class="flex-1 border rounded px-2 py-1 text-xs outline-none" />
          <button @click="addCategory" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs border-0 cursor-pointer">添加分类</button>
        </div>
      </div>

      <datalist id="wf-cat-list">
        <option value="">无分类</option>
        <option v-for="cat in wfCategories" :key="cat" :value="cat" />
      </datalist>

      <div class="flex items-center gap-2 mb-2">
        <button @click="scan" class="text-xs px-3 py-1 bg-purple-100 text-purple-700 rounded hover:bg-purple-200 border-0 cursor-pointer">📂 扫描缩略图</button>
        <span class="text-xs text-gray-500">{{ scanResult }}</span>
      </div>

      <div class="flex flex-col gap-2 mb-3">
        <div v-for="(w, i) in wfMeta" :key="w.workflow + i" class="flex items-start gap-2 p-2 border rounded bg-gray-50">
          <div class="flex-shrink-0 flex flex-col items-center gap-1">
            <img v-if="w.thumbnail" :src="'/api/thumbnail?path=' + encodeURIComponent(w.workflow) + '&_t=' + encodeURIComponent(w.thumbnail)" class="w-12 h-12 object-cover rounded bg-gray-50" alt="" />
            <div v-else class="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-300 text-[10px]">无图</div>
            <label class="text-[10px] text-blue-600 cursor-pointer hover:underline" @click.prevent="uploadThumb(w)">上传</label>
          </div>
          <div class="flex flex-col gap-1 flex-1 text-sm min-w-0">
            <div class="flex items-center gap-1">
              <input :value="w.workflow.replace(/\.json$/i, '')" @change="onRename(w, $event)" type="text" placeholder="工作流名称" class="flex-1 min-w-0 border rounded px-2 py-1 font-mono text-xs outline-none" />
              <span class="text-xs text-gray-400">.json</span>
            </div>
            <input v-model="w.lora_link" @input="autoSaveWfMeta()" type="text" placeholder="Lora 链接 URL（可选）" class="border rounded px-2 py-1 font-mono text-xs outline-none" />
            <input v-model="w.category" @input="autoSaveWfMeta()" type="text" placeholder="无分类" class="border rounded px-2 py-1 text-xs outline-none" list="wf-cat-list" autocomplete="off" />
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs text-gray-500">{{ status }}</span>
      </div>
    </div>
  </div>
</template>
