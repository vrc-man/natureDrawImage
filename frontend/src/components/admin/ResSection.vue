<script setup lang="ts">
import { ref } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

interface ResItem {
  w: number
  h: number
  label: string
}

const adminRes = ref<ResItem[]>([])
const resStatus = ref('')
let resTimer: ReturnType<typeof setTimeout> | null = null

async function load() {
  try {
    const d = await api('GET', '/api/admin/resolutions')
    adminRes.value = (d.presets || []).map((r: any) => ({ w: r.w || 1024, h: r.h || 1024, label: r.label || '' }))
  } catch (e: any) {
    resStatus.value = '加载失败: ' + e.message
  }
}

async function save() {
  try {
    resStatus.value = '保存中…'
    await api('POST', '/api/admin/resolutions', { presets: adminRes.value })
    resStatus.value = '✓ 已保存'
    setTimeout(() => { if (resStatus.value === '✓ 已保存') resStatus.value = '' }, 2000)
  } catch (e: any) {
    resStatus.value = '保存失败: ' + e.message
  }
}

function autoSave() {
  if (resTimer) clearTimeout(resTimer)
  resTimer = setTimeout(() => save(), 600)
}

function addPreset() {
  adminRes.value.push({ w: 1024, h: 1024, label: '' })
  autoSave()
}

function removePreset(i: number) {
  adminRes.value.splice(i, 1)
  autoSave()
}

function movePreset(i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= adminRes.value.length) return
  const t = adminRes.value[i]
  adminRes.value[i] = adminRes.value[j]
  adminRes.value[j] = t
  autoSave()
}

load()
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <h2 class="text-sm font-bold text-gray-700 mb-3">🖼️ 分辨率预设</h2>

    <div class="space-y-2 mb-3">
      <div v-for="(r, i) in adminRes" :key="i" class="flex items-center gap-1.5 text-sm bg-gray-50 rounded-xl px-3 py-2">
        <span class="text-[10px] text-gray-400 w-4 shrink-0">{{ i + 1 }}</span>
        <input v-model.number="r.w" type="number" min="64" step="8" class="w-20 border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400" />
        <span class="text-gray-400">×</span>
        <input v-model.number="r.h" type="number" min="64" step="8" class="w-20 border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400" />
        <input v-model="r.label" type="text" class="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400 min-w-0" placeholder="标签" />
        <button @click="movePreset(i, -1)" :disabled="i === 0" class="px-1.5 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 disabled:opacity-30 cursor-pointer border-0 text-[10px]">↑</button>
        <button @click="movePreset(i, 1)" :disabled="i === adminRes.length - 1" class="px-1.5 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 disabled:opacity-30 cursor-pointer border-0 text-[10px]">↓</button>
        <button @click="removePreset(i)" class="px-1.5 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px]">✕</button>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <button @click="addPreset" class="px-3 py-1 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 text-sm cursor-pointer border-0">+ 添加预设</button>
      <button @click="save" class="px-3 py-1 bg-pink-500 text-white rounded-lg hover:bg-pink-600 text-sm cursor-pointer border-0">保存</button>
      <span class="text-xs text-gray-500">{{ resStatus }}</span>
    </div>
  </div>
</template>
