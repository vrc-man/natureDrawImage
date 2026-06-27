<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, resizeImage, batchUploadThumbnails, type BatchThumbItem } from './useAdminApi'
import { showCenterToast } from '@/composables/useToast'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([])
const status = ref('')
let timer: any = null

async function load() {
  try {
    const d = await api('GET', '/api/admin/characters')
    items.value = (d.characters || []).map((c: any) => ({ name: c.name || '', tags: c.tags || '', image: c.image || '', category: c.category || '' }))
  } catch {}
}

async function save() {
  try {
    status.value = '保存中…'
    await api('POST', '/api/admin/characters', { characters: items.value })
    status.value = '✓ 已保存'
    setTimeout(() => { if (status.value === '✓ 已保存') status.value = '' }, 2000)
  } catch (e: any) { status.value = '保存失败: ' + e.message }
}

function debounce() { clearTimeout(timer); status.value = '保存中…'; timer = setTimeout(save, 600) }

function add() {
  items.value.push({ name: '', tags: '', image: '', category: '' })
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
      const r = await fetch('/api/admin/character_thumbnail', { method: 'POST', body: fd })
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText) }
      const d = await r.json()
      if (d.filename && items.value[i]) items.value[i].image = d.filename
      debounce()
    } catch (e: any) { status.value = '上传失败: ' + e.message }
  }; inp.click()
}

const batchUploading = ref(false)
const batchResult = ref('')
const charCategories = ref<string[]>(['VOCALOID', '原创', '东方', '碧蓝航线', '原神', '明日方舟'])
const catInput = ref('')
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
      const d = await batchUploadThumbnails('/api/admin/character_thumbnail_batch', files)
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
    <div class="flex items-center justify-end mb-2">
      <button @click="load" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer">刷新</button>
    </div>
    <div>
      <p class="text-xs text-gray-500 mb-2">配置可选角色。tags 为必填项（英文 Danbooru 标签），名称为可选别名（不填则前端直接显示 tags）。用户选择角色后，tags 会被追加到 prompt 中画风之后。</p>
	      <!-- 角色分类标签管理 -->
	      <div class="mb-3 border rounded p-3 bg-blue-50">
	        <div class="text-sm font-semibold mb-2">📁 角色分类标签管理</div>
	        <div class="flex flex-wrap gap-1 mb-2">
	          <span v-for="cat in charCategories" :key="cat" class="inline-flex items-center text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">
	            {{ cat }}
	            <button @click="charCategories = charCategories.filter(c => c !== cat)" class="ml-1 text-[10px] opacity-60 hover:opacity-100 border-0 bg-transparent cursor-pointer">✕</button>
	          </span>
	        </div>
	        <div class="flex gap-2">
	          <input v-model="catInput" @keydown.enter="charCategories.push(catInput); catInput = ''" type="text" placeholder="输入新分类名称" class="flex-1 border rounded px-2 py-1 text-xs outline-none" />
	          <button @click="charCategories.push(catInput); catInput = ''" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs border-0 cursor-pointer">添加分类</button>
	        </div>
	      </div>
      <div class="mb-3 border rounded p-3 bg-amber-50">
        <div class="flex items-center gap-2 flex-wrap">
          <button @click="batchUpload" :disabled="batchUploading" class="text-xs px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600 border-0 cursor-pointer disabled:opacity-50">⬆️ 批量上传缩略图</button>
          <span class="text-xs text-gray-500">{{ batchResult }}</span>
        </div>
        <p class="text-[11px] text-gray-500 mt-1.5">
          可一次选多张图片。文件名（去扩展名）需与角色<b>别名完全一致且区分大小写</b>。未填别名的角色无法批量匹配，请手动上传。上传后会自动生成 512×512 WebP 缩略图。
        </p>
        <div v-if="batchDetails.length" class="mt-2 max-h-40 overflow-y-auto text-[11px] space-y-0.5">
          <div v-for="(r, i) in batchDetails" :key="i" class="flex items-center gap-1.5">
            <span v-if="r.status === 'ok'" class="text-green-600">✓</span>
            <span v-else-if="r.status === 'unmatched'" class="text-amber-600">⚠</span>
            <span v-else class="text-red-500">✗</span>
            <span class="font-mono text-gray-600">{{ r.filename }}</span>
            <span v-if="r.status === 'ok'" class="text-gray-400">→ {{ r.matched.length }} 个角色</span>
            <span v-else-if="r.status === 'unmatched'" class="text-amber-600">未找到匹配角色</span>
            <span v-else class="text-red-500">{{ r.error }}</span>
          </div>
        </div>
      </div>
      <div class="flex flex-col gap-2 mb-3">
        <div v-for="(c, i) in items" :key="i" class="flex items-start gap-2 p-2 border rounded bg-gray-50">
          <div class="flex-shrink-0 flex flex-col items-center gap-1">
            <img v-if="c.image" :src="'/api/character_thumbnail?name=' + encodeURIComponent(c.image)" class="w-12 h-12 object-cover rounded bg-gray-50" alt="" />
            <div v-else class="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-300 text-[10px]">无图</div>
            <label class="text-[10px] text-blue-600 cursor-pointer hover:underline" @click.prevent="uploadThumb(i)">上传</label>
          </div>
          <div class="flex flex-col gap-1 flex-1 text-sm">
            <textarea v-model="c.tags" @input="debounce()" rows="2" placeholder="英文 tags（必填，逗号分隔）" class="border rounded px-2 py-1 font-mono text-xs resize-none outline-none"></textarea>
            <input v-model="c.name" @input="debounce()" placeholder="别名（可选，不填则显示 tags）" class="border rounded px-2 py-1 outline-none" />
                        <!-- 分类标签：点选 -->
            <div class="flex flex-wrap items-center gap-1">
              <span class="text-[11px] text-gray-400 shrink-0">分类：</span>
              <button
                v-for="cat in charCategories"
                :key="cat"
                type="button"
                @click="c.category = c.category === cat ? '' : cat; debounce()"
                class="text-[11px] px-2 py-0.5 rounded-full border cursor-pointer transition-colors"
                :class="c.category === cat
                  ? 'bg-blue-500 text-white border-blue-500'
                  : 'bg-white text-gray-500 border-gray-200 hover:border-blue-300 hover:text-blue-500'"
              >{{ cat }}</button>
            </div>
          </div>
          <div class="flex flex-col gap-1">
            <button @click="move(i, -1)" :disabled="i === 0" class="text-xs px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer disabled:opacity-50">▲</button>
            <button @click="move(i, 1)" :disabled="i === items.length - 1" class="text-xs px-2 py-1 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer disabled:opacity-50">▼</button>
            <button @click="del(i)" class="text-xs px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 border-0 cursor-pointer">✕</button>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="add" class="px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600 text-sm border-0 cursor-pointer">+ 添加角色</button>
        <span class="text-xs text-gray-500">{{ status }}</span>
      </div>
    </div>
  </div>
</template>
