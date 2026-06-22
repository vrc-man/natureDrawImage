<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api, fmt, onlineGithubIds } from './useAdminApi'

defineProps<{ visible: boolean }>()

interface User {
  github_id: string
  login: string
  email: string
  role: string
  created_at: number
  banned: boolean
  banned_reason?: string
}

const users = ref<User[]>([])
const total = ref(0)
const loading = ref(false)

const search = ref('')
const limit = ref(20)
const offset = ref(0)

// 角色 / 封禁：走后端，跨全库筛选 + 分页
const roleFilter = ref<'all' | 'admin' | 'user'>('all')
const banFilter = ref<'all' | 'banned' | 'active'>('all')
// 在线：实时内存状态，不持久化、无法用 SQL 查，只对当前页过滤
const onlineOnly = ref(false)

let searchTimer: ReturnType<typeof setTimeout> | null = null
let suppress = false

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      search: search.value.trim(),
      limit: String(limit.value),
      offset: String(offset.value),
    })
    if (roleFilter.value !== 'all') params.set('role', roleFilter.value)
    if (banFilter.value !== 'all') params.set('banned', banFilter.value === 'banned' ? '1' : '0')
    const d = await api('GET', '/api/admin/users?' + params.toString())
    users.value = d.users || []
    total.value = d.total || 0
  } catch {} finally {
    loading.value = false
  }
}

// 翻页 / 每页条数变化 → 直接拉取
watch([limit, offset], () => { if (!suppress) load() })
// 角色 / 封禁筛选变化 → 回到第一页（offset watch 负责实际请求）
watch([roleFilter, banFilter], () => {
  if (suppress) return
  if (offset.value !== 0) offset.value = 0
  else load()
})
watch(search, () => {
  if (suppress) return
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (offset.value !== 0) offset.value = 0
    else load()
  }, 300)
})

// 在线筛选仅作用于当前页（实时内存状态）
const viewUsers = computed(() => {
  if (!onlineOnly.value) return users.value
  return users.value.filter((u) => onlineGithubIds.value.has(u.github_id))
})

const page = computed(() => Math.floor(offset.value / limit.value) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / limit.value)))
const rangeStart = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const rangeEnd = computed(() => Math.min(offset.value + users.value.length, total.value))

function prevPage() {
  if (offset.value <= 0) return
  offset.value = Math.max(0, offset.value - limit.value)
}
function nextPage() {
  if (offset.value + limit.value >= total.value) return
  offset.value += limit.value
}
function resetFilters() {
  const changed =
    roleFilter.value !== 'all' ||
    banFilter.value !== 'all' ||
    search.value !== '' ||
    offset.value !== 0
  // 静默重置所有筛选，统一只发一次请求
  suppress = true
  roleFilter.value = 'all'
  banFilter.value = 'all'
  onlineOnly.value = false
  search.value = ''
  offset.value = 0
  suppress = false
  if (changed) load()
}

const hasFilter = computed(
  () => roleFilter.value !== 'all' || banFilter.value !== 'all' || search.value !== '' || onlineOnly.value
)

async function banUser(uid: string) {
  if (!confirm('确认封禁')) return
  if (prompt('确认封禁') !== '确认封禁') { alert('输入不匹配'); return }
  const reason = prompt('封禁原因（可选）') || ''
  try {
    await api('POST', '/api/admin/users/ban', { github_id: uid, reason })
    load()
  } catch (e: any) {
    alert('封禁失败: ' + e.message)
  }
}

async function unbanUser(uid: string) {
  if (!confirm('确认解封')) return
  if (prompt('确认解封') !== '确认解封') { alert('输入不匹配'); return }
  try {
    await api('POST', '/api/admin/users/unban', { github_id: uid })
    load()
  } catch (e: any) {
    alert('解封失败: ' + e.message)
  }
}

