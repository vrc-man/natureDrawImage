<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from './useAdminApi'
import { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const props = defineProps<{ visible: boolean }>()

const todayTotal = ref(0)
const hourlyLabels = ref<string[]>([])
const hourlyData = ref<number[]>([])
const dailyLabels = ref<string[]>([])
const dailyData = ref<number[]>([])
const dateFrom = ref('')
const dateTo = ref('')
const searchLogin = ref('')
const loading = ref(false)

// 自动刷新（默认开启30秒）
const autoRefresh = ref(localStorage.getItem('statsAutoRefresh') !== '0')
const refreshInterval = ref(parseInt(localStorage.getItem('statsRefreshInterval') || '30'))
let autoTimer: ReturnType<typeof setInterval> | null = null

const hourlyCanvas = ref<HTMLCanvasElement | null>(null)
const dailyCanvas = ref<HTMLCanvasElement | null>(null)
let hourlyChart: Chart | null = null
let dailyChart: Chart | null = null

function fill24h(labels: string[], data: number[]) {
  const map: Record<string, number> = {}
  for (let i = 0; i < labels.length; i++) map[labels[i]] = data[i]
  const h: string[] = new Array(24), d: number[] = new Array(24).fill(0)
  for (let i = 0; i < 24; i++) {
    const hour = String(i).padStart(2, '0')
    h[i] = hour + ':00'
    d[i] = map[hour] || 0
  }
  return { h, d }
}

function fill7d(labels: string[], data: number[]) {
  const days: string[] = [], counts: number[] = []
  for (let i = 0; i < labels.length; i++) {
    const parts = labels[i].split('-')
    days.push(parts[1] + '/' + parts[2])
    counts.push(data[i] || 0)
  }
  return { days, counts }
}

function queryParams() {
  let url = '/api/admin/stats/generation'
  const params: string[] = []
  params.push('tz_offset=' + (-new Date().getTimezoneOffset() / 60))
  if (dateFrom.value) params.push('date_from=' + (new Date(dateFrom.value + 'T00:00:00').getTime() / 1000))
  if (dateTo.value) params.push('date_to=' + (new Date(dateTo.value + 'T23:59:59').getTime() / 1000))
  if (searchLogin.value.trim()) params.push('login=' + encodeURIComponent(searchLogin.value.trim()))
  if (params.length) url += '?' + params.join('&')
  return url
}

function resetRange() {
  dateFrom.value = ''
  dateTo.value = ''
  searchLogin.value = ''
  load()
}

async function load() {
  loading.value = true
  try {
    const d = await api('GET', queryParams())
    todayTotal.value = d.today_total || 0
    const h = fill24h(
      (d.hourly || []).map((x: any) => x.hour),
      (d.hourly || []).map((x: any) => x.count)
    )
    hourlyLabels.value = h.h
    hourlyData.value = h.d
    const dd = fill7d(
      (d.daily || []).map((x: any) => x.day),
      (d.daily || []).map((x: any) => x.count)
    )
    dailyLabels.value = dd.days
    dailyData.value = dd.counts
  } catch {}
  loading.value = false
}

function makeChart(canvas: HTMLCanvasElement | null, labels: string[], data: number[], label: string, color: string) {
  if (!canvas) return null
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label, data, backgroundColor: color, borderRadius: 4, maxBarThickness: 40 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: {
        x: { ticks: { font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { font: { size: 10 }, stepSize: 1 }, grid: { color: '#f0f0f0' } },
      },
    },
  })
}

function renderCharts() {
  if (hourlyChart) { hourlyChart.destroy(); hourlyChart = null }
  if (dailyChart) { dailyChart.destroy(); dailyChart = null }
  nextTick(() => {
    const hc = hourlyCanvas.value, dc = dailyCanvas.value
    if (!hc || hc.offsetWidth === 0) return
    hourlyChart = makeChart(hc, hourlyLabels.value, hourlyData.value, '生成数', 'rgba(244,114,182,0.7)')
    dailyChart = makeChart(dc!, dailyLabels.value, dailyData.value, '生成数', 'rgba(59,130,246,0.7)')
  })
}

