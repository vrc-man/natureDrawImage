<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api, fmtShort, copyText } from './useAdminApi'

defineProps<{ visible: boolean }>()

// ---- Pagination & Filter ----
const keys = ref<any[]>([])
const total = ref(0)
const pageSize = 20
const currentPage = ref(1)
const filter = ref<'all' | 'unused' | 'used'>('all')
const search = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function loadKeys() {
  const params = new URLSearchParams()
  params.set('limit', String(pageSize))
  params.set('offset', String((currentPage.value - 1) * pageSize))
  if (filter.value === 'used') params.set('used_only', '1')
  if (filter.value === 'unused') params.set('unused_only', '1')
  if (search.value.trim()) params.set('search', search.value.trim())
  try {
    const r = await api('GET', '/api/admin/access-keys?' + params.toString())
    keys.value = r.items || []
    total.value = r.total || 0
  } catch {}
}
watch([filter, currentPage, search], loadKeys)

function goPage(p: number) {
  if (p >= 1 && p <= totalPages.value) currentPage.value = p
}

// ---- Selection ----
const selectedKeys = ref<Set<string>>(new Set())
const lastClickedIdx = ref<number | null>(null)

function toggleOne(keyPreview: string, idx: number, event: MouseEvent) {
  if (event.shiftKey && lastClickedIdx.value !== null) {
    const start = Math.min(lastClickedIdx.value, idx)
    const end = Math.max(lastClickedIdx.value, idx)
    const allKeys = keys.value.slice(start, end + 1).map(k => k.key_preview)
    // 判断第一个点击的状态来决定区间是选中还是取消
    const firstState = selectedKeys.value.has(keys.value[lastClickedIdx.value]?.key_preview)
    // 获取当前区间的统一状态
    const rangeAllSelected = allKeys.every(k => selectedKeys.value.has(k))
    if (rangeAllSelected) {
      allKeys.forEach(k => selectedKeys.value.delete(k))
    } else {
      allKeys.forEach(k => selectedKeys.value.add(k))
    }
  } else {
    if (selectedKeys.value.has(keyPreview)) {
      selectedKeys.value.delete(keyPreview)
    } else {
      selectedKeys.value.add(keyPreview)
    }
  }
  selectedKeys.value = new Set(selectedKeys.value) // trigger reactivity
  lastClickedIdx.value = idx
}

function toggleAll() {
  const allPreviews = keys.value.map(k => k.key_preview)
  const allSelected = allPreviews.every(k => selectedKeys.value.has(k))
  if (allSelected) {
    allPreviews.forEach(k => selectedKeys.value.delete(k))
  } else {
    allPreviews.forEach(k => selectedKeys.value.add(k))
  }
  selectedKeys.value = new Set(selectedKeys.value)
}

const isAllSelected = computed(() => keys.value.length > 0 && keys.value.every(k => selectedKeys.value.has(k.key_preview)))
const selectedCount = computed(() => selectedKeys.value.size)

function clearSelection() { selectedKeys.value = new Set() }

async function batchDelete() {
  if (!selectedCount.value) { alert('请先选择要删除的密钥'); return }
  if (!confirm(`确认彻底删除 ${selectedCount.value} 个密钥？此操作不可恢复！`)) return
  if (prompt('输入"彻底删除"确认') !== '彻底删除') { alert('输入不匹配'); return }
  // 逐个 reveal 取完整 key 再删除
  let success = 0
  for (const preview of selectedKeys.value) {
    try {
      const r = await api('POST', '/api/admin/access-keys/reveal', { key_preview: preview })
      if (r.key) {
        await api('POST', '/api/admin/access-keys/remove', { key: r.key })
        success++
      }
    } catch {}
  }
  clearSelection()
  await loadKeys()
  alert(`批量删除完成：成功 ${success} 个，失败 ${selectedCount.value - success} 个`)
}

// ---- Existing Actions ----
const genCount = ref(10)
const genType = ref<'time' | 'count' | 'both'>('time')
const genDays = ref(0)
const genHours = ref(24)
const genMins = ref(0)
const genMaxUses = ref(10)
const generatedKeys = ref<string[]>([])
const genMsg = ref('')
const newKeyPreviews = ref<Set<string>>(new Set())

