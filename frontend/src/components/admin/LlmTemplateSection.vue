<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, fmtShort } from './useAdminApi'

interface LlmTemplate {
  id: number
  name: string
  description: string
  system_generate: string
  system_rewrite: string
  enabled: boolean
  sort_order: number
  created_at: number
  updated_at: number
}

defineProps<{ visible: boolean }>()

const items = ref<LlmTemplate[]>([])
const loading = ref(false)
const status = ref('')
const showModal = ref(false)
const editing = ref<LlmTemplate | null>(null)
const form = ref<Partial<LlmTemplate>>({})

function emptyForm(): Partial<LlmTemplate> {
  return {
    name: '',
    description: '',
    system_generate: '',
    system_rewrite: '',
    enabled: true,
    sort_order: 0,
  }
}

async function load() {
  loading.value = true
  try {
    const d = await api('GET', '/api/admin/features/llm-templates')
    items.value = d.templates || []
  } catch (e: any) {
    status.value = '加载失败: ' + e.message
  } finally {
    loading.value = false
  }
}

function openNew() {
  editing.value = null
  form.value = emptyForm()
  showModal.value = true
}

function openEdit(item: LlmTemplate) {
  editing.value = item
  form.value = { ...item }
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editing.value = null
  form.value = {}
}

async function save() {
  if (!String(form.value.name || '').trim()) { alert('请输入模板名称'); return }
  if (!String(form.value.system_generate || '').trim()) { alert('请输入不改写规则'); return }
  try {
    const body = {
      name: form.value.name || '',
      description: form.value.description || '',
      system_generate: form.value.system_generate || '',
      system_rewrite: form.value.system_rewrite || '',
      enabled: form.value.enabled !== false,
      sort_order: Number(form.value.sort_order || 0),
    }
    if (editing.value) {
      await api('PUT', `/api/admin/features/llm-templates/${editing.value.id}`, body)
      status.value = '✓ 已保存'
    } else {
      await api('POST', '/api/admin/features/llm-templates', body)
      status.value = '✓ 已新增'
    }
    closeModal()
    await load()
    setTimeout(() => { if (status.value.startsWith('✓')) status.value = '' }, 2000)
  } catch (e: any) {
    alert('保存失败: ' + e.message)
  }
}

async function toggleEnabled(item: LlmTemplate) {
  try {
    await api('PUT', `/api/admin/features/llm-templates/${item.id}`, { enabled: !item.enabled })
    await load()
  } catch (e: any) { alert('切换失败: ' + e.message) }
}

async function del(item: LlmTemplate) {
  if (!confirm(`确定删除模板「${item.name}」？`)) return
  if (prompt(`确认删除模板「${item.name}」，请输入"确认删除"`) !== '确认删除') { alert('输入不匹配'); return }
  try {
    await api('DELETE', `/api/admin/features/llm-templates/${item.id}`)
    await load()
  } catch (e: any) { alert('删除失败: ' + e.message) }
}

onMounted(load)
</script>

