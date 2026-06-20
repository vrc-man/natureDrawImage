<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, fmt } from './useAdminApi'

defineProps<{ visible: boolean }>()

const reports = ref<any[]>([])
const count = ref(0)

async function load() {
  try {
    const d = await api('GET', '/api/admin/reports')
    reports.value = d.reports || []
    count.value = reports.value.length
  } catch {}
}

async function resolve(id: number, action: string) {
  const labels: Record<string, string> = {
    delete: '删图',
    ban_creator: '封禁绘图者',
    ban_reporter: '封禁举报者',
    dismiss: '忽略',
  }
  if (!confirm(`确认${labels[action] || action}？`)) return
  try {
    await api('POST', '/api/admin/report/resolve', { report_id: id, action })
    load()
  } catch (e: any) {
    alert('操作失败: ' + e.message)
  }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <div class="space-y-3">
      <div v-for="r in reports" :key="r.id" class="border border-gray-100 rounded-xl p-3">
        <div class="flex items-start gap-3">
          <img v-if="r.image_exists !== false" :src="'/api/output/thumb?path=' + encodeURIComponent(r.image_path || '')" class="lb-thumb w-24 h-24 rounded-lg object-cover shrink-0 bg-gray-50 cursor-pointer" :data-path="r.image_path" />
          <div v-else class="w-24 h-24 rounded-lg bg-gray-100 flex items-center justify-center text-[10px] text-gray-400 shrink-0">已删除</div>
          <div class="flex-1 min-w-0 text-xs space-y-0.5">
            <div class="truncate text-gray-600 font-mono text-[10px]">{{ r.image_path }}</div>
            <div class="text-gray-500 mt-1">{{ r.reason }}</div>
            <div class="text-[10px] text-gray-400 mt-1">
              <span>{{ r.timestamp ? fmt(r.timestamp) : '' }}</span>
            </div>
            <div class="text-[10px] text-gray-400">
              绘图者 IP：<span class="font-mono">{{ r.creator_ip || '未知' }}</span>
              &nbsp;|&nbsp; 举报者 IP：<span class="font-mono">{{ r.reporter_ip || '未知' }}</span>
            </div>
          </div>
        </div>
        <div class="flex gap-2 mt-2 ml-[108px]">
          <button @click="resolve(r.id, 'delete')" class="px-2 py-0.5 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0 text-[10px]">删图</button>
          <button @click="resolve(r.id, 'ban_creator')" class="px-2 py-0.5 bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer border-0 text-[10px]">封禁绘图者</button>
          <button @click="resolve(r.id, 'ban_reporter')" class="px-2 py-0.5 bg-orange-500 text-white rounded hover:bg-orange-600 cursor-pointer border-0 text-[10px]">封禁举报者</button>
          <button @click="resolve(r.id, 'dismiss')" class="px-2 py-0.5 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 cursor-pointer border-0 text-[10px]">忽略</button>
        </div>
      </div>
    </div>
    <div v-if="!reports.length" class="text-xs text-gray-400 py-6 text-center">暂无举报</div>
    <button @click="load" class="mt-3 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
  </div>
</template>