async function generateKeys() {
  if (!confirm(`生成 ${genCount.value} 个${genType.value === 'time' ? '计时' : genType.value === 'count' ? '计次' : '混合'}密钥？`)) return
  try {
    const body: any = { count: genCount.value, type: genType.value }
    if (genType.value === 'time' || genType.value === 'both') { body.days = genDays.value; body.hours = genHours.value; body.mins = genMins.value }
    if (genType.value === 'count' || genType.value === 'both') body.max_uses = genMaxUses.value
    const r = await api('POST', '/api/admin/access-keys/generate', body)
    generatedKeys.value = r.keys || []
    newKeyPreviews.value = new Set((r.keys || []).map((k: string) => k.length >= 12 ? k.slice(0, 8) + '...' + k.slice(-4) : k))
    genMsg.value = `✓ 已生成 ${generatedKeys.value.length} 个，并加入列表顶部（请立即复制保存，完整密钥仅此一次显示）`
    await loadKeys()
    setTimeout(() => { newKeyPreviews.value = new Set() }, 5000)
  } catch (e: any) { alert('生成失败: ' + e.message) }
}
function dismissGenerated() { generatedKeys.value = []; genMsg.value = '' }
function isNewKey(k: any): boolean { return newKeyPreviews.value.has(k.key_preview || k.preview || '') }

function statusLabel(k: any): string {
  if (!k) return '未知'
  if (k.disabled) return '已禁用'
  if (k.expired) return '已过期'
  if (k.used_up) return '次数用尽'
  if (k.used && k.used_count > 0) return '已使用'
  if (k.max_uses && k.used_count >= k.max_uses) return '次数用尽'
  if (k.expires_at && k.expires_at * 1000 < Date.now()) return '已过期'
  return '可用'
}
function statusClass(s: string): string {
  const m: Record<string, string> = {
    '禁用中': 'bg-gray-200 text-gray-600',
    '已禁用': 'bg-gray-200 text-gray-600',
    '已过期': 'bg-red-100 text-red-600',
    '次数用尽': 'bg-orange-100 text-orange-600',
    '已使用': 'bg-blue-100 text-blue-600',
    '可用': 'bg-green-100 text-green-600',
  }
  return m[s] || 'bg-gray-100 text-gray-600'
}
function typeLabel(k: any): string {
  if (k.type === 'both') return '时间+次数'
  if (k.type === 'count') return '按次数'
  return '按时间'
}
async function deleteKey(preview: string) {
  if (!confirm('彻底删除密钥 ' + preview + '？此操作不可恢复！')) return
  if (prompt('输入"彻底删除"确认') !== '彻底删除') { alert('输入不匹配'); return }
  try { const r = await api('POST', '/api/admin/access-keys/reveal', { key_preview: preview }); if (r.key) { await api('POST', '/api/admin/access-keys/remove', { key: r.key }); } await loadKeys(); alert('删除完成：成功 1 个，失败 0 个'); clearSelection() } catch (e: any) { alert('删除失败: ' + e.message) }
}
async function enableKey(preview: string) {
  if (!confirm('重新启用密钥 ' + preview + '？')) return
  try { await api('POST', '/api/admin/access-keys/enable', { key_preview: preview }); loadKeys() } catch (e: any) { alert('启用失败: ' + e.message) }
}
async function disableKey(preview: string) {
  if (!confirm('禁用密钥 ' + preview + '？')) return
  if (prompt('确认禁用') !== '确认禁用') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/access-keys/delete', { key_preview: preview }); loadKeys() } catch (e: any) { alert('禁用失败: ' + e.message) }
}
async function removeKey(preview: string) {
  if (!confirm('删除密钥 ' + preview + '？')) return
  if (prompt('确认删除') !== '确认删除') { alert('输入不匹配'); return }
  try { const r = await api('POST', '/api/admin/access-keys/reveal', { key_preview: preview }); if (r.key) { await api('POST', '/api/admin/access-keys/remove', { key: r.key }); } await loadKeys(); alert('删除完成：成功 1 个，失败 0 个'); clearSelection() } catch (e: any) { alert('删除失败: ' + e.message) }
}
async function revealKey(preview: string) {
  try { const r = await api('POST', '/api/admin/access-keys/reveal', { key_preview: preview }); alert('完整密钥：' + r.key) } catch (e: any) { alert('查看失败: ' + e.message) }
}
async function copyFullKey(preview: string, btn: HTMLElement) {
  if (!preview) { alert('无效密钥'); return }
  try {
    const r = await api('POST', '/api/admin/access-keys/reveal', { key_preview: preview })
    if (!r.key) { alert('未取到完整密钥'); return }
    copyText(r.key, btn)
  } catch (e: any) { alert('复制失败: ' + e.message) }
}
async function cleanupKeys() {
  if (!confirm('清理已过期/次数用尽的密钥？')) return
  if (prompt('输入"确认清理"') !== '确认清理') { alert('输入不匹配'); return }
  try { const r = await api('POST', '/api/admin/access-keys/cleanup'); alert(`已清理 ${r.cleaned || 0} 个失效密钥`); loadKeys() } catch (e: any) { alert('清理失败: ' + e.message) }
}