async function setRole(user: User, role: 'admin' | 'user') {
  const label = user.login || user.github_id
  let isSelf = false
  if (role === 'admin') {
    if (!confirm(`确认将 ${label} 设为管理员？`)) return
    if (prompt('确认设为管理员') !== '确认设为管理员') { alert('输入不匹配'); return }
  } else {
    try { isSelf = (await api('GET', '/api/admin/whoami')).github_id === user.github_id } catch {}
    const msg = isSelf
      ? `确认将自己降为普通用户？成功后你将失去后台权限，该账号绑定的访问密钥会被释放。`
      : `确认将管理员 ${label} 降为普通用户？该用户绑定的访问密钥会被释放。`
    if (!confirm(msg)) return
    if (prompt('确认降级管理员') !== '确认降级管理员') { alert('输入不匹配'); return }
  }
  try {
    await api('POST', '/api/admin/users/set_role', { github_id: user.github_id, role })
    if (isSelf) { location.href = '/'; return }
    load()
  } catch (e: any) {
    alert('角色修改失败: ' + e.message)
  }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <!-- 工具栏：搜索 + 筛选 -->
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <div class="relative">
        <input
          v-model="search"
          type="text"
          placeholder="搜索 登录名 / 邮箱 / GitHub ID"
          class="w-56 pl-7 pr-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-200"
        />
        <span class="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
      </div>

      <select v-model="roleFilter" class="text-xs border border-gray-200 rounded-lg py-1.5 px-2 bg-white">
        <option value="all">全部角色</option>
        <option value="admin">仅管理员</option>
        <option value="user">仅普通用户</option>
      </select>

      <select v-model="banFilter" class="text-xs border border-gray-200 rounded-lg py-1.5 px-2 bg-white">
        <option value="all">全部状态</option>
        <option value="banned">仅已封禁</option>
        <option value="active">仅正常</option>
      </select>

      <label class="flex items-center gap-1 text-xs text-gray-600 cursor-pointer select-none">
        <input type="checkbox" v-model="onlineOnly" class="accent-pink-500" />
        仅在线
      </label>

      <select v-model.number="limit" class="text-xs border border-gray-200 rounded-lg py-1.5 px-2 bg-white">
        <option :value="20">20 / 页</option>
        <option :value="50">50 / 页</option>
        <option :value="100">100 / 页</option>
        <option :value="200">200 / 页</option>
      </select>

      <button
        v-if="hasFilter"
        @click="resetFilters"
        class="text-xs text-gray-500 hover:text-gray-700 cursor-pointer border-0 bg-transparent"
      >清除筛选</button>

      <span class="ml-auto text-xs text-gray-400">
        共 {{ total }} 人 · 本页 {{ rangeStart }}-{{ rangeEnd }}
        <template v-if="onlineOnly"> · 在线 {{ viewUsers.length }}</template>
      </span>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="text-left text-gray-500 border-b border-gray-100">
            <th class="py-1.5 pr-2">状态</th>
            <th class="py-1.5 pr-2">GitHub ID</th>
            <th class="py-1.5 pr-2">登录名</th>
            <th class="py-1.5 pr-2">邮箱</th>
            <th class="py-1.5 pr-2">角色</th>
            <th class="py-1.5 pr-2">注册时间</th>
            <th class="py-1.5 pr-2">封禁原因</th>
            <th class="py-1.5">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in viewUsers" :key="u.github_id" class="border-b border-gray-50 hover:bg-gray-50">
            <td class="py-1.5 pr-2">
              <span class="w-2 h-2 rounded-full inline-block" :class="onlineGithubIds.has(u.github_id) ? 'bg-green-500' : 'bg-gray-300'"></span>
            </td>
            <td class="py-1.5 pr-2 font-mono">{{ u.github_id }}</td>
            <td class="py-1.5 pr-2">{{ u.login }}</td>
            <td class="py-1.5 pr-2">{{ u.email || '-' }}</td>
            <td class="py-1.5 pr-2">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'">{{ u.role }}</span>
            </td>
            <td class="py-1.5 pr-2 text-gray-500">{{ fmt(u.created_at) }}</td>
            <td class="py-1.5 pr-2 text-red-500 max-w-[120px] truncate">{{ u.banned_reason || '-' }}</td>
            <td class="py-1.5">
              <div class="flex flex-wrap gap-1">
                <button v-if="u.role === 'admin'" @click="setRole(u, 'user')" class="px-2 py-0.5 bg-purple-100 text-purple-600 rounded hover:bg-purple-200 cursor-pointer border-0 text-[10px]">降为普通用户</button>
                <button v-else @click="setRole(u, 'admin')" class="px-2 py-0.5 bg-purple-100 text-purple-600 rounded hover:bg-purple-200 cursor-pointer border-0 text-[10px]">设为管理员</button>
                <span v-if="u.role === 'admin'" class="text-[10px] text-gray-400 self-center">不可封禁</span>
                <button v-else-if="u.banned" @click="unbanUser(u.github_id)" class="px-2 py-0.5 bg-emerald-100 text-emerald-600 rounded hover:bg-emerald-200 cursor-pointer border-0 text-[10px]">解封</button>
                <button v-else @click="banUser(u.github_id)" class="px-2 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px]">封禁</button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && viewUsers.length === 0">
            <td colspan="8" class="py-6 text-center text-gray-400">
              {{ onlineOnly && users.length > 0 ? '当前页没有在线用户' : (hasFilter ? '没有符合筛选条件的用户' : '暂无用户') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分页 -->
    <div class="flex items-center gap-2 mt-3">
      <button @click="load" class="text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
      <span v-if="loading" class="text-xs text-gray-400">加载中…</span>
      <div class="ml-auto flex items-center gap-2">
        <button
          @click="prevPage"
          :disabled="offset <= 0"
          class="px-2 py-1 text-xs rounded border border-gray-200 bg-white disabled:opacity-40 disabled:cursor-not-allowed enabled:hover:bg-gray-50 enabled:cursor-pointer"
        >上一页</button>
        <span class="text-xs text-gray-500">{{ page }} / {{ pageCount }}</span>
        <button
          @click="nextPage"
          :disabled="offset + limit >= total"
          class="px-2 py-1 text-xs rounded border border-gray-200 bg-white disabled:opacity-40 disabled:cursor-not-allowed enabled:hover:bg-gray-50 enabled:cursor-pointer"
        >下一页</button>
      </div>
    </div>
  </div>
</template>
