<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, fmt, relTime } from './useAdminApi'

defineProps<{ visible: boolean }>()

const gcStats = ref<any>({})
const gcLogs = ref<any[]>([])
const gcPage = ref(0)
const gcTotal = ref(0)
const gcDateFrom = ref('')
const gcDateTo = ref('')
const gcRunning = ref(false)
const gcResult = ref('')
const autoRefresh = ref(false)
const refreshInterval = ref(30)
let refreshTimer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

async function loadGcStats() {
  try {
    const d = await api('GET', '/api/admin/gc/stats')
    gcStats.value = d
  } catch {}
}

async function loadGcLogs(reset = false) {
  if (reset) { gcPage.value = 0 }
  try {
    let url = `/api/admin/gc/logs?limit=20&offset=${gcPage.value * 20}`
    if (gcDateFrom.value) {
      url += '&min_time=' + encodeURIComponent(String(new Date(gcDateFrom.value).getTime() / 1000))
    }
    if (gcDateTo.value) {
      url += '&max_time=' + encodeURIComponent(String(new Date(gcDateTo.value).setHours(23, 59, 59) / 1000))
    }
    const d = await api('GET', url)
    gcLogs.value = d.items || []
    gcTotal.value = d.total || 0
  } catch {}
}

function filterLogs() {
  gcPage.value = 0
  loadGcLogs()
}

function resetFilter() {
  gcDateFrom.value = ''
  gcDateTo.value = ''
  gcPage.value = 0
  loadGcLogs()
}

function onAutoRefreshChange() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  if (autoRefresh.value) {
    refreshTimer = setInterval(() => {
      loadGcStats()
      loadGcLogs()
    }, refreshInterval.value * 1000)
  }
}

async function runGc(backup: boolean) {
  gcRunning.value = true
  gcResult.value = ''
  try {
    await api('POST', '/api/admin/gc', { backup })
    pollTimer = setInterval(async () => {
      try {
        const d = await api('GET', '/api/admin/gc/status')
        if (d.status === 'done') {
          if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
          gcRunning.value = false
          gcResult.value = 'GC 完成！清理了: ' + JSON.stringify(d.cleaned || {})
          loadGcStats()
          loadGcLogs(true)
          setTimeout(() => { if (gcResult.value.startsWith('GC 完成')) gcResult.value = '' }, 5000)
        } else if (d.status === 'error') {
          if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
          gcRunning.value = false
          gcResult.value = 'GC 出错: ' + (d.error || '未知错误')
          setTimeout(() => { if (gcResult.value.startsWith('GC 出错')) gcResult.value = '' }, 8000)
        }
      } catch (e: any) {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
        gcRunning.value = false
        gcResult.value = '轮询失败: ' + e.message
      }
    }, 1000)
  } catch (e: any) {
    gcRunning.value = false
    gcResult.value = 'GC 启动失败: ' + e.message
  }
}

async function gcWithBackup() {
  if (!confirm('确认执行GC？将先备份再清理。此操作不可恢复。')) return
  if (prompt('确认清理') !== '确认清理') { alert('输入不匹配'); return }
  await runGc(true)
}

async function gcWithoutBackup() {
  if (!confirm('确认执行GC？不备份直接清理。此操作不可恢复。')) return
  if (prompt('确认清理') !== '确认清理') { alert('输入不匹配'); return }
  await runGc(false)
}

async function clearLogs() {
  if (!confirm('确认清空所有 GC 日志？不可恢复。')) return
  if (prompt('确认清空') !== '确认清空') { alert('输入不匹配'); return }
  try {
    await api('POST', '/api/admin/gc/logs/clear')
    gcPage.value = 0
    loadGcLogs()
  } catch (e: any) {
    gcResult.value = '清空失败: ' + e.message
  }
}

const orphanScanRunning = ref(false)
const orphanScanResult = ref('')
const orphanScanDetails = ref<any>(null)
let orphanPollTimer: ReturnType<typeof setInterval> | null = null

