<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const annTitle = ref('')
const annContent = ref('')
const annEnabled = ref('off')
const annStatus = ref('')

async function load() {
  try {
    const d = await api('GET', '/api/admin/announcement')
    const a = d.announcement || {}
    annTitle.value = a.title || ''
    annContent.value = a.content || ''
    annEnabled.value = a.enabled ? 'on' : 'off'
    annStatus.value = ''
  } catch (e: any) {
    annStatus.value = '加载失败: ' + e.message
  }
}

async function save() {
  try {
    annStatus.value = '保存中…'
    await api('POST', '/api/admin/announcement', {
      enabled: annEnabled.value === 'on',
      title: annTitle.value,
      content: annContent.value,
    })
    annStatus.value = '✓ 已保存'
    setTimeout(() => { if (annStatus.value === '✓ 已保存') annStatus.value = '' }, 2000)
  } catch (e: any) {
    annStatus.value = '保存失败: ' + e.message
  }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <div class="text-sm mb-3">
      <label class="flex flex-col gap-1 max-w-md mb-3">
        <span>标题</span>
        <input v-model="annTitle" type="text" maxlength="100" class="border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400" placeholder="公告标题" />
      </label>
      <label class="flex flex-col gap-1 max-w-md">
        <span>内容</span>
        <textarea v-model="annContent" rows="3" class="border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400 resize-y" placeholder="公告内容"></textarea>
      </label>
    </div>

    <div class="flex items-center gap-3 text-sm mb-3">
      <span>启用：</span>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="radio" v-model="annEnabled" value="on" class="accent-pink-500" /> 开
      </label>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="radio" v-model="annEnabled" value="off" class="accent-pink-500" /> 关
      </label>
    </div>

    <div class="flex items-center gap-2">
      <button @click="save" class="px-3 py-1 bg-pink-500 text-white rounded-lg hover:bg-pink-600 text-sm cursor-pointer border-0">保存</button>
      <span class="text-xs text-gray-500">{{ annStatus }}</span>
    </div>
  </div>
</template>
