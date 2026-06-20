<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

const cheadEnabled = ref(false)
const cheadHtml = ref('')
const cheadStatus = ref('')

const badgeText = computed(() => cheadEnabled.value ? '已启用' : '已禁用')
const badgeClass = computed(() => cheadEnabled.value
  ? 'bg-green-500 text-white'
  : 'bg-gray-200 text-gray-700')

async function load() {
  try {
    const d = await api('GET', '/api/admin/custom_head')
    const c = d.config || {}
    cheadEnabled.value = !!c.enabled
    cheadHtml.value = c.html || ''
    cheadStatus.value = ''
  } catch (e: any) {
    cheadStatus.value = '加载失败: ' + e.message
  }
}

async function save() {
  try {
    cheadStatus.value = '保存中…'
    await api('POST', '/api/admin/custom_head', {
      enabled: cheadEnabled.value,
      html: cheadHtml.value,
    })
    cheadStatus.value = '✓ 已保存'
    setTimeout(() => { if (cheadStatus.value === '✓ 已保存') cheadStatus.value = '' }, 2000)
  } catch (e: any) {
    cheadStatus.value = '保存失败: ' + e.message
  }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <p class="text-xs text-gray-500 mb-3">
      自定义 HTML 标签注入到页面 &lt;head&gt; 中，可用于统计代码、验证信息等。注意不要包含 &lt;body&gt; 相关标签。
    </p>

    <label class="flex items-center gap-2 text-sm mb-3 cursor-pointer">
      <input type="checkbox" v-model="cheadEnabled" class="accent-pink-500" />
      <span>启用注入</span>
    </label>

    <label class="flex flex-col gap-1 max-w-lg mb-3">
      <span class="text-xs text-gray-600">HTML 内容</span>
      <textarea v-model="cheadHtml" rows="5" class="border border-gray-200 rounded-lg px-2 py-1 text-xs font-mono outline-none focus:border-pink-400 resize-y" placeholder="&lt;script&gt;...&lt;/script&gt;"></textarea>
    </label>

    <div class="flex items-center gap-2">
      <button @click="save" class="px-3 py-1 bg-pink-500 text-white rounded-lg hover:bg-pink-600 text-sm cursor-pointer border-0">保存</button>
      <span class="text-xs text-gray-500">{{ cheadStatus }}</span>
    </div>
  </div>
</template>