<template>
  <div v-if="visible">
    <div class="flex items-center justify-between mb-4">
      <div>
        <div class="text-sm font-semibold text-gray-700">🧩 LLM 提示词模板</div>
        <p class="text-xs text-gray-500 mt-1">JSON 外挂存储，只影响 LLM 生成最终正负提示词，不改变生图日志和数据库表。</p>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-gray-500">{{ status }}</span>
        <button @click="openNew" class="px-3 py-1 bg-emerald-500 text-white rounded hover:bg-emerald-600 text-sm cursor-pointer border-0">+ 新建模板</button>
        <button @click="load" class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 cursor-pointer border-0">刷新</button>
      </div>
    </div>

    <div v-if="!items.length && !loading" class="text-center text-gray-400 text-sm py-8 border-2 border-dashed border-gray-200 rounded-xl">
      暂无模板。用户端会继续使用内置 tags / natural 规则。
    </div>

    <div class="space-y-3">
      <div v-for="item in items" :key="item.id" class="border rounded-xl p-4 bg-white hover:shadow-sm transition-shadow" :class="item.enabled ? 'border-gray-200' : 'border-gray-100 opacity-70'">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-semibold text-gray-800 truncate">{{ item.name }}</span>
              <span class="text-[10px] px-2 py-0.5 rounded-full" :class="item.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'">{{ item.enabled ? '启用' : '禁用' }}</span>
              <span class="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">排序 {{ item.sort_order || 0 }}</span>
            </div>
            <p v-if="item.description" class="text-xs text-gray-500 mt-1 whitespace-pre-wrap">{{ item.description }}</p>
            <div class="text-[11px] text-gray-400 mt-2">
              更新：{{ fmtShort(item.updated_at) || '-' }} · 创建：{{ fmtShort(item.created_at) || '-' }}
            </div>
          </div>
          <div class="flex items-center gap-1 flex-shrink-0">
            <button @click="toggleEnabled(item)" class="text-xs px-2 py-1 rounded border-0 cursor-pointer" :class="item.enabled ? 'bg-gray-200 text-gray-600 hover:bg-gray-300' : 'bg-green-500 text-white hover:bg-green-600'">{{ item.enabled ? '禁用' : '启用' }}</button>
            <button @click="openEdit(item)" class="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 border-0 cursor-pointer">编辑</button>
            <button @click="del(item)" class="text-xs px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 border-0 cursor-pointer">删除</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showModal" class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-800">{{ editing ? '编辑模板' : '新建模板' }}</h3>
          <button @click="closeModal" class="text-gray-400 hover:text-gray-600 bg-transparent border-0 text-xl cursor-pointer">×</button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <label class="text-sm text-gray-600">
            模板名称
            <input v-model="form.name" class="mt-1 w-full border rounded px-3 py-2 outline-none focus:border-pink-400" placeholder="例如 Anima 动漫标签" />
          </label>
          <label class="text-sm text-gray-600">
            排序
            <input v-model.number="form.sort_order" type="number" class="mt-1 w-full border rounded px-3 py-2 outline-none focus:border-pink-400" />
          </label>
        </div>

        <label class="block text-sm text-gray-600 mb-3">
          说明
          <input v-model="form.description" class="mt-1 w-full border rounded px-3 py-2 outline-none focus:border-pink-400" placeholder="用户端下拉可见的简短说明" />
        </label>

        <label class="flex items-center gap-2 text-sm text-gray-600 mb-3 cursor-pointer select-none">
          <input v-model="form.enabled" type="checkbox" class="w-4 h-4 accent-pink-500" /> 启用（用户端下拉显示）
        </label>

        <label class="block text-sm text-gray-600 mb-3">
          不改写规则 system_generate <span class="text-red-500">*</span>
          <textarea v-model="form.system_generate" rows="8" class="mt-1 w-full border rounded px-3 py-2 font-mono text-xs outline-none focus:border-pink-400 resize-y" placeholder="写给 LLM 的模板规则。系统会自动追加 NSFW 规则和 POSITIVE/NEGATIVE 输出格式。"></textarea>
        </label>

        <label class="block text-sm text-gray-600 mb-4">
          改写规则 system_rewrite <span class="text-gray-400">（可空，空则复用不改写规则）</span>
          <textarea v-model="form.system_rewrite" rows="8" class="mt-1 w-full border rounded px-3 py-2 font-mono text-xs outline-none focus:border-pink-400 resize-y" placeholder="用户勾选“改写”时使用。留空则复用 system_generate。"></textarea>
        </label>

        <div class="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-700 mb-4">
          注意：模板只控制 LLM 如何生成最终 positive / negative；生图日志、fork、GC、路径记录和数据库表保持原样。
        </div>

        <div class="flex justify-end gap-2">
          <button @click="closeModal" class="px-4 py-2 bg-gray-200 rounded hover:bg-gray-300 border-0 cursor-pointer">取消</button>
          <button @click="save" class="px-4 py-2 bg-pink-500 text-white rounded hover:bg-pink-600 border-0 cursor-pointer">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>
