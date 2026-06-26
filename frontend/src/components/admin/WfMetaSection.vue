<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, resizeImage, batchUploadThumbnails, type BatchThumbItem } from './useAdminApi'
import { showCenterToast } from '@/composables/useToast'

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
const searchKey = ref('')

// 按工作流名过滤（不区分大小写，实时）。返回 {w, idx} 保留在 wfMeta 中的真实索引，确保编辑/重命名正确指向原对象
const filteredMeta = computed(() => {
  const q = searchKey.value.trim().toLowerCase()
  if (!q) return wfMeta.value
  return wfMeta.value.filter(w => w.workflow.toLowerCase().includes(q))
})

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
    showCenterToast('✓ 已保存')
    setTimeout(() => { if (status.value === '✓ 已保存') status.value = '' }, 2000)
  } catch (e: any) { status.value = '保存失败: ' + e.message }
}

function autoSaveWfMeta() {
  if (saveTimer) clearTimeout(saveTimer)
  status.value = '保存中…'
  saveTimer = setTimeout(saveWfMeta, 600)
}

function setCategory(w: WfEntry, cat: string) {
  w.category = w.category === cat ? '' : cat
  autoSaveWfMeta()
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
      const compressed = await resizeImage(f); const fd = new FormData(); fd.append('file', compressed); fd.append('name', w.workflow)
      const r = await fetch('/api/admin/wf_thumbnail', { method: 'POST', body: fd })
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText) }
      const d = await r.json()
      w.thumbnail = d.filename
      clearTimeout(saveTimer!)
      await saveWfMeta()
    } catch (e: any) { status.value = '上传失败: ' + e.message }
  }; inp.click()
}

const batchUploading = ref(false)
const batchResult = ref('')
const batchDetails = ref<BatchThumbItem[]>([])

