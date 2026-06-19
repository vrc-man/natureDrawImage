<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, fmt, fmtShort, copyText } from './useAdminApi'

defineProps<{ visible: boolean }>()

const keys = ref<any[]>([])
const genCount = ref(10)
const genType = ref<'time' | 'count' | 'both'>('time')
const genDays = ref(0)
const genHours = ref(24)
const genMins = ref(0)
const genMaxUses = ref(10)
const generatedKeys = ref<string[]>([])

async function loadKeys() {
  try { const r = await api('GET', '/api/admin/access-keys'); keys.value = r.items || [] } catch {}
}

async function generateKeys() {
  if (!confirm(`生成 ${genCount.value} 个${genType.value === 'time' ? '计时' : genType.value === 'count' ? '计次' : '混合'}密钥？`)) return
  try {
    const body: any = { count: genCount.value, type: genType.value }
    if (genType.value === 'time' || genType.value === 'both') { body.days = genDays.value; body.hours = genHours.value; body.mins = genMins.value }
    if (genType.value === 'count' || genType.value === 'both') body.max_uses = genMaxUses.value
    const r = await api('POST', '/api/admin/access-keys/generate', body)
    generatedKeys.value = r.keys || []
    loadKeys()
  } catch (e: any) { alert('生成失败: ' + e.message) }
}

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
  try { await api('POST', '/api/admin/access-keys/remove', { key_preview: preview }); loadKeys() } catch (e: any) { alert('删除失败: ' + e.message) }
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
  try { await api('POST', '/api/admin/access-keys/remove', { key_preview: preview }); loadKeys() } catch (e: any) { alert('删除失败: ' + e.message) }
}
async function revealKey(preview: string) {
  try { const r = await api('POST', '/api/admin/access-keys/reveal', { key_preview: preview }); alert('完整密钥：' + r.key) } catch (e: any) { alert('查看失败: ' + e.message) }
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
    <h2 class="text-sm font-bold text-gray-700 mb-3">🔑 访问密钥管理</h2>

    <p class="text-xs text-gray-500 mb-4">管理访问密钥，支持计时、计次或混合类型的密钥。生成的密钥可用于 API 访问。</p>

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
      <div v-if="generatedKeys.length" class="mt-3 space-y-1">
        <div v-for="(key, i) in generatedKeys" :key="i" class="bg-green-50 border border-green-200 rounded px-2 py-1 text-xs font-mono text-green-700 cursor-pointer select-all" @click="copyText(key, $event.currentTarget as HTMLElement)" :title="'点击复制'">
          {{ key }}
        </div>
        <p class="text-[10px] text-gray-400 mt-1">点击密钥复制到剪贴板</p>
      </div>
    </div>

    <!-- Keys List -->
    <div class="mb-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-xs font-semibold text-gray-600">密钥列表 ({{ keys.length }})</h3>
        <button @click="cleanupKeys" class="px-2 py-0.5 bg-orange-100 text-orange-600 rounded hover:bg-orange-200 cursor-pointer border-0 text-xs">🧹 清理</button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-100">
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
            <tr v-for="k in keys" :key="k.preview || k.id" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-1 pr-2 font-mono text-gray-700">{{ k.preview || k.key_preview || (k.key ? k.key.slice(0, 16) + '...' : '-') }}</td>
              <td class="py-1 pr-2"><span class="px-1 py-0.5 rounded text-[10px]" :class="statusClass(statusLabel(k))">{{ statusLabel(k) }}</span></td>
              <td class="py-1 pr-2"><span class="px-1 py-0.5 rounded text-[10px] bg-gray-100 text-gray-600">{{ typeLabel(k) }}</span></td>
              <td class="py-1 pr-2">{{ k.login || k.github_id || k.user || '-' }}</td>
              <td class="py-1 pr-2">{{ k.used_count || 0 }}{{ k.max_uses ? '/' + k.max_uses : '' }}</td>
              <td class="py-1 pr-2 text-gray-500 whitespace-nowrap">{{ fmtShort(k.created_at) }}</td>
              <td class="py-1 pr-2 text-gray-500 whitespace-nowrap">{{ k.expires_at ? fmtShort(k.expires_at) : '-' }}</td>
              <td class="py-1 flex flex-wrap gap-1">
                <button @click="copyText(k.key || k.preview || '', $event.currentTarget as HTMLElement)" class="px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 cursor-pointer border-0 text-[10px]">复制密钥</button>
                <button v-if="k.disabled" @click="enableKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-emerald-100 text-emerald-600 rounded hover:bg-emerald-200 cursor-pointer border-0 text-[10px]">重新启用</button>
                <button v-else @click="disableKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-yellow-100 text-yellow-600 rounded hover:bg-yellow-200 cursor-pointer border-0 text-[10px]">禁用</button>
                <button @click="revealKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 cursor-pointer border-0 text-[10px]">查看</button>
                <button @click="deleteKey(k.preview || k.key_preview)" class="px-1.5 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px]">彻底删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!keys.length" class="text-xs text-gray-400 py-4 text-center">暂无密钥</div>
    </div>

    <button @click="loadKeys" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
  </div>
</template>
