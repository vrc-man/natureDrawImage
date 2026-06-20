<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

async function load() {
  try {
    const d = await api('GET', '/api/admin/users')
    users.value = d.users || []
  } catch {}
}

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

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
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
          <tr v-for="u in users" :key="u.github_id" class="border-b border-gray-50 hover:bg-gray-50">
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
              <span v-if="u.role === 'admin'" class="text-[10px] text-gray-400">不可封禁</span>
              <button v-else-if="u.banned" @click="unbanUser(u.github_id)" class="px-2 py-0.5 bg-emerald-100 text-emerald-600 rounded hover:bg-emerald-200 cursor-pointer border-0 text-[10px]">解封</button>
              <button v-else @click="banUser(u.github_id)" class="px-2 py-0.5 bg-red-100 text-red-600 rounded hover:bg-red-200 cursor-pointer border-0 text-[10px]">封禁</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <button @click="load" class="mt-3 text-xs text-pink-500 hover:underline cursor-pointer border-0 bg-transparent">🔄 刷新</button>
  </div>
</template>