async function runOrphanScan() {
  if (!confirm('确认执行孤儿文件清扫？将扫描无 gen_logs 关联的原图，备份到 gcbackups 后删除，并清理关联缩略图。')) return
  if (prompt('确认清扫') !== '确认清扫') { alert('输入不匹配'); return }
  orphanScanRunning.value = true
  orphanScanResult.value = ''
  orphanScanDetails.value = null
  try {
    await api('POST', '/api/admin/gc/orphan-scan')
    orphanPollTimer = setInterval(async () => {
      try {
        const s = await api('GET', '/api/admin/gc/orphan-scan/status')
        if (s.status === 'done') {
          if (orphanPollTimer) { clearInterval(orphanPollTimer); orphanPollTimer = null }
          orphanScanRunning.value = false
          const c = s.cleaned || {}
          const parts = []
          if (c.originals > 0) parts.push(`原图 ${c.originals} 已删`)
          if (c.originals_failed > 0) parts.push(`失败 ${c.originals_failed}`)
          if (c.thumbs > 0) parts.push(`缩略图 ${c.thumbs} 已清`)
          if (c.featured_removed > 0) parts.push(`死精选 ${c.featured_removed} 已清`)
          orphanScanResult.value = parts.length ? '清扫完成：' + parts.join('，') : '清扫完成，无孤儿文件'
          orphanScanDetails.value = s.result || null
          loadGcStats()
        } else if (s.status === 'error') {
          if (orphanPollTimer) { clearInterval(orphanPollTimer); orphanPollTimer = null }
          orphanScanRunning.value = false
          orphanScanResult.value = '孤儿文件清扫出错: ' + (s.error || '未知错误')
        }
      } catch {
        if (orphanPollTimer) { clearInterval(orphanPollTimer); orphanPollTimer = null }
        orphanScanRunning.value = false
      }
    }, 1000)
  } catch (e: any) {
    orphanScanRunning.value = false
    orphanScanResult.value = '孤儿文件清扫启动失败: ' + e.message
  }
}

const cleanDirsRunning = ref(false)
const cleanDirsResult = ref('')

async function runCleanEmptyDirs() {
  if (!confirm('确认清理空目录？只删除 output / thumb_cache / deletion_thumbs 下「YYYY-MM-DD」格式的空目录（跳过今天），非空目录不受影响。')) return
  cleanDirsRunning.value = true
  cleanDirsResult.value = ''
  try {
    const d = await api('POST', '/api/admin/gc/clean-empty-dirs')
    cleanDirsResult.value = `清理完成：删除 ${d.removed ?? 0} 个空日期目录`
    setTimeout(() => { if (cleanDirsResult.value.includes('清理完成')) cleanDirsResult.value = '' }, 5000)
  } catch (e: any) {
    cleanDirsResult.value = '清理失败: ' + e.message
  } finally {
    cleanDirsRunning.value = false
  }
}

// ───── 外挂模块：图片目录健康检查（只读统计，不改任何数据）─────
const healthRunning = ref(false)
const healthResult = ref('')
const healthDetails = ref<any>(null)
let healthPollTimer: ReturnType<typeof setInterval> | null = null

function fmtBytes(n: number) {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return v.toFixed(i ? 1 : 0) + ' ' + u[i]
}

async function runHealthCheck() {
  healthRunning.value = true
  healthResult.value = ''
  healthDetails.value = null
  try {
    const r = await api('POST', '/api/admin/features/health/scan')
    if (!r.ok) { healthRunning.value = false; healthResult.value = r.error || '启动失败'; return }
    healthPollTimer = setInterval(async () => {
      try {
        const s = await api('GET', '/api/admin/features/health/scan/status')
        if (s.status === 'done') {
          if (healthPollTimer) { clearInterval(healthPollTimer); healthPollTimer = null }
          healthRunning.value = false
          healthDetails.value = s
          healthResult.value = '检查完成'
          setTimeout(() => { if (healthResult.value === '检查完成') healthResult.value = '' }, 5000)
        } else if (s.status === 'error') {
          if (healthPollTimer) { clearInterval(healthPollTimer); healthPollTimer = null }
          healthRunning.value = false
          healthResult.value = '检查出错: ' + (s.error || '未知错误')
        }
      } catch {
        if (healthPollTimer) { clearInterval(healthPollTimer); healthPollTimer = null }
        healthRunning.value = false
      }
    }, 1000)
  } catch (e: any) {
    healthRunning.value = false
    healthResult.value = '检查启动失败: ' + e.message
  }
}