function batchUpload() {
  const inp = document.createElement('input')
  inp.type = 'file'; inp.accept = 'image/*'; inp.multiple = true
  inp.onchange = async () => {
    const files = Array.from(inp.files || [])
    if (!files.length) return
    batchUploading.value = true
    batchResult.value = '上传中…'
    batchDetails.value = []
    try {
      const d = await batchUploadThumbnails('/api/admin/wf_thumbnail_batch', files)
      batchDetails.value = d.results
      const parts = []
      if (d.matched > 0) parts.push(`✓ ${d.matched} 匹配上传`)
      if (d.unmatched > 0) parts.push(`⚠ ${d.unmatched} 未匹配`)
      if (d.errored > 0) parts.push(`✗ ${d.errored} 失败`)
      batchResult.value = parts.join('，') || '无文件'
      showCenterToast(`批量上传完成：${d.matched} 张已匹配`)
      await load()
    } catch (e: any) {
      batchResult.value = '批量上传失败: ' + e.message
    } finally {
      batchUploading.value = false
    }
  }
  inp.click()
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded shadow p-4 mb-4">
    <div class="flex items-center justify-between mb-2 gap-2 flex-wrap">
      <div class="flex items-center gap-1">
        <input v-model="searchKey" type="text" placeholder="🔍 工作流名称搜索" class="border rounded px-2 py-1 text-xs w-44 outline-none" />
        <button v-if="searchKey" @click="searchKey=''" class="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">清除</button>
        <span v-if="searchKey" class="text-[11px] text-gray-400">{{ filteredMeta.length }} / {{ wfMeta.length }} 个匹配</span>
      </div>
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

      <div class="mb-3 border rounded p-3 bg-amber-50">
        <div class="flex items-center gap-2 flex-wrap">
          <button @click="batchUpload" :disabled="batchUploading" class="text-xs px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600 border-0 cursor-pointer disabled:opacity-50">⬆️ 批量上传缩略图</button>
          <span class="text-xs text-gray-500">{{ batchResult }}</span>
        </div>
        <p class="text-[11px] text-gray-500 mt-1.5">
          可一次选多张图片。文件名（去扩展名）需与工作流名 <b>完全一致且区分大小写</b>，例如 <code class="bg-white px-1 rounded">MyFlow.png</code> 匹配工作流 <code class="bg-white px-1 rounded">MyFlow.json</code>。上传后会自动生成 512×512 WebP 缩略图。
        </p>
        <div v-if="batchDetails.length" class="mt-2 max-h-40 overflow-y-auto text-[11px] space-y-0.5">
          <div v-for="(r, i) in batchDetails" :key="i" class="flex items-center gap-1.5">
            <span v-if="r.status === 'ok'" class="text-green-600">✓</span>
            <span v-else-if="r.status === 'unmatched'" class="text-amber-600">⚠</span>
            <span v-else class="text-red-500">✗</span>
            <span class="font-mono text-gray-600">{{ r.filename }}</span>
            <span v-if="r.status === 'ok'" class="text-gray-400">→ {{ r.matched.length }} 个工作流</span>
            <span v-else-if="r.status === 'unmatched'" class="text-amber-600">未找到匹配工作流</span>
            <span v-else class="text-red-500">{{ r.error }}</span>
          </div>
        </div>
      </div>

      <div class="flex flex-col gap-2 mb-3">
        <div v-if="!filteredMeta.length" class="text-xs text-gray-400 py-6 text-center">
          {{ searchKey ? '没有匹配的工作流' : '暂无工作流' }}
        </div>
        <div v-for="(w, i) in filteredMeta" :key="w.workflow + i" class="flex items-start gap-2 p-2 border rounded bg-gray-50">
          <div class="flex-shrink-0 flex flex-col items-center gap-1">
            <img v-if="w.thumbnail" :src="'/api/thumbnail?path=' + encodeURIComponent(w.workflow) + '&_t=' + encodeURIComponent(w.thumbnail)" class="w-12 h-12 object-cover rounded bg-gray-50" alt="" />
            <div v-else class="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-300 text-[10px]">无图</div>
            <label class="text-[10px] text-blue-600 cursor-pointer hover:underline" @click.prevent="uploadThumb(w)">上传</label>
          </div>
          <div class="flex flex-col gap-1.5 flex-1 text-sm min-w-0">
            <div class="flex items-center gap-1">
              <input :value="w.workflow.replace(/\.json$/i, '')" @change="onRename(w, $event)" type="text" placeholder="工作流名称" class="flex-1 min-w-0 border rounded px-2 py-1 font-mono text-xs outline-none" />
              <span class="text-xs text-gray-400">.json</span>
            </div>
            <input v-model="w.lora_link" @input="autoSaveWfMeta()" type="text" placeholder="Lora 链接 URL（可选）" class="border rounded px-2 py-1 font-mono text-xs outline-none" />
            <!-- 分类标签：直接点选 -->
            <div class="flex flex-wrap items-center gap-1">
              <span class="text-[11px] text-gray-400 shrink-0">分类：</span>
              <button
                v-for="cat in wfCategories"
                :key="cat"
                type="button"
                @click="setCategory(w, cat)"
                class="text-[11px] px-2 py-0.5 rounded-full border cursor-pointer transition-colors"
                :class="w.category === cat
                  ? 'bg-blue-500 text-white border-blue-500'
                  : 'bg-white text-gray-500 border-gray-200 hover:border-blue-300 hover:text-blue-500'"
              >{{ cat }}</button>
              <!-- 工作流当前分类已不在分类列表中（历史遗留） -->
              <button
                v-if="w.category && !wfCategories.includes(w.category)"
                type="button"
                @click="setCategory(w, w.category)"
                class="text-[11px] px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-600 cursor-pointer"
                title="该分类不在分类标签列表中，点击清除"
              >{{ w.category }} ✕</button>
              <span v-if="!wfCategories.length" class="text-[11px] text-gray-300">请先在上方添加分类标签</span>
            </div>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs text-gray-500">{{ status }}</span>
      </div>
    </div>
  </div>
</template>
