<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchGPU } from '@/api/endpoints'

const gpuContent = ref('')
let timer: ReturnType<typeof setInterval> | null = null

function gpuBar(value: number, max: number, color: string) {
  const pct = max > 0 ? Math.round(value * 100 / max) : 0
  return `<div class="w-full bg-gray-200 rounded-full h-2 mt-0.5"><div class="h-2 rounded-full transition-all" style="width:${pct}%;background:${color}"></div></div>`
}

async function poll() {
  try {
    const d = await fetchGPU()
    if (d && d.gpus && Array.isArray(d.gpus)) {
      gpuContent.value = d.gpus.map((g: any, i: number) => {
        const utilPct = g.utilization || 0
        const utilColor = utilPct > 90 ? '#ef4444' : utilPct > 70 ? '#f59e0b' : '#34d399'
        const memPct = g.memory_used && g.memory_total ? Math.round(g.memory_used * 100 / g.memory_total) : 0
        const memColor = memPct > 90 ? '#ef4444' : memPct > 70 ? '#f59e0b' : '#34d399'
        const tempColor = g.temperature > 80 ? '#ef4444' : g.temperature > 65 ? '#f59e0b' : '#34d399'
        return `<div class="border-b border-gray-50 pb-2 mb-2 last:border-0 last:mb-0 last:pb-0">
          <div class="flex items-center justify-between text-xs">
            <span class="font-medium text-gray-700">GPU ${i}: ${g.name || ''}</span>
            ${g.temperature !== undefined ? `<span style="color:${tempColor}">${g.temperature}°C</span>` : ''}
          </div>
          <div class="text-[10px] text-gray-400 mt-0.5">利用率 ${utilPct}%</div>
          ${gpuBar(utilPct, 100, utilColor)}
          <div class="text-[10px] text-gray-400 mt-1">
            显存 ${g.memory_used || 0}MB / ${g.memory_total || 0}MB (${memPct}%)
          </div>
          ${gpuBar(g.memory_used || 0, g.memory_total || 1, memColor)}
          ${g.power_draw !== undefined && g.power_limit ? `<div class="text-[10px] text-gray-400 mt-1">功耗 ${g.power_draw}W / ${g.power_limit}W</div>` : ''}
        </div>`
      }).join('')
    } else if (d && d.available === false) {
      gpuContent.value = `<div class="text-xs text-red-500">⚠️ ${d.error || 'GPU 不可用'}</div>`
    } else {
      gpuContent.value = '<div class="text-xs text-gray-400">GPU 状态正常</div>'
    }
  } catch { gpuContent.value = '<div class="text-xs text-gray-400">GPU 状态加载中...</div>' }
}

onMounted(() => {
  poll()
  timer = setInterval(poll, 15000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div class="bg-white/75 backdrop-blur rounded-2xl p-4 border border-pink-100">
    <div class="text-xs text-gray-500 space-y-1" v-html="gpuContent"></div>
  </div>
</template>
