<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const enabled = ref(false)
const loading = ref(true)
const status = ref('')
const opStatus = ref('')
const running = ref(false)
const pid = ref<number | null>(null)
const startedAt = ref<number | null>(null)
const exitCode = ref<number | null>(null)
const port = ref(8188)
const lastAction = ref('')
const logTab = ref<'launcher' | 'comfy'>('launcher')
const launcherLog = ref<string[]>([])
const comfyLog = ref<string[]>([])
const follow = ref(false)
const busy = ref(false)
const logStatus = ref('')

let pollTimer: ReturnType<typeof setInterval> | null = null
let followTimer: ReturnType<typeof setInterval> | null = null

async function loadStatus() {
  try {
    const d = await api('GET', '/api/admin/comfy-manager/status')
    enabled.value = !!d.enabled
    if (enabled.value) {
      running.value = !!d.running
      pid.value = d.pid ?? null
      startedAt.value = d.started_at ?? null
      exitCode.value = d.exit_code ?? null
      port.value = d.port ?? 8188
      lastAction.value = d.last_action || ''
      status.value = ''
    }
  } catch (e: any) {
    status.value = '加载失败: ' + e.message
  } finally {
    loading.value = false
  }
}

async function loadLogs(tail = 200, source: 'launcher' | 'comfy' = logTab.value) {
  if (!enabled.value) return
  try {
    const d = await api('GET', `/api/admin/comfy-manager/logs?tail=${tail}&source=${source}`)
    const lines = (d.log || []).slice(-tail)
    if (source === 'comfy') comfyLog.value = lines
    else launcherLog.value = lines
    logStatus.value = ''
  } catch (e: any) {
    logStatus.value = '日志加载失败: ' + e.message
  }
}

function switchTab(t: 'launcher' | 'comfy') {
  logTab.value = t
  loadLogs(200, t)
}

async function doStart() {
  if (busy.value) return
  busy.value = true; opStatus.value = '启动中…'
  try {
    const d = await api('POST', '/api/admin/comfy-manager/start')
    opStatus.value = d.ok ? '✓ 已启动' : '✗ ' + (d.error || '启动失败')
    await loadStatus(); await loadLogs()
  } catch (e: any) { opStatus.value = '✗ ' + e.message }
  finally { busy.value = false }
}

async function doStop() {
  if (busy.value) return
  if (!confirm('确定强制结束 ComfyUI 进程？')) return
  busy.value = true; opStatus.value = '停止中…'
  try {
    const d = await api('POST', '/api/admin/comfy-manager/stop')
    opStatus.value = d.ok ? '✓ 已停止' : '✗ ' + (d.error || '停止失败')
    await loadStatus(); await loadLogs()
  } catch (e: any) { opStatus.value = '✗ ' + e.message }
  finally { busy.value = false }
}

async function doRestart() {
  if (busy.value) return
  if (!confirm('将强制停止并重新启动 ComfyUI，确认继续？')) return
  busy.value = true; opStatus.value = '重启中…'
  try {
    const d = await api('POST', '/api/admin/comfy-manager/restart')
    opStatus.value = d.ok ? '✓ 重启指令已发出' : '✗ ' + (d.error || '重启失败')
    await loadStatus(); await loadLogs()
  } catch (e: any) { opStatus.value = '✗ ' + e.message }
  finally { busy.value = false }
}

