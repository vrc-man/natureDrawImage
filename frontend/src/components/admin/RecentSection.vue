<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, fmt, copyText, onlineGithubIds } from './useAdminApi'

defineProps<{ visible: boolean }>()

const images = ref<any[]>([])
const page = ref(0)
const total = ref(0)
const pageSize = 12
const bannedSet = ref<Set<string>>(new Set())
const featuredSet = ref<Set<string>>(new Set())
const autoEnabled = ref(false)
const interval = ref(30)
const nameSearch = ref('')
let autoTimer: any = null

const shown = computed(() => images.value.length)
const totalPages = computed(() => Math.ceil(total.value / pageSize) || 1)
const startItem = computed(() => page.value * pageSize + 1)
const endItem = computed(() => Math.min(startItem.value + shown.value - 1, total.value))

function stopAuto() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null }
}

function startAuto() {
  stopAuto()
  if (!autoEnabled.value || page.value !== 0) return
  autoTimer = setInterval(() => loadRecent(), (interval.value || 30) * 1000)
}

function toggleAuto() {
  autoEnabled.value = !autoEnabled.value
  if (autoEnabled.value) startAuto()
  else stopAuto()
}

async function loadRecent() {
  try {
    await refreshSets()
    let u = `/api/admin/recent?limit=${pageSize}&offset=${page.value * pageSize}`
    if (nameSearch.value.trim()) u += '&name=' + encodeURIComponent(nameSearch.value.trim())
    const d = await api('GET', u)
    images.value = d.items || []
    total.value = d.total || 0
    startAuto()
  } catch {}
}

function searchByName() { page.value = 0; loadRecent() }
function resetSearch() { nameSearch.value = ''; page.value = 0; loadRecent() }

async function refreshSets() {
  try {
    const [bans, featured] = await Promise.all([
      api('GET', '/api/admin/bans').catch(() => ({ banned: [] })),
      api('GET', '/api/admin/featured').catch(() => ({ items: [] })),
    ])
    bannedSet.value = new Set((bans.banned || []).filter(Boolean))
    featuredSet.value = new Set((featured.items || []).map((p: any) => typeof p === 'string' ? p : p.path || '').filter(Boolean))
  } catch {}
}

async function del(path: string) {
  try {
    await api('POST', '/api/admin/delete', { path })
    images.value = images.value.filter(i => i.path !== path)
    total.value = Math.max(0, total.value - 1)
  } catch (e: any) { alert('删除失败: ' + e.message) }
}

async function ban(ip: string) {
  if (!ip || !confirm('封禁 IP ' + ip + ' ？')) return
  if (prompt('确认封禁') !== '确认封禁') { alert('输入不匹配'); return }
  try {
    await api('POST', '/api/admin/ban', { ip })
    bannedSet.value.add(ip)
  } catch (e: any) { alert('封禁失败: ' + e.message) }
}

async function toggleFeatured(path: string) {
  try {
    if (featuredSet.value.has(path)) {
      await api('POST', '/api/admin/featured/remove', { path })
      featuredSet.value.delete(path)
    } else {
      await api('POST', '/api/admin/featured/add', { path })
      featuredSet.value.add(path)
    }
  } catch (e: any) { alert('操作失败: ' + e.message) }
}

function prev() {
  if (page.value > 0) { page.value--; loadRecent() }
}

function next() {
  if (page.value + 1 < totalPages.value) { page.value++; loadRecent() }
}

function goPage(p: number) {
  page.value = p; loadRecent()
}

function resetPage() {
  page.value = 0; loadRecent(); refreshSets()
}

function copyIp(ip: string, el: HTMLElement | null) {
  copyText(ip, el)
}

onMounted(() => { loadRecent(); refreshSets() })
onUnmounted(() => stopAuto())

const pageWindow = computed(() => {
  const tp = totalPages.value
  if (tp <= 1) return []
  const p = page.value
  const s = Math.max(0, p - 2)
  const e = Math.min(tp - 1, p + 2)
  const items: (number | 'left' | 'right')[] = []
  if (p > 0) items.push(p - 1)
  if (s > 0) items.push('left')
  for (let i = s; i <= e; i++) items.push(i)
  if (e < tp - 1) items.push('right')
  if (p < tp - 1) items.push(p + 1)
  return items
})
</script>

