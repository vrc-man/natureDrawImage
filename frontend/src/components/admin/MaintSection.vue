<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const maintEnabled = ref(false)
const maintMessage = ref('')
const maintStatus = ref('')

const badgeText = computed(() => maintEnabled.value ? '维护中' : '正常运行')
const badgeClass = computed(() => maintEnabled.value
  ? 'bg-red-500 text-white'
  : 'bg-gray-200 text-gray-700')

async function load() {
  try {
    const d = await api('GET', '/api/admin/maintenance')
    const c = d.config || {}
    maintEnabled.value = !!c.enabled
    maintMessage.value = c.message || ''
    maintStatus.value = ''
  } catch (e: any) {
    maintStatus.value = '加载失败: ' + e.message
  }
}

async function save() {
  try {
    maintStatus.value = '保存中…'
    await api('POST', '/api/admin/maintenance', {
      enabled: maintEnabled.value,
      message: maintMessage.value,
    })
    maintStatus.value = '✓ 已保存'
    setTimeout(() => { if (maintStatus.value === '✓ 已保存') maintStatus.value = '' }, 2000)
  } catch (e: any) {
    maintStatus.value = '保存失败: ' + e.message
  }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <p class="text-xs text-gray-500 mb-3">
      开启维护模式后，非管理员用户将看到维护提示页面。
    </p>

    <label class="flex items-center gap-2 text-sm mb-3 cursor-pointer">
      <input type="checkbox" v-model="maintEnabled" class="accent-pink-500" />
      <span>启用维护模式</span>
    </label>

    <label class="flex flex-col gap-1 max-w-md mb-3">
      <span class="text-xs text-gray-600">维护消息</span>
      <textarea v-model="maintMessage" rows="4" class="border border-gray-200 rounded-lg px-2 py-1 text-xs font-mono outline-none focus:border-pink-400 resize-y" placeholder="维护提示内容"></textarea>
    </label>

    <div class="flex items-center gap-2">
      <button @click="save" class="px-3 py-1 bg-pink-500 text-white rounded-lg hover:bg-pink-600 text-sm cursor-pointer border-0">保存</button>
      <span class="text-xs text-gray-500">{{ maintStatus }}</span>
    </div>
  </div>
</template>
