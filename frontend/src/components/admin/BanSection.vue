<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, fmt } from './useAdminApi'

defineProps<{ visible: boolean }>()

const bans = ref<string[]>([])
const whitelist = ref<string[]>([])
const banInput = ref('')
const wlInput = ref('')
const banSearch = ref('')
const wlSearch = ref('')

const ipImages = ref<any[]>([])
const ipImagesIp = ref('')
const ipImagesSelected = ref<Set<string>>(new Set())

const filteredBans = computed(() =>
  bans.value.filter(ip => ip.includes(banSearch.value))
)

const filteredWhitelist = computed(() =>
  whitelist.value.filter(ip => ip.includes(wlSearch.value))
)

async function loadBans() {
  try {
    bans.value = (await api('GET', '/api/admin/bans')).banned || []
    whitelist.value = (await api('GET', '/api/admin/ip-whitelist')).whitelist || []
  } catch {}
}

async function banIP() {
  const ip = banInput.value.trim()
  if (!ip) return
  if (!confirm('确认封禁 ' + ip + ' ？')) return
  if (prompt('确认封禁') !== '确认封禁') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/ban', { ip }); banInput.value = ''; loadBans() } catch (e: any) { alert('封禁失败: ' + e.message) }
}

async function unbanIP(ip: string) {
  if (!confirm('确认解封 ' + ip + ' ？')) return
  if (prompt('确认解封') !== '确认解封') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/unban', { ip }); loadBans() } catch (e: any) { alert('解封失败: ' + e.message) }
}

async function addWL() {
  const ip = wlInput.value.trim()
  if (!ip) return
  if (!confirm('确认添加白名单 ' + ip + ' ？')) return
  if (prompt('确认添加') !== '确认添加') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/ip-whitelist/add', { ip }); wlInput.value = ''; loadBans() } catch (e: any) { alert('添加失败: ' + e.message) }
}

async function removeWL(ip: string) {
  if (!confirm('确认移除白名单 ' + ip + ' ？')) return
  if (prompt('确认移除') !== '确认移除') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/ip-whitelist/remove', { ip }); loadBans() } catch (e: any) { alert('移除失败: ' + e.message) }
}

async function showIpImages(ip: string) {
  ipImagesIp.value = ip
  ipImagesSelected.value = new Set()
  try {
    const d = await api('GET', '/api/admin/images_by_ip?ip=' + encodeURIComponent(ip))
    ipImages.value = d.items || []
  } catch { ipImages.value = [] }
}

function closeIpImages() {
  ipImagesIp.value = ''
  ipImages.value = []
  ipImagesSelected.value = new Set()
}

function toggleImageSelect(path: string) {
  const s = new Set(ipImagesSelected.value)
  s.has(path) ? s.delete(path) : s.add(path)
  ipImagesSelected.value = s
}

function selectAllImages() {
  ipImagesSelected.value = new Set(ipImages.value.map((i: any) => i.path))
}

async function deleteSelectedImages() {
  const paths = Array.from(ipImagesSelected.value)
  if (!paths.length) return
  if (!confirm('确认删除 ' + paths.length + ' 张图片？')) return
  if (prompt('确认删除') !== '确认删除') { alert('输入不匹配'); return }
  try { await api('POST', '/api/admin/delete_batch', { paths }); ipImagesSelected.value = new Set(); showIpImages(ipImagesIp.value) } catch (e: any) { alert('删除失败: ' + e.message) }
}

