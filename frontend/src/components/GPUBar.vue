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
        const utilPct = g['utilization.gpu'] ?? 0
        const memU = g['memory.used'] ?? 0, memT = g['memory.total'] ?? 1
        const memPct = memT ? Math.round(memU * 100 / memT) : 0
        const temp = g['temperature.gpu']
        const power = g['power.draw'], plim = g['power.limit']
        const pStr = power != null && plim != null ? `${power.toFixed(0)}/${plim.toFixed(0)}W` : power != null ? `${power.toFixed(0)}W` : '?'
        const tempColor = temp >= 80 ? 'text-red-600' : temp >= 70 ? 'text-orange-600' : 'text-emerald-600'
        const utilColor = utilPct >= 90 ? '#ef4444' : utilPct >= 60 ? '#f59e0b' : '#34d399'
        const memColor = memPct >= 90 ? '#ef4444' : memPct >= 70 ? '#f59e0b' : '#f472b6'
        return `<div class="flex flex-wrap gap-2 items-center text-xs py-1">
          <span class="font-medium">${g.name || ''}</span>
          <span>GPU ${utilPct}%</span> ${gpuBar(utilPct, 100, utilColor)}
          <span>VRAM ${memU}/${memT}M</span> ${gpuBar(memU, memT, memColor)}
          ${temp != null ? `<span class="${tempColor}">🌡${temp}°C</span>` : ''}
          <span>⚡${pStr}</span>
        </div>`
      }).join('')
      if (d.poll_interval_ms && timer) {
        clearInterval(timer)
        timer = setInterval(poll, d.poll_interval_ms)
      }
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
