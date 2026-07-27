<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, fmtShort } from './useAdminApi'

defineProps<{ visible: boolean }>()

const items = ref<any[]>([])
const loading = ref(false)
const status = ref('')
const selectMode = ref(false)
const selected = ref<Set<string>>(new Set())

const allSelected = computed(() => items.value.length > 0 && items.value.every(x => selected.value.has(x.token)))

async function load() {
  loading.value = true
  try {
    const d = await api('GET', '/api/admin/features/share/links')
    items.value = d.items || []
  } catch (e: any) { status.value = '加载失败: ' + e.message } finally { loading.value = false }
}

function toggleSelect(token: string) {
  const s = new Set(selected.value)
  if (s.has(token)) s.delete(token); else s.add(token)
  selected.value = s
}

function toggleAll() {
  if (allSelected.value) { selected.value = new Set() }
  else { selected.value = new Set(items.value.map(x => x.token)) }
}

async function revoke(token: string) {
  if (!confirm('确定撤销此分享链接？')) return
  try {
    await api('POST', '/api/admin/features/share/revoke', { token })
    items.value = items.value.filter(x => x.token !== token)
    selected.value.delete(token)
    status.value = '✓ 已撤销'
    setTimeout(() => { if (status.value.startsWith('✓')) status.value = '' }, 3000)
  } catch (e: any) { alert('撤销失败: ' + e.message) }
}

async function revokeSelected() {
  const tokens = [...selected.value]
  if (!tokens.length) return
  if (!confirm(`确定撤销选中的 ${tokens.length} 个分享链接？`)) return
  for (const t of tokens) {
    try { await api('POST', '/api/admin/features/share/revoke', { token: t }) } catch {}
  }
  items.value = items.value.filter(x => !selected.value.has(x.token))
  selected.value = new Set()
  status.value = `✓ 已撤销 ${tokens.length} 个`
  setTimeout(() => { if (status.value.startsWith('✓')) status.value = '' }, 3000)
}

async function revokeAll() {
  if (!confirm('确定撤销所有分享链接？此操作不可恢复')) return
  const tokens = items.value.map(x => x.token)
  for (const t of tokens) {
    try { await api('POST', '/api/admin/features/share/revoke', { token: t }) } catch {}
  }
  items.value = []
  selected.value = new Set()
  status.value = '✓ 已全部撤销'
  setTimeout(() => { if (status.value.startsWith('✓')) status.value = '' }, 3000)
}

function copyLink(url: string) {
  navigator.clipboard.writeText(location.origin + url).then(() => status.value = '✓ 已复制').catch(() => {})
}

// Extend
const extToken = ref('')
const extOpen = ref(false)
const extDownloads = ref(0)
const extHours = ref(0)
const extStatus = ref('')

function openExt(token: string) {
  extToken.value = token
  extDownloads.value = 0
  extHours.value = 0
  extStatus.value = ''
  extOpen.value = true
}

async function doExt() {
  if (!extDownloads.value && !extHours.value) { extStatus.value = '请设置续次数或续时间'; return }
  extStatus.value = '...'
  try {
    await api('POST', '/api/admin/features/share/revoke', { token: extToken.value })
    await api('POST', '/api/output/share/update', { token: extToken.value, add_downloads: extDownloads.value, add_hours: extHours.value })
    extStatus.value = '✅ 已更新'
    await load()
    setTimeout(() => { if (extOpen.value) extOpen.value = false }, 1500)
  } catch (e: any) { extStatus.value = '❌ ' + e.message }
}

function remainingTime(expires_at: number): string {
  if (!expires_at) return '无限'
  const left = expires_at - Date.now() / 1000
  if (left <= 0) return '已过期'
  if (left < 3600) return Math.ceil(left / 60) + ' 分钟'
  if (left < 86400) return Math.round(left / 3600) + ' 小时'
  return Math.round(left / 86400) + ' 天'
}

onMounted(load)
</script>