<template>
  <div v-if="visible" class="bg-white rounded shadow p-4 mb-4">
    <div class="flex items-center justify-between mb-2 gap-2 flex-wrap">
      <div class="flex items-center gap-1">
        <input v-model="nameSearch" type="text" placeholder="图片名搜索" class="border rounded px-2 py-1 text-xs w-32 outline-none" @keyup.enter="searchByName" />
        <button @click="searchByName" class="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 cursor-pointer border-0">搜索</button>
        <button @click="resetSearch" class="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 cursor-pointer border-0">重置</button>
      </div>
      <div class="flex gap-2">
        <button @click="resetPage" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0">刷新</button>
        <button @click="toggleAuto"
          class="text-sm px-3 py-1 rounded hover:bg-green-600 cursor-pointer border-0 transition-colors"
          :class="autoEnabled ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'">
          {{ autoEnabled ? '自动刷新' : '自动刷新: 关' }}
        </button>
        <input v-model.number="interval" type="number" min="5" max="300"
          class="w-12 text-xs text-center border rounded py-1" title="刷新间隔(秒)" />
      </div>
    </div>
    <div>
      <div v-if="!images.length" class="text-gray-400 text-sm">暂无</div>
      <div v-else id="recent-grid" class="grid grid-cols-3 sm:grid-cols-6 gap-2">
        <div v-for="img in images" :key="img.path" class="border rounded p-1 bg-gray-50">
          <img :src="'/api/output/thumb?path=' + encodeURIComponent(img.path || '')" loading="lazy"
            class="lb-thumb w-full aspect-square object-cover rounded bg-white cursor-pointer"
            :data-path="img.path" :data-mtime="img.mtime || ''" :data-ip="img.ip || img.client_ip || '?'" />
          <div class="text-[10px] mt-1 break-all">{{ img.path }}</div>
          <div class="text-[10px] text-gray-500">{{ fmt(img.mtime) }}</div>
          <div class="text-[10px] text-purple-600 truncate" :title="img.creator_email || ''">{{ img.creator_login || '' }}</div>
          <div class="flex items-center justify-between gap-1 mt-1">
            <span @click="copyIp(img.ip || img.client_ip || '', $event.currentTarget as HTMLElement)"
              class="text-[10px] font-mono bg-amber-100 text-amber-800 rounded px-1 truncate max-w-[120px] cursor-pointer"
              :title="img.ip || img.client_ip || '?'">{{ img.ip || img.client_ip || '?' }}</span>
            <span v-if="bannedSet.has(img.ip || img.client_ip)"
              class="text-[10px] bg-gray-300 text-gray-700 rounded px-1">已封</span>
            <button v-else @click="ban(img.ip || img.client_ip)"
              class="text-[10px] bg-red-500 text-white rounded px-1 hover:bg-red-600 cursor-pointer border-0">禁此IP</button>
          </div>
          <button @click="toggleFeatured(img.path)"
            class="mt-1 w-full text-[10px] rounded px-1 py-0.5 hover:bg-amber-600 cursor-pointer border-0"
            :class="featuredSet.has(img.path)
              ? 'bg-amber-500 text-white'
              : 'bg-yellow-100 text-amber-700 border border-amber-300 hover:bg-yellow-200'">
            {{ featuredSet.has(img.path) ? '★ 已精选 (取消)' : '☆ 加入精选' }}
          </button>
          <button @click="del(img.path)"
            class="mt-1 w-full text-[10px] bg-gray-700 text-white rounded px-1 py-0.5 hover:bg-black cursor-pointer border-0">🗑 删图</button>
        </div>
      </div>
      <div v-if="images.length" class="flex items-center gap-2 mt-2">
        <span class="text-xs text-gray-500">显示 {{ startItem }}-{{ endItem }} / {{ total }} 条</span>
        <span class="text-xs text-gray-400">
          <a v-if="page > 0" href="#" @click.prevent="prev" class="text-blue-600 hover:underline mx-1">上一页</a>
          <template v-for="item in pageWindow" :key="typeof item === 'number' ? item : item">
            <span v-if="item === 'left' || item === 'right'" class="mx-1 text-gray-400">...</span>
            <span v-else-if="item === page" class="mx-1 font-bold text-gray-800">{{ item + 1 }}</span>
            <a v-else href="#" @click.prevent="goPage(item as number)" class="text-blue-600 hover:underline mx-1">{{ (item as number) + 1 }}</a>
          </template>
          <a v-if="page + 1 < totalPages" href="#" @click.prevent="next" class="text-blue-600 hover:underline mx-1">下一页</a>
        </span>
      </div>
    </div>
  </div>
</template>
