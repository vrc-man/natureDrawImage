<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from './useAdminApi'
import { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

defineProps<{ visible: boolean }>()

const todayTotal = ref(0)
const hourlyLabels = ref<string[]>([])
const hourlyData = ref<number[]>([])
const dailyLabels = ref<string[]>([])
const dailyData = ref<number[]>([])
const dateFrom = ref('')
const dateTo = ref('')
const searchLogin = ref('')

const hourlyCanvas = ref<HTMLCanvasElement | null>(null)
const dailyCanvas = ref<HTMLCanvasElement | null>(null)
let hourlyChart: Chart | null = null
let dailyChart: Chart | null = null

function fill24h(labels: string[], data: number[]) {
  const map: Record<string, number> = {}
  for (let i = 0; i < labels.length; i++) map[labels[i]] = data[i]
  const offset = -new Date().getTimezoneOffset() / 60
  const h: string[] = new Array(24), d: number[] = new Array(24).fill(0)
  for (let i = 0; i < 24; i++) {
    const utcHour = String(i).padStart(2, '0')
    const localIdx = Math.round((i + offset + 24) % 24)
    h[localIdx] = String(localIdx).padStart(2, '0') + ':00'
    d[localIdx] += (map[utcHour] || 0)
  }
  return { h, d }
}

function fill7d(labels: string[], data: number[]) {
  const map: Record<string, number> = {}
  for (let i = 0; i < labels.length; i++) map[labels[i]] = data[i]
  const days: string[] = [], counts: number[] = []
  const now = Date.now()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now - i * 86400000)
    const k = d.toISOString().slice(0, 10)
    const parts = k.split('-')
    days.push(parts[1] + '/' + parts[2])
    counts.push(map[k] || 0)
  }
  return { days, counts }
}

function queryParams() {
  let url = '/api/admin/stats/generation'
  const params: string[] = []
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

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  load()
  timer = setInterval(load, 30000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (hourlyChart) hourlyChart.destroy()
  if (dailyChart) dailyChart.destroy()
})
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
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
        <button @click="load" class="px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs cursor-pointer border-0">查询</button>
        <button @click="resetRange" class="px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs cursor-pointer border-0">重置</button>
      </div>
    </div>

    <div class="mb-4">
      <div class="text-xs font-medium text-gray-600 mb-2">📊 每小时分布</div>
      <div class="h-32"><canvas ref="hourlyCanvas"></canvas></div>
    </div>

    <div>
      <div class="text-xs font-medium text-gray-600 mb-2">📈 每日趋势</div>
      <div class="h-32"><canvas ref="dailyCanvas"></canvas></div>
    </div>
  </div>
</template>