onMounted(loadBans)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <div class="flex gap-4">
      <!-- Blacklist -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-xs font-semibold text-red-500">封禁列表 ({{ bans.length }})</span>
          <input v-model="banSearch" placeholder="搜索..." class="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400" />
        </div>
        <div class="text-xs space-y-0.5 mb-2 max-h-64 overflow-y-auto">
          <div v-for="(ip, i) in filteredBans" :key="ip" class="flex items-center justify-between py-1 px-1.5 rounded hover:bg-red-50 group">
            <span class="text-gray-400 mr-1.5 text-[10px] shrink-0">{{ i + 1 }}.</span>
            <a href="#" class="flex-1 truncate text-red-600 hover:text-red-800 no-underline hover:underline" @click.prevent="showIpImages(ip)">{{ ip }}</a>
            <button @click="unbanIP(ip)" class="opacity-0 group-hover:opacity-100 shrink-0 ml-1 px-1.5 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px] transition-opacity">解封</button>
          </div>
          <div v-if="!filteredBans.length" class="text-gray-400 text-[10px] py-2 text-center">无封禁 IP</div>
        </div>
        <div class="flex gap-1.5">
          <input v-model="banInput" @keydown.enter="banIP" placeholder="IP 地址" class="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-pink-400" />
          <button @click="banIP" class="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs hover:bg-red-600 cursor-pointer border-0 shrink-0">封禁</button>
        </div>
      </div>

      <!-- Whitelist -->
      <div class="flex-1 min-w-0 border-l border-gray-100 pl-4">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-xs font-semibold text-emerald-600">白名单 ({{ whitelist.length }})</span>
          <input v-model="wlSearch" placeholder="搜索..." class="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-[10px] outline-none focus:border-pink-400" />
        </div>
        <div class="text-xs space-y-0.5 mb-2 max-h-64 overflow-y-auto">
          <div v-for="ip in filteredWhitelist" :key="ip" class="flex items-center justify-between py-1 px-1.5 rounded hover:bg-emerald-50 group">
            <span class="flex-1 truncate text-emerald-700">{{ ip }}</span>
            <button @click="removeWL(ip)" class="opacity-0 group-hover:opacity-100 shrink-0 ml-1 px-1.5 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px] transition-opacity">移除</button>
          </div>
          <div v-if="!filteredWhitelist.length" class="text-gray-400 text-[10px] py-2 text-center">无白名单 IP</div>
        </div>
        <div class="flex gap-1.5">
          <input v-model="wlInput" @keydown.enter="addWL" placeholder="IP 地址" class="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-pink-400" />
          <button @click="addWL" class="px-3 py-1.5 bg-emerald-500 text-white rounded-lg text-xs hover:bg-emerald-600 cursor-pointer border-0 shrink-0">添加</button>
        </div>
      </div>
    </div>

    <button @click="loadBans" class="mt-3 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>

    <!-- IP Images Panel -->
    <Teleport to="body">
      <div v-if="ipImagesIp" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col" @click.stop>
          <div class="flex items-center justify-between p-4 border-b border-gray-100">
            <h3 class="text-sm font-bold text-gray-700">IP: {{ ipImagesIp }} ({{ ipImages.length }})</h3>
            <button @click="closeIpImages" class="text-gray-400 hover:text-gray-600 text-xl cursor-pointer border-0 bg-transparent">&times;</button>
          </div>
          <div class="flex items-center gap-2 px-4 py-2 border-b border-gray-50">
            <button @click="selectAllImages" class="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[10px] hover:bg-gray-200 cursor-pointer border-0">全选</button>
            <button v-if="ipImagesSelected.size" @click="deleteSelectedImages" class="px-2 py-1 bg-red-500 text-white rounded-lg text-[10px] hover:bg-red-600 cursor-pointer border-0">删除选中 ({{ ipImagesSelected.size }})</button>
            <span v-else class="text-[10px] text-gray-400">选择图片后批量删除</span>
          </div>
          <div class="flex-1 overflow-y-auto p-4">
            <div v-if="!ipImages.length" class="text-xs text-gray-400 text-center py-8">该 IP 下暂无图片</div>
            <div v-else class="grid grid-cols-4 sm:grid-cols-6 gap-2">
              <div v-for="img in ipImages" :key="img.path" class="relative group">
                <img :src="'/api/output/thumb?path=' + encodeURIComponent(img.path)"
                  class="lb-thumb w-full aspect-square object-cover rounded-lg cursor-pointer"
                  :class="{ 'ring-2 ring-pink-500': ipImagesSelected.has(img.path) }"
                  :data-path="img.path" :data-mtime="img.mtime"
                  @click="toggleImageSelect(img.path)" />
                <input type="checkbox"
                  :checked="ipImagesSelected.has(img.path)"
                  @change="toggleImageSelect(img.path)"
                  class="absolute top-1 left-1 accent-pink-500 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