watch([hourlyLabels, dailyLabels], renderCharts)

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  localStorage.setItem('statsAutoRefresh', autoRefresh.value ? '1' : '0')
  restartAutoTimer()
}

function changeInterval() {
  localStorage.setItem('statsRefreshInterval', String(refreshInterval.value))
  restartAutoTimer()
}

function restartAutoTimer() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null }
  if (autoRefresh.value) {
    autoTimer = setInterval(() => load(), refreshInterval.value * 1000)
  }
}

// 每次展开时自动刷新
watch(() => props.visible, (v) => {
  if (v) load()
})

onMounted(() => {
  load()
  if (autoRefresh.value) {
    autoTimer = setInterval(() => load(), refreshInterval.value * 1000)
  }
})

onUnmounted(() => {
  if (autoTimer) clearInterval(autoTimer)
  if (hourlyChart) hourlyChart.destroy()
  if (dailyChart) dailyChart.destroy()
})
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <!-- Header -->
    <div class="flex items-start justify-between mb-3 flex-wrap gap-2">
      <div class="flex items-center gap-3">
        <span class="text-xl font-bold text-pink-600">{{ todayTotal }}</span>
        <span class="text-xs text-gray-400">生图数</span>
      </div>
      <div class="flex items-center gap-2 text-xs flex-wrap">
        <input v-model="searchLogin" type="text" placeholder="用户搜索" class="border rounded px-2 py-1 text-xs outline-none w-24" @keyup.enter="load" />
        <input v-model="dateFrom" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
        <span class="text-gray-400">—</span>
        <input v-model="dateTo" type="date" class="border rounded px-2 py-1 text-xs outline-none" />
        <button @click="load" :disabled="loading" class="px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs cursor-pointer border-0 disabled:opacity-50">🔄 刷新</button>
        <button @click="resetRange" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">重置</button>
      </div>
    </div>

    <!-- Auto-refresh bar -->
    <div class="flex items-center gap-2 mb-3 text-xs text-gray-400">
      <label class="flex items-center gap-1 cursor-pointer select-none">
        <input type="checkbox" :checked="autoRefresh" @change="toggleAutoRefresh" class="w-3.5 h-3.5 accent-pink-500 cursor-pointer" />
        自动刷新
      </label>
      <span v-if="autoRefresh" class="flex items-center gap-1">
        每
        <input v-model.number="refreshInterval" @change="changeInterval" type="number" min="5" max="3600" class="w-14 border border-gray-200 rounded px-1 py-0.5 text-[10px] outline-none bg-white text-center" /> 秒
      </span>
    </div>

    <!-- Charts -->
    <div class="mb-4">
      <div class="text-xs font-medium text-gray-600 mb-2">📊 每小时分布</div>
      <div class="relative h-32">
        <div v-if="loading" class="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-white/60 rounded z-10">
          <svg class="animate-spin h-6 w-6 text-pink-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span class="text-xs text-gray-400">加载中请稍后...</span>
        </div>
        <canvas ref="hourlyCanvas" :class="loading ? 'opacity-30' : 'opacity-100'" class="transition-opacity duration-300"></canvas>
      </div>
    </div>

    <div>
      <div class="text-xs font-medium text-gray-600 mb-2">📈 每日趋势</div>
      <div class="relative h-32">
        <div v-if="loading" class="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-white/60 rounded z-10">
          <svg class="animate-spin h-6 w-6 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span class="text-xs text-gray-400">加载中请稍后...</span>
        </div>
        <canvas ref="dailyCanvas" :class="loading ? 'opacity-30' : 'opacity-100'" class="transition-opacity duration-300"></canvas>
      </div>
    </div>
  </div>
</template>
