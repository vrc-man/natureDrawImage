<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from './useAdminApi'
import { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const props = defineProps<{ visible: boolean }>()

const range = ref('today')
const data = ref<any>(null)
const selectedIndex = ref(0)
const loading = ref(false)
const chartLoading = ref(false)
const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null

// 自动刷新（默认开启30秒）
const autoRefresh = ref(localStorage.getItem('lbAutoRefresh') !== '0')
const refreshInterval = ref(parseInt(localStorage.getItem('lbRefreshInterval') || '30'))
let autoTimer: ReturnType<typeof setInterval> | null = null

const ranges = [
  { key: 'today', label: '日榜' },
  { key: 'weekly', label: '周榜' },
  { key: 'monthly', label: '月榜' },
]

const selectedUser = computed(() => data.value?.items?.[selectedIndex.value] || null)

async function load() {
  loading.value = true
  try {
    const d = await api('GET', `/api/admin/features/gen-leaderboard?range=${range.value}`)
    data.value = d
    if (selectedIndex.value >= (d.items?.length || 0)) selectedIndex.value = 0
  } catch {}
  loading.value = false
  renderChartDelayed()
}

function renderChartDelayed() {
  chartLoading.value = true
  nextTick(() => {
    renderChart()
    setTimeout(() => { chartLoading.value = false }, 350)
  })
}

function selectUser(index: number) {
  selectedIndex.value = index
  renderChartDelayed()
}

function renderChart() {
  if (chart) { chart.destroy(); chart = null }
  const user = selectedUser.value
  if (!user) return
  nextTick(() => {
    const el = canvas.value
    if (!el || el.offsetWidth === 0) return
    const ctx = el.getContext('2d')
    if (!ctx) return
    const hours = user.hourly || []
    const labels = hours.map((_: number, i: number) => String(i).padStart(2, '0') + ':00')
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: '生成数',
          data: hours,
          backgroundColor: hours.map((v: number) =>
            v >= Math.max(...hours) ? 'rgba(244,63,94,0.85)' : 'rgba(244,114,182,0.55)'),
          borderRadius: 3,
          maxBarThickness: 24,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: true } },
        scales: {
          x: { ticks: { font: { size: 9 }, maxRotation: 0 }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { font: { size: 9 }, stepSize: 1, precision: 0 }, grid: { color: '#fce7f3' } },
        },
      },
    })
  })
}

const maxCount = computed(() => {
  if (!data.value?.items?.length) return 1
  return Math.max(...data.value.items.map((i: any) => i.gen_count)) || 1
})

const medals = ['🥇', '🥈', '🥉']

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  localStorage.setItem('lbAutoRefresh', autoRefresh.value ? '1' : '0')
  restartAutoTimer()
}

function changeInterval() {
  localStorage.setItem('lbRefreshInterval', String(refreshInterval.value))
  restartAutoTimer()
}

function restartAutoTimer() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null }
  if (autoRefresh.value) {
    autoTimer = setInterval(() => load(), refreshInterval.value * 1000)
  }
}

watch(range, load)
watch([range, () => data.value?.items?.length], () => {
  nextTick(renderChart)
})

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
  if (chart) chart.destroy()
  if (autoTimer) clearInterval(autoTimer)
})
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <span v-if="data?.total !== undefined" class="text-xs text-gray-400">区间共 <strong class="text-pink-500">{{ data.total.toLocaleString() }}</strong> 张</span>
      </div>
      <div class="flex items-center gap-2">
        <select v-model="range" class="text-xs border border-pink-200 rounded-lg px-2 py-1 bg-white text-gray-600 outline-none focus:border-pink-400 cursor-pointer">
          <option v-for="r in ranges" :key="r.key" :value="r.key">{{ r.label }}</option>
        </select>
        <button @click="load" :disabled="loading" class="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0 disabled:opacity-50">🔄 刷新</button>
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

    <!-- Loading -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-10 gap-2">
      <svg class="animate-spin h-6 w-6 text-pink-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <span class="text-xs text-gray-400">加载中请稍后...</span>
    </div>

    <!-- Empty -->
    <div v-else-if="!data?.items?.length" class="text-center text-xs text-gray-400 py-10">暂无数据</div>

    <!-- Ranking List -->
    <template v-else>
      <div class="space-y-1.5 mb-4">
        <div v-for="(user, i) in data.items" :key="user.login"
          :class="['flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer transition-all border', selectedIndex === i ? 'bg-pink-50 border-pink-200' : 'hover:bg-gray-50 border-transparent']"
          @click="selectUser(i)">
          <span class="text-lg shrink-0">{{ medals[i] || '#' + (i+1) }}</span>
          <span class="text-sm font-medium text-gray-700 truncate flex-1">{{ user.login }}</span>
          <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden hidden sm:block">
            <div class="h-full rounded-full transition-all duration-500" :style="{ width: (user.gen_count / maxCount * 100) + '%' }"
              :class="i === 0 ? 'bg-gradient-to-r from-pink-400 to-rose-400' : i === 1 ? 'bg-gradient-to-r from-sky-400 to-blue-400' : 'bg-gradient-to-r from-amber-400 to-orange-400'">
            </div>
          </div>
          <span class="text-sm font-bold shrink-0" :class="i === 0 ? 'text-rose-500' : i === 1 ? 'text-blue-500' : 'text-orange-500'">{{ user.gen_count.toLocaleString() }}</span>
        </div>
      </div>

      <!-- Detail: selected user's chart + info -->
      <div v-if="selectedUser" class="bg-gray-50 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-medium text-gray-600">{{ selectedUser.login }} 24h 生成分布</span>
          <span class="text-[10px] text-gray-400">
            活跃高峰: <strong>{{ String(selectedUser.peak_hour).padStart(2, '0') }}:00~{{ String(selectedUser.peak_hour).padStart(2, '0') }}:59</strong> ({{ selectedUser.peak_hour_count }}张)
          </span>
        </div>

        <!-- Chart area with loading overlay -->
        <div class="relative h-28">
          <div v-if="chartLoading" class="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-gray-50/80 rounded z-10">
            <svg class="animate-spin h-5 w-5 text-pink-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
            <span class="text-[10px] text-gray-400">加载中请稍后...</span>
          </div>
          <canvas ref="canvas" :class="chartLoading ? 'opacity-30' : 'opacity-100'" class="transition-opacity duration-300"></canvas>
        </div>

        <div v-if="selectedUser.peak_day" class="mt-1.5 text-[10px] text-gray-400 text-center">
          此区间最多产图日: <strong>{{ selectedUser.peak_day }}</strong> ({{ selectedUser.peak_day_count }}张)
        </div>
      </div>
    </template>
  </div>
</template>
