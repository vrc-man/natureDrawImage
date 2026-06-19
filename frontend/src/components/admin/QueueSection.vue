<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from './useAdminApi'
import { onlineGithubIds, setOnlineUsers } from './useAdminApi'

defineProps<{ visible: boolean }>()

const queueData = ref<any>({})
const onlineList = ref<any[]>([])

async function loadQueue() {
  try {
    const d = await api('GET', '/api/admin/queue')
    queueData.value = d
    onlineList.value = d.online_users || []
    setOnlineUsers(d.online_users || [])
  } catch {}
}

async function cancelItem(id?: number) {
  if (id !== undefined) {
    if (!confirm('确定取消此排队任务？')) return
    await api('POST', '/api/admin/queue/cancel', { item_id: id })
  } else {
    if (!confirm('确定要强制取消当前正在执行的任务吗？')) return
    await api('POST', '/api/admin/queue/cancel', {})
  }
  loadQueue()
}

async function forceUnlock() {
  if (!confirm('确定要强制解锁吗？\n\n仅用于 WebSocket 异常导致锁卡死的情况。如果确实有任务在执行，请先用"取消当前任务"。')) return
  await api('POST', '/api/admin/queue/force-unlock')
  loadQueue()
}

function fmtTime(ts: number) {
  if (!ts) return '?'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

function fmtTimeShort(ts: number) {
  if (!ts) return '?'
  return new Date(ts * 1000).toLocaleTimeString()
}

function elapsed(ts: number) {
  if (!ts) return '?'
  return Math.floor((Date.now() / 1000) - ts) + 's'
}

let pollTimer: any = null
onMounted(() => {
  loadQueue()
  pollTimer = setInterval(loadQueue, 1000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div v-if="visible">
    <!-- Online -->
    <div class="text-sm text-gray-500 mb-1">{{ queueData.online_count || 0 }} 在线</div>
    <div class="text-xs text-gray-400 mb-2">{{ (queueData.online_users || []).map((u:any) => u.login).join(', ') }}</div>

    <div class="text-sm text-gray-500">
      <!-- Current Task -->
      <div v-if="queueData.busy" class="bg-yellow-50 rounded px-2 py-1.5 mb-2 border border-yellow-200">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-semibold text-yellow-700">&#x1F534; 正在生成</span>
          <span v-if="queueData.current_task" class="text-xs font-medium text-gray-700">
            {{ queueData.current_task.login ? queueData.current_task.login + (queueData.current_task.github_id ? ' (#' + queueData.current_task.github_id + ')' : '') : (queueData.current_task.github_id || '?') }}
          </span>
          <span v-if="queueData.current_task" class="text-xs text-gray-500">{{ queueData.current_task.workflow || '?' }}</span>
          <span v-if="queueData.current_task" class="text-[10px] text-gray-400">{{ queueData.current_task.started_at ? fmtTimeShort(queueData.current_task.started_at) : '?' }} ({{ queueData.current_task.started_at ? elapsed(queueData.current_task.started_at) : '?' }})</span>
          <span v-if="queueData.current_task" class="text-[10px] text-gray-400">IP: {{ queueData.current_task.client_ip || '?' }}</span>
        </div>
        <div v-if="queueData.current_task" class="text-[10px] text-gray-500 mt-0.5">提示词: {{ (queueData.current_task.final_prompt || '?').substring(0, 80) }}</div>
      </div>

      <!-- GPU Idle -->
      <div v-else class="bg-green-50 rounded px-2 py-1.5 mb-2 text-xs text-green-600 border border-green-200">
        &#x2705; GPU 空闲，无排队
      </div>

      <!-- Waiting Queue -->
      <div v-if="(queueData.queue || []).filter((x:any) => x.status === 'waiting').length" :class="[queueData.busy ? 'mt-2' : '', 'mb-1']">
        <div class="text-xs text-gray-500 mb-1">排队中 ({{ (queueData.queue || []).filter((x:any) => x.status === 'waiting').length }} 个)：</div>
        <div v-for="(q,i) in (queueData.queue || []).filter((x:any) => x.status === 'waiting')" :key="q.id" class="flex items-center gap-2 bg-gray-50 rounded px-2 py-1 text-[10px] mb-0.5">
          <span class="text-gray-400 w-6">#{{ i+1 }}</span>
          <span class="font-medium">{{ q.login || q.github_id }}</span>
          <span class="text-gray-400">{{ (q.workflow || '?').substring(0, 30) }}</span>
          <span class="text-gray-400 ml-auto">{{ q.created_at ? fmtTimeShort(q.created_at) : '?' }}</span>
          <button @click="cancelItem(q.id)" class="text-[9px] px-1.5 py-0.5 bg-red-400 text-white rounded hover:bg-red-500 cursor-pointer border-0">取消</button>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="mt-3 flex gap-2 items-center">
      <button v-if="queueData.busy" :disabled="queueData.cancel_set" @click="cancelItem()"
        :class="['px-3 py-1 rounded text-sm cursor-pointer border-0', queueData.cancel_set ? 'bg-gray-400 text-white' : 'bg-red-500 text-white hover:bg-red-600']">
        {{ queueData.cancel_set ? '取消中...' : '&#x23F9; 取消当前任务' }}
      </button>
      <button @click="forceUnlock" class="px-3 py-1 bg-orange-500 text-white rounded hover:bg-orange-600 text-sm cursor-pointer border-0">&#x1F513; 强制解锁</button>
      <span class="text-xs text-gray-500"></span>
    </div>
  </div>
</template>