<template>
  <div v-if="visible">
    <div class="flex items-center justify-between mb-4">
      <div>
        <p class="text-xs text-gray-500">查看和管理所有用户生成的分享链接。服务器重启后所有链接自动失效。</p>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-gray-500">{{ status }}</span>
        <button @click="load" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0">🔄 刷新</button>
        <button v-if="items.length" @click="selectMode = !selectMode; if(!selectMode) selected = new Set()" class="text-sm px-3 py-1 rounded cursor-pointer border-0" :class="selectMode ? 'bg-pink-100 text-pink-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'">☑ 编辑</button>
        <button v-if="items.length" @click="revokeAll" class="text-sm px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0">撤销全部</button>
      </div>
    </div>

    <div v-if="!items.length && !loading" class="text-center text-gray-400 text-sm py-8 border-2 border-dashed border-gray-200 rounded-xl">
      暂无有效分享链接
    </div>

    <div v-if="selectMode && selected.size" class="mb-3 flex items-center gap-2 px-3 py-2 bg-red-50 rounded-xl border border-red-200">
      <span class="text-xs text-red-600 flex-1">已选 {{ selected.size }} 项</span>
      <button @click="revokeSelected" class="text-xs px-3 py-1.5 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0">批量撤销</button>
    </div>

    <div class="space-y-2">
      <div v-for="it in items" :key="it.token" class="border rounded-xl p-3 bg-white hover:shadow-sm transition-shadow border-gray-200">
        <div class="flex items-start justify-between gap-3">
          <div v-if="selectMode" class="flex items-center h-6 shrink-0 pt-0.5">
            <input type="checkbox" :checked="selected.has(it.token)" @change="toggleSelect(it.token)" class="w-4 h-4 accent-pink-500 cursor-pointer" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-xs text-gray-700 truncate" :title="it.path">{{ it.path }}</div>
            <div class="text-[10px] text-gray-400 mt-1">
              创建者: {{ it.created_login || it.created_by }}
              次数: {{ it.downloads }}/{{ it.max_downloads || '∞' }}
              剩余: {{ remainingTime(it.expires_at) }}
              创建: {{ fmtShort(it.created_at) || '-' }}
            </div>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <button @click="copyLink(it.url)" class="text-[10px] px-2 py-1 bg-pink-100 text-pink-600 rounded hover:bg-pink-200 cursor-pointer border-0">复制</button>
            <button v-if="!selectMode" @click="openExt(it.token)" class="text-[10px] px-2 py-1 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 cursor-pointer border-0">续</button>
            <button v-if="!selectMode" @click="revoke(it.token)" class="text-[10px] px-2 py-1 bg-red-100 text-red-500 rounded hover:bg-red-200 cursor-pointer border-0">撤销</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectMode && items.length" class="mt-3 flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-xl border border-gray-200">
      <label class="flex items-center gap-2 text-xs text-gray-600 cursor-pointer select-none">
        <input type="checkbox" :checked="allSelected" @change="toggleAll" class="w-4 h-4 accent-pink-500 cursor-pointer" />
        全选/取消
      </label>
      <span class="text-xs text-gray-400 ml-auto">{{ selected.size }}/{{ items.length }} 已选</span>
    </div>

  </div>

  <!-- Extend Modal (Teleport 到 body，避免父容器 backdrop-filter 影响 fixed) -->
  <Teleport to="body">
    <div v-if="extOpen" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.self="extOpen=false">
      <div class="bg-white rounded-2xl shadow-xl max-w-xs w-full p-4">
        <h4 class="text-sm font-bold text-gray-700 mb-3">📤 续期/续次数</h4>
        <label class="block text-xs text-gray-600 mb-2">
          增加下载次数
          <input v-model.number="extDownloads" type="number" min="0" max="100" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
        </label>
        <label class="block text-xs text-gray-600 mb-3">
          增加有效期（小时）
          <input v-model.number="extHours" type="number" min="0" max="720" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
        </label>
        <div v-if="extStatus" class="mb-2 text-xs" :class="extStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ extStatus }}</div>
        <div class="flex gap-2">
          <button @click="extOpen=false" class="flex-1 py-2 bg-gray-100 rounded-xl hover:bg-gray-200 text-xs text-gray-600 cursor-pointer border-0">取消</button>
          <button @click="doExt" class="flex-1 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-xs font-semibold cursor-pointer border-0">确定</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
