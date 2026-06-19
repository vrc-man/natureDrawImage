<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, resizeImage, scanThumbnails, fmt } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([])
const status = ref('')
const scanResult = ref('')
let timer: any = null

async function load() {
  try {
    const d = await api('GET', '/api/admin/styles')
    items.value = (d.styles || []).map((s: any) => ({ name: s.name || '', tags: s.tags || '', image: s.image || '' }))
  } catch {}
}

async function save() {
  try {
    status.value = '保存中…'
    await api('POST', '/api/admin/styles', { styles: items.value })
    status.value = '✓ 已保存'
    setTimeout(() => { if (status.value === '✓ 已保存') status.value = '' }, 2000)
  } catch (e: any) { status.value = '保存失败: ' + e.message }
}

function debounce() { clearTimeout(timer); status.value = '保存中…'; timer = setTimeout(save, 600) }

function add() {
  items.value.push({ name: '', tags: '', image: '' })
  debounce()
}

function move(i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= items.value.length) return
  ;[items.value[i], items.value[j]] = [items.value[j], items.value[i]]
  save()
}

function del(i: number) { items.value.splice(i, 1); save() }

async function uploadThumb(i: number) {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'
  inp.onchange = async () => {
    const f = inp.files![0]; if (!f) return
    try {
      const compressed = await resizeImage(f); const fd = new FormData(); fd.append('file', compressed)
      const r = await fetch('/api/admin/style_thumbnail', { method: 'POST', body: fd })
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText) }
      const d = await r.json()
      if (d.filename && items.value[i]) items.value[i].image = d.filename
      debounce()
    } catch (e: any) { status.value = '上传失败: ' + e.message }
  }; inp.click()
}

async function scan() {
  scanResult.value = ''
  try {
    const d = await scanThumbnails('styles')
    const r = d.styles || {}
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
        🖌️ 画风管理
        <span class="ml-2 text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">{{ items.length }}</span>
      </h2>
      <button @click="load" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer">刷新</button>
    </div>
    <div>
      <p class="text-xs text-gray-500 mb-2">配置可选画风。tags 为必填项（英文 Danbooru 标签），名称为可选别名（不填则前端直接显示 tags）。用户选择画风后，tags 会被追加到最终 prompt 最前面。</p>
      <div class="flex items-center gap-2 mb-2">
        <button @click="scan" class="text-xs px-3 py-1 bg-purple-100 text-purple-700 rounded hover:bg-purple-200 border-0 cursor-pointer">📂 扫描缩略图</button>
        <span class="text-xs text-gray-500">{{ scanResult }}</span>
      </div>
      <div class="flex flex-col gap-2 mb-3">
        <div v-for="(s, i) in items" :key="i" class="flex items-start gap-2 p-2 border rounded bg-gray-50">
          <div class="flex-shrink-0 flex flex-col items-center gap-1">
            <img v-if="s.image" :src="'/api/style_thumbnail?name=' + encodeURIComponent(s.image)" class="w-12 h-12 object-cover rounded bg-gray-50" alt="" />
            <div v-else class="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-300 text-[10px]">无图</div>
            <label class="text-[10px] text-blue-600 cursor-pointer hover:underline" @click.prevent="uploadThumb(i)">上传</label>
          </div>
          <div class="flex flex-col gap-1 flex-1 text-sm">
            <textarea v-model="s.tags" @input="debounce()" rows="2" placeholder="英文 tags（必填，逗号分隔）" class="border rounded px-2 py-1 font-mono text-xs resize-none outline-none"></textarea>
            <input v-model="s.name" @input="debounce()" placeholder="别名（可选，不填则显示 tags）" class="border rounded px-2 py-1 outline-none" />
          </div>
          <div class="flex flex-col gap-1">
            <button @click="move(i, -1)" :disabled="i === 0" class="text-xs px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer disabled:opacity-50">▲</button>
            <button @click="move(i, 1)" :disabled="i === items.length - 1" class="text-xs px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer disabled:opacity-50">▼</button>
            <button @click="del(i)" class="text-xs px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 border-0 cursor-pointer">✕</button>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="add" class="px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600 text-sm border-0 cursor-pointer">+ 添加画风</button>
        <span class="text-xs text-gray-500">{{ status }}</span>
      </div>
    </div>
  </div>
</template>