onMounted(() => {
  loadStatus()
  pollTimer = setInterval(loadStatus, 5000)
  followTimer = setInterval(() => { if (follow.value && enabled.value) loadLogs(200, logTab.value) }, 1000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (followTimer) clearInterval(followTimer)
})
</script>

<template>
  <div v-if="!loading && !enabled" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <p class="text-xs text-gray-500">
      ⚙️ ComfyUI 启动器管理<strong>未启用</strong>。请在 <code class="bg-gray-100 px-1 rounded">.env</code> 配置
      <code class="bg-gray-100 px-1 rounded">COMFY_MANAGER_URL</code> / <code class="bg-gray-100 px-1 rounded">COMFY_MANAGER_KEY</code>
      / <code class="bg-gray-100 px-1 rounded">COMFY_MANAGER_CONFIRM_KEY</code> 后重启后端。
    </p>
  </div>

  <div v-else-if="enabled" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <!-- 状态 -->
    <div class="flex flex-wrap items-center gap-3 mb-3">
      <span class="inline-flex items-center gap-1 text-sm font-semibold" :class="running ? 'text-emerald-600' : 'text-gray-500'">
        <span class="w-2.5 h-2.5 rounded-full inline-block" :class="running ? 'bg-emerald-500' : 'bg-gray-300'"></span>
        {{ running ? '● 运行中' : '○ 已停止' }}
      </span>
      <span v-if="running && pid" class="text-xs text-gray-500">PID: {{ pid }}</span>
      <span v-if="startedAt" class="text-xs text-gray-500">启动于 {{ new Date(startedAt * 1000).toLocaleTimeString('zh-CN') }}</span>
      <span v-if="!running && exitCode != null" class="text-xs text-amber-600">上次退出码: {{ exitCode }}</span>
      <span v-if="lastAction" class="text-xs text-gray-400">最近操作: {{ lastAction }}</span>
      <span class="text-xs text-gray-400">端口: {{ port }}</span>
    </div>

    <!-- 操作按钮 -->
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <button @click="doStart" :disabled="busy"
        class="px-4 py-1.5 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 disabled:opacity-40 text-sm cursor-pointer border-0">🚀 启动</button>
      <button @click="doStop" :disabled="busy"
        class="px-4 py-1.5 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-40 text-sm cursor-pointer border-0">⏹ 停止</button>
      <button @click="doRestart" :disabled="busy"
        class="px-4 py-1.5 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-40 text-sm cursor-pointer border-0">🔄 重启</button>
      <span class="text-xs text-gray-500">{{ opStatus }}</span>
    </div>

    <!-- 日志 -->
    <div class="flex items-center justify-between mb-1">
      <div class="flex items-center gap-2">
        <button @click="switchTab('launcher')"
          class="px-3 py-1 text-xs rounded-full border cursor-pointer"
          :class="logTab === 'launcher' ? 'bg-pink-500 text-white border-pink-500' : 'bg-white text-gray-500 border-gray-200 hover:border-pink-300'">启动器 / API</button>
        <button @click="switchTab('comfy')"
          class="px-3 py-1 text-xs rounded-full border cursor-pointer"
          :class="logTab === 'comfy' ? 'bg-pink-500 text-white border-pink-500' : 'bg-white text-gray-500 border-gray-200 hover:border-pink-300'">ComfyUI</button>
      </div>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-1 text-xs text-gray-500 cursor-pointer">
          <input type="checkbox" v-model="follow" class="accent-pink-500" /> 自动跟随
        </label>
        <button @click="loadLogs(200, logTab)" class="text-xs text-pink-500 hover:underline cursor-pointer bg-transparent border-0">刷新</button>
        <button @click="logTab === 'comfy' ? comfyLog = [] : launcherLog = []" class="text-xs text-gray-400 hover:text-pink-500 cursor-pointer bg-transparent border-0">清空</button>
      </div>
    </div>
    <div class="bg-gray-950 text-gray-100 rounded-lg p-2 h-64 overflow-auto font-mono text-xs">
      <template v-if="logTab === 'comfy'">
        <div v-for="(line, i) in comfyLog" :key="i" class="whitespace-pre-wrap break-all">{{ line }}</div>
        <div v-if="!comfyLog.length" class="text-gray-500">暂无 ComfyUI 日志（启动后自动刷新）</div>
      </template>
      <template v-else>
        <div v-for="(line, i) in launcherLog" :key="i" class="whitespace-pre-wrap break-all">{{ line }}</div>
        <div v-if="!launcherLog.length" class="text-gray-500">暂无启动器日志</div>
      </template>
    </div>
    <p v-if="logStatus" class="text-xs text-red-500 mt-1">{{ logStatus }}</p>
  </div>
</template>
