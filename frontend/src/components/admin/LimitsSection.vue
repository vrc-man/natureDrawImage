<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from './useAdminApi'

defineProps<{ visible: boolean }>()

interface LimitField {
  key: string
  label: string
  desc: string
}

const limitFields: LimitField[] = [
  { key: 'gen_cooldown_sec', label: '生图冷却', desc: '每次生图后的冷却时间（秒）' },
  { key: 'image_rate_window_sec', label: '图片限流窗口', desc: '图片生成限流的时间窗口（秒）' },
  { key: 'image_rate_max', label: '图片限流上限', desc: '窗口内最大图片数' },
  { key: 'report_window_sec', label: '举报窗口', desc: '举报限流的时间窗口（秒）' },
  { key: 'report_window_max', label: '举报上限', desc: '窗口内最大举报数' },
  { key: 'report_pending_max', label: '待处理举报上限', desc: '最多待处理举报数' },
  { key: 'gpu_poll_interval_ms', label: 'GPU轮询间隔', desc: 'GPU 状态轮询间隔（毫秒）' },
  { key: 'gpu_cache_ttl_ms', label: 'GPU缓存', desc: 'GPU 缓存有效期（毫秒）' },
  { key: 'gc_interval_hours', label: 'GC间隔', desc: '自动 GC 执行间隔（小时）' },
]

function defaultFor(key: string): number {
  if (key.includes('max') || key.includes('pending')) return 1
  if (key.includes('poll') || key.includes('cache')) return 5000
  return 0
}

const limits = ref<Record<string, any>>({})
const status = ref('')

async function load() {
  try {
    const d = await api('GET', '/api/admin/limits')
    limits.value = d.limits || d
  } catch (e: any) {
    status.value = '加载失败: ' + e.message
  }
}

async function save() {
  status.value = '保存中…'
  try {
    const payload: Record<string, any> = {}
    for (const f of limitFields) {
      payload[f.key] = parseInt(limits.value[f.key], 10) || defaultFor(f.key)
    }
    payload.featured_tip = limits.value.featured_tip || ''
    await api('POST', '/api/admin/limits', payload)
    status.value = '✓ 已保存'
    setTimeout(() => { if (status.value === '✓ 已保存') status.value = '' }, 2000)
  } catch (e: any) {
    status.value = '保存失败: ' + e.message
  }
}

async function runGc(backup: boolean) {
  try {
    await api('POST', '/api/admin/gc', { backup })
    let retries = 0
    const poll = setInterval(async () => {
      retries++
      if (retries > 60) {
        clearInterval(poll)
        alert('GC 超时，请检查后端状态')
        return
      }
      try {
        const d = await api('GET', '/api/admin/gc/status')
        if (d.status === 'done') {
          clearInterval(poll)
          alert('GC 完成，清理了: ' + JSON.stringify(d.cleaned || {}))
        } else if (d.status === 'error') {
          clearInterval(poll)
          alert('GC 出错: ' + (d.error || '未知错误'))
        }
      } catch { clearInterval(poll) }
    }, 1000)
  } catch (e: any) {
    alert('GC 启动失败: ' + e.message)
  }
}

async function gcRunWithConfirm() {
  if (!confirm('确认执行GC？将先备份再清理。此操作不可恢复。')) return
  if (prompt('确认清理') !== '确认清理') { alert('输入不匹配'); return }
  await runGc(true)
}

async function forceRestart() {
  if (!confirm('确定强制重启？所有任务中断。')) return
  if (prompt('输入"确认重启服务"') !== '确认重启服务') { alert('输入不匹配'); return }
  try {
    await api('POST', '/api/admin/force-restart')
  } catch (e: any) { alert('重启失败: ' + e.message) }
}

async function gracefulRestart() {
  if (!confirm('优雅重启将等待当前任务完成后重启。确定？')) return
  if (prompt('输入"确认重启服务"') !== '确认重启服务') { alert('输入不匹配'); return }
  try {
    await api('POST', '/api/admin/graceful-restart')
  } catch (e: any) { alert('重启失败: ' + e.message) }
}

onMounted(load)
</script>

<template>
  <div v-if="visible" class="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-3">
    <h2 class="text-sm font-bold text-gray-700 mb-3">⏱️ 限流配置</h2>

    <div class="grid grid-cols-3 gap-3 text-xs mb-4">
      <div v-for="f in limitFields" :key="f.key">
        <label class="text-gray-500 block mb-0.5">{{ f.label }}</label>
        <input v-model="limits[f.key]" type="number" class="w-full border border-gray-200 rounded-lg px-2 py-1 outline-none focus:border-pink-400 box-border" />
        <div class="text-[10px] text-gray-400 mt-0.5">{{ f.desc }}</div>
      </div>
    </div>

    <div class="mb-4">
      <label class="text-xs text-gray-500 block mb-0.5">精选提示</label>
      <input v-model="limits.featured_tip" placeholder="精选区域显示的自定义提示文字" class="w-full border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none focus:border-pink-400 box-border" />
    </div>

    <div class="flex items-center gap-2 mb-3">
      <button @click="save" class="px-4 py-1.5 bg-pink-500 text-white rounded-lg text-xs hover:bg-pink-600 cursor-pointer border-0">保存</button>
      <span class="text-xs" :class="status.startsWith('✓') ? 'text-green-500' : status ? 'text-red-400' : 'text-gray-400'">{{ status }}</span>
    </div>

    <div class="flex items-center gap-2 pt-3 border-t border-gray-100">
      <button @click="gcRunWithConfirm" class="px-3 py-1 bg-amber-500 text-white rounded-lg text-xs hover:bg-amber-600 cursor-pointer border-0">🧹 立即GC</button>
      <button @click="forceRestart" class="px-3 py-1 bg-red-500 text-white rounded-lg text-xs hover:bg-red-600 cursor-pointer border-0">强制重启</button>
      <button @click="gracefulRestart" class="px-3 py-1 bg-orange-500 text-white rounded-lg text-xs hover:bg-orange-600 cursor-pointer border-0">优雅重启</button>
    </div>
  </div>
</template>