onMounted(() => {
  loadGcStats()
  loadGcLogs()
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (pollTimer) clearInterval(pollTimer)
  if (orphanPollTimer) clearInterval(orphanPollTimer)
  if (healthPollTimer) clearInterval(healthPollTimer)
})
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3 text-xs">
      <div class="bg-blue-50 rounded-xl p-3">
        <div class="text-blue-500 text-[10px]">重启次数</div>
        <div class="text-lg font-bold text-blue-700">{{ gcStats.restart_count ?? 0 }}</div>
      </div>
      <div class="bg-green-50 rounded-xl p-3">
        <div class="text-green-500 text-[10px]">累计生图</div>
        <div class="text-lg font-bold text-green-700">{{ gcStats.total_images ?? 0 }}</div>
      </div>
      <div class="bg-purple-50 rounded-xl p-3">
        <div class="text-purple-500 text-[10px]">上次 GC</div>
        <div class="text-lg font-bold text-purple-700">{{ relTime(gcStats.last_gc_time || gcStats.last_gc || 0) }}</div>
      </div>
      <div class="bg-orange-50 rounded-xl p-3">
        <div class="text-orange-500 text-[10px]">在线 / 队列</div>
        <div class="text-lg font-bold text-orange-700">{{ gcStats.online_users ?? 0 }} / {{ gcStats.queue_size ?? 0 }}</div>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2 mb-3">
      <button @click="gcWithBackup" :disabled="gcRunning" class="px-3 py-1 bg-red-500 text-white rounded-lg text-xs hover:bg-red-600 disabled:opacity-40 cursor-pointer border-0">⚠️ 立即执行GC</button>
      <button @click="gcWithoutBackup" :disabled="gcRunning" class="px-3 py-1 bg-orange-500 text-white rounded-lg text-xs hover:bg-orange-600 disabled:opacity-40 cursor-pointer border-0">⚠️ GC不备份</button>
      <button @click="runOrphanScan" :disabled="orphanScanRunning" class="px-3 py-1 bg-purple-500 text-white rounded-lg text-xs hover:bg-purple-600 disabled:opacity-40 cursor-pointer border-0">🧹 孤儿文件清扫</button>
      <button @click="runCleanEmptyDirs" :disabled="cleanDirsRunning" class="px-3 py-1 bg-teal-500 text-white rounded-lg text-xs hover:bg-teal-600 disabled:opacity-40 cursor-pointer border-0">🗂️ 清理空目录</button>
      <button @click="runHealthCheck" :disabled="healthRunning" class="px-3 py-1 bg-sky-500 text-white rounded-lg text-xs hover:bg-sky-600 disabled:opacity-40 cursor-pointer border-0" title="外挂模块：只读扫描，统计图片总数/占用/缺缩略图/孤儿文件">🩺 健康检查</button>
      <button @click="clearLogs" class="px-3 py-1 bg-gray-100 text-gray-600 rounded-lg text-xs hover:bg-gray-200 cursor-pointer border-0">清空日志</button>
      <span v-if="gcRunning" class="text-xs text-amber-500">GC 运行中…</span>
      <span v-if="gcResult" class="text-xs" :class="gcResult.includes('完成') ? 'text-green-500' : gcResult ? 'text-red-400' : ''">{{ gcResult }}</span>
      <span v-if="orphanScanRunning" class="text-xs text-purple-500">孤儿文件清扫中…</span>
      <span v-if="orphanScanResult" class="text-xs" :class="orphanScanResult.includes('完成') ? 'text-green-500' : orphanScanResult.includes('出错') || orphanScanResult.includes('失败') ? 'text-red-400' : ''">{{ orphanScanResult }}</span>
      <span v-if="cleanDirsRunning" class="text-xs text-teal-500">清理空目录中…</span>
      <span v-if="cleanDirsResult" class="text-xs" :class="cleanDirsResult.includes('完成') ? 'text-green-500' : 'text-red-400'">{{ cleanDirsResult }}</span>
      <span v-if="healthRunning" class="text-xs text-sky-500">健康检查扫描中…</span>
      <span v-if="healthResult" class="text-xs" :class="healthResult.includes('完成') ? 'text-green-500' : 'text-red-400'">{{ healthResult }}</span>
    </div>

    <!-- 健康检查结果（外挂模块，只读统计）-->
    <div v-if="healthDetails" class="mb-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
      <div class="bg-sky-50 rounded-xl p-3">
        <div class="text-sky-500 text-[10px]">图片总数</div>
        <div class="text-lg font-bold text-sky-700">{{ healthDetails.total_images ?? 0 }}</div>
      </div>
      <div class="bg-indigo-50 rounded-xl p-3">
        <div class="text-indigo-500 text-[10px]">总占用</div>
        <div class="text-lg font-bold text-indigo-700">{{ fmtBytes(healthDetails.total_size_bytes ?? 0) }}</div>
      </div>
      <div class="bg-amber-50 rounded-xl p-3">
        <div class="text-amber-500 text-[10px]">缺缩略图</div>
        <div class="text-lg font-bold text-amber-700">{{ healthDetails.missing_thumb ?? 0 }}</div>
      </div>
      <div class="bg-rose-50 rounded-xl p-3">
        <div class="text-rose-500 text-[10px]">孤儿文件</div>
        <div class="text-lg font-bold text-rose-700">{{ healthDetails.orphan_files ?? 0 }}</div>
      </div>
    </div>

    <!-- 孤儿清扫详情 -->
    <div v-if="orphanScanDetails" class="mb-3 border rounded p-3 bg-purple-50 text-xs max-h-48 overflow-y-auto">
      <div v-if="orphanScanDetails.backup_dir" class="text-gray-500 mb-1">备份目录：<span class="font-mono">{{ orphanScanDetails.backup_dir }}</span></div>
      <div v-if="orphanScanDetails.originals_deleted?.length" class="mb-2">
        <div class="font-semibold text-green-600 mb-1">✓ 已删原图 ({{ orphanScanDetails.originals_deleted.length }}):</div>
        <div v-for="d in orphanScanDetails.originals_deleted" :key="d.path" class="text-[11px] text-gray-600 pl-2">
          <span class="text-green-500">✓</span> {{ d.path }}
          <span v-if="!d.backed_up" class="text-amber-500 ml-1">未备份</span>
        </div>
      </div>
      <div v-if="orphanScanDetails.originals_failed?.length">
        <div class="font-semibold text-red-600 mb-1">✗ 删除失败 ({{ orphanScanDetails.originals_failed.length }}):</div>
        <div v-for="f in orphanScanDetails.originals_failed" :key="f.path" class="text-[11px] text-red-600 pl-2">
          <span class="text-red-500">✗</span> {{ f.path }} — {{ f.reason }}
        </div>
      </div>
      <div v-if="!orphanScanDetails.originals_deleted?.length && !orphanScanDetails.originals_failed?.length" class="text-gray-400">无孤儿原图</div>
    </div>

    <div class="flex items-center gap-2 mb-2 flex-wrap">
      <input v-model="gcDateFrom" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400 w-[130px]" title="开始日期" />
      <input v-model="gcDateTo" type="date" class="border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400 w-[130px]" title="结束日期" />
      <button @click="filterLogs" class="px-2 py-1 bg-pink-500 text-white rounded-lg text-[10px] cursor-pointer border-0">筛选</button>
      <button @click="resetFilter" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] cursor-pointer border-0">重置</button>
      <label class="flex items-center gap-1 text-[10px] text-gray-500 ml-auto">
        <input type="checkbox" v-model="autoRefresh" @change="onAutoRefreshChange" class="accent-pink-500" />
        自动刷新
      </label>
      <input v-model.number="refreshInterval" @change="onAutoRefreshChange" type="number" min="5" class="w-14 border border-gray-200 rounded-lg px-1.5 py-1 text-[10px] outline-none focus:border-pink-400" title="刷新间隔（秒）" />
      <span class="text-[10px] text-gray-400">秒</span>
    </div>

    <div class="text-xs space-y-1 max-h-64 overflow-y-auto">
      <div v-for="g in gcLogs" :key="g.id || g.timestamp" class="py-1.5 border-b border-gray-50 text-gray-600 flex items-center gap-2">
        <span class="text-[10px] text-gray-400 shrink-0">{{ fmt(g.timestamp || g.created_at || 0) }}</span>
        <span v-if="g.duration" class="text-[10px] text-gray-400 shrink-0">{{ (g.duration / 1000).toFixed(1) }}s</span>
        <span v-if="g.backup" class="text-[9px] bg-amber-100 text-amber-600 px-1 rounded shrink-0" title="已备份">📦</span>
        <div class="flex-1 min-w-0">
          <span v-if="g.cleaned" class="text-[10px]">
            <span v-for="(v, k) in g.cleaned" :key="k" class="mr-1.5"><span class="text-gray-500">{{ k }}:</span> {{ v }}</span>
          </span>
          <span v-else class="text-gray-500">{{ g.message || g.status || '' }}</span>
        </div>
      </div>
      <div v-if="!gcLogs.length" class="text-gray-400 py-4 text-center text-[10px]">暂无 GC 日志</div>
    </div>

    <div class="flex items-center gap-2 mt-2 text-xs">
      <button @click="gcPage--; loadGcLogs()" :disabled="gcPage <= 0" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">上一页</button>
      <span class="text-gray-400">{{ gcPage + 1 }}</span>
      <button @click="gcPage++; loadGcLogs()" class="text-pink-500 hover:underline disabled:text-gray-300 cursor-pointer border-0 bg-transparent">下一页</button>
      <button @click="loadGcStats; loadGcLogs()" class="ml-auto text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
    </div>
  </div>
</template>