onMounted(loadKeys)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">

    <p class="text-xs text-gray-500 mb-4">管理访问密钥，支持计时、计次或混合类型的密钥。</p>

    <!-- Generate -->
    <div class="mb-6 p-3 bg-gray-50 rounded-xl">
      <h3 class="text-xs font-semibold text-gray-600 mb-2">生成密钥</h3>
      <div class="flex items-center gap-3 text-xs flex-wrap">
        <label>数量：<input type="number" v-model.number="genCount" min="1" max="50" class="w-14 border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
        <label>
          类型：
          <select v-model="genType" class="border border-gray-200 rounded px-1 py-0.5 text-xs">
            <option value="time">按时间</option>
            <option value="count">按次数</option>
            <option value="both">混合</option>
          </select>
        </label>
        <template v-if="genType === 'time' || genType === 'both'">
          <label>天：<input type="number" v-model.number="genDays" min="0" class="w-12 border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
          <label>小时：<input type="number" v-model.number="genHours" min="0" class="w-12 border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
          <label>分钟：<input type="number" v-model.number="genMins" min="0" class="w-12 border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
        </template>
        <template v-if="genType === 'count' || genType === 'both'">
          <label>最大使用：<input type="number" v-model.number="genMaxUses" min="1" class="w-14 border border-gray-200 rounded px-1 py-0.5 text-xs" /></label>
        </template>
        <button @click="generateKeys" class="px-3 py-1 bg-pink-500 text-white rounded hover:bg-pink-600 cursor-pointer border-0 text-xs">生成</button>
      </div>

      <!-- Generated keys display -->
      <div v-if="generatedKeys.length" class="mt-3">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-[11px] text-green-700 flex-1">{{ genMsg }}</span>
          <button @click="dismissGenerated" class="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0 text-[10px] shrink-0">✕ 我已保存</button>
        </div>
        <div class="space-y-1">
          <div v-for="(key, i) in generatedKeys" :key="i" class="bg-green-50 border border-green-200 rounded px-2 py-1 text-xs font-mono text-green-700 cursor-pointer select-all" @click="copyText(key, $event.currentTarget as HTMLElement)" :title="'点击复制'">
            {{ key }}
          </div>
          <p class="text-[10px] text-gray-400 mt-1">点击密钥复制到剪贴板</p>
        </div>
      </div>
    </div>

    <!-- Filter & Batch Actions Bar -->
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <div class="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5 text-xs">
        <button @click="filter='all'; currentPage=1" class="px-2 py-1 rounded-md cursor-pointer border-0 transition-colors" :class="filter==='all'?'bg-white text-gray-800 shadow-sm':'text-gray-500 hover:text-gray-700'">全部</button>
        <button @click="filter='unused'; currentPage=1" class="px-2 py-1 rounded-md cursor-pointer border-0 transition-colors" :class="filter==='unused'?'bg-white text-gray-800 shadow-sm':'text-gray-500 hover:text-gray-700'">未使用</button>
        <button @click="filter='used'; currentPage=1" class="px-2 py-1 rounded-md cursor-pointer border-0 transition-colors" :class="filter==='used'?'bg-white text-gray-800 shadow-sm':'text-gray-500 hover:text-gray-700'">已使用</button>
      </div>
      <input v-model="search" placeholder="搜索密钥/用户…" class="flex-1 min-w-[120px] border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400" @input="currentPage=1" />
      <button @click="loadKeys" class="px-2 py-1 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent shrink-0">🔄 刷新</button>
    </div>

    <!-- Selection Bar -->
    <div v-if="selectedCount > 0" class="flex items-center gap-2 mb-2 px-2 py-1.5 bg-pink-50 rounded-lg text-xs">
      <span class="text-pink-700 font-semibold">已选 {{ selectedCount }} 项</span>
      <button @click="batchDelete" class="px-2 py-0.5 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0">🗑️ 批量删除</button>
      <button @click="clearSelection" class="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">取消选择</button>
      <div class="ml-auto flex items-center gap-1">
        <button @click="cleanupKeys" class="px-2 py-0.5 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0">🧹 清理</button>
      </div>
    </div>
    <div v-else class="flex items-center justify-end mb-2">
      <button @click="cleanupKeys" class="px-2 py-0.5 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0 text-xs">🧹 清理</button>
    </div>

    <!-- Keys List -->
    <div class="mb-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-xs font-semibold text-gray-600">密钥列表 ({{ total }})</h3>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-100">
              <th class="py-1 pr-2 w-8">
                <input type="checkbox" :checked="isAllSelected" @change="toggleAll" class="accent-pink-500 cursor-pointer" :disabled="!keys.length" />
              </th>
              <th class="py-1 pr-2">密钥</th>
              <th class="py-1 pr-2">状态</th>
              <th class="py-1 pr-2">类型</th>
              <th class="py-1 pr-2">用户</th>
              <th class="py-1 pr-2">使用次数</th>
              <th class="py-1 pr-2">创建时间</th>
              <th class="py-1 pr-2">过期时间</th>
              <th class="py-1">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(k, idx) in keys" :key="k.preview || k.id" class="border-b border-gray-50 transition-colors" :class="{ 'bg-yellow-50 ring-1 ring-yellow-300': isNewKey(k), 'bg-pink-50/50': selectedKeys.has(k.key_preview) }">
              <td class="py-1 pr-2">
                <input type="checkbox" :checked="selectedKeys.has(k.key_preview)" @click="toggleOne(k.key_preview, idx, $event)" class="accent-pink-500 cursor-pointer" />
              </td>
              <td class="py-1 pr-2 font-mono text-gray-700" :title="k.key_preview">
                <span v-if="isNewKey(k)" class="inline-block mr-1 px-1 py-0.5 bg-yellow-400 text-white rounded text-[9px] font-sans">新</span>
                {{ k.preview || k.key_preview || (k.key ? k.key.slice(0, 16) + '...' : '-') }}
              </td>
              <td class="py-1 pr-2"><span class="px-1 py-0.5 rounded text-[10px]" :class="statusClass(statusLabel(k))">{{ statusLabel(k) }}</span></td>
              <td class="py-1 pr-2"><span class="px-1 py-0.5 rounded text-[10px] bg-gray-100 text-gray-600">{{ typeLabel(k) }}</span></td>
              <td class="py-1 pr-2">{{ k.login || k.github_id || k.user || '-' }}</td>
              <td class="py-1 pr-2">{{ k.used_count || 0 }}{{ k.max_uses ? '/' + k.max_uses : '' }}</td>
              <td class="py-1 pr-2 text-gray-500 whitespace-nowrap">{{ fmtShort(k.created_at) }}</td>
              <td class="py-1 pr-2 text-gray-500 whitespace-nowrap">{{ k.expires_at ? fmtShort(k.expires_at) : '-' }}</td>
              <td class="py-1 flex flex-wrap gap-1">
                <button @click="copyFullKey(k.preview || k.key_preview, $event.currentTarget as HTMLElement)" class="px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 cursor-pointer border-0 text-[10px]">复制密钥</button>
                <button v-if="k.disabled" @click="enableKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-emerald-100 text-emerald-600 rounded hover:bg-emerald-200 cursor-pointer border-0 text-[10px]">重新启用</button>
                <button v-else @click="disableKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-yellow-100 text-yellow-600 rounded hover:bg-yellow-200 cursor-pointer border-0 text-[10px]">禁用</button>
                <button @click="revealKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 cursor-pointer border-0 text-[10px]">查看</button>
                <button @click="deleteKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px]">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!keys.length" class="text-xs text-gray-400 py-4 text-center">暂无密钥</div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex items-center justify-center gap-1 text-xs">
      <button @click="goPage(1)" :disabled="currentPage<=1" class="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-100 cursor-pointer disabled:cursor-default border-0">&laquo;</button>
      <button @click="goPage(currentPage-1)" :disabled="currentPage<=1" class="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-100 cursor-pointer disabled:cursor-default border-0">&lsaquo;</button>
      <template v-for="p in totalPages" :key="p">
        <button v-if="Math.abs(p - currentPage) <= 2 || p === 1 || p === totalPages" @click="goPage(p)" class="px-2 py-1 rounded cursor-pointer border-0" :class="p===currentPage?'bg-pink-500 text-white':'hover:bg-gray-100'">{{ p }}</button>
        <span v-else-if="p === 2 || p === totalPages - 1" class="px-1 text-gray-400">…</span>
      </template>
      <button @click="goPage(currentPage+1)" :disabled="currentPage>=totalPages" class="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-100 cursor-pointer disabled:cursor-default border-0">&rsaquo;</button>
      <button @click="goPage(totalPages)" :disabled="currentPage>=totalPages" class="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-100 cursor-pointer disabled:cursor-default border-0">&raquo;</button>
    </div>
  </div>
</template>
