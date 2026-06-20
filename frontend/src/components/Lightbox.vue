<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useLightbox } from '@/composables/useLightbox'
import { api } from '@/api/client'

const { lbOpen, lbState, current, close, prev, next } = useLightbox()
const showReport = ref(false)
const reportReason = ref('')
const reportStatus = ref('')
const lbCreator = ref('')
const forkLoading = ref(false)

function fetchCreator() {
  const c = current()
  if (c?.creator) { lbCreator.value = c.creator; return }
  if (c?.path) {
    lbCreator.value = ''
    api('GET', '/api/output/creator?path=' + encodeURIComponent(c.path))
      .then((d: any) => { if (d.github_id) lbCreator.value = d.github_login || d.github_id })
      .catch(() => { lbCreator.value = '' })
  } else {
    lbCreator.value = ''
  }
}
watch(() => lbState.index, fetchCreator)
watch(lbOpen, (v) => { if (v) setTimeout(fetchCreator, 50) })

function onKeyDown(e: KeyboardEvent) {
  if (!lbOpen.value) return
  if (e.key === 'Escape') { if (showReport.value) { showReport.value = false } else { close() } }
  else if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}

async function doFork() {
  if (!current() || forkLoading.value) return
  forkLoading.value = true
  try {
    const d = await api<any>('POST', '/api/output/fork', { path: current()!.path || current()!.filename || '' })
    localStorage.setItem('forkedWorkflow', JSON.stringify(d.workflow || null))
    localStorage.setItem('forkedMeta', JSON.stringify(d))
    close()
    location.reload()
  } catch (e: any) {
    forkLoading.value = false
    alert('Fork 失败: ' + e.message)
  }
}

async function doCopyLink() {
  if (!current()) return
  try {
    const d = await api<any>('POST', '/api/output/signed-url', { path: current()!.path || current()!.filename || '' })
    await navigator.clipboard.writeText(location.origin + (d.url || current()!.url))
    alert('链接已复制')
  } catch { await navigator.clipboard.writeText(location.origin + '/api/output/file?path=' + encodeURIComponent(current()!.path || current()!.filename || '') + '&full=1'); alert('已复制（无签名）') }
}

async function doReport() {
  if (!current() || !reportReason.value.trim()) return
  reportStatus.value = '提交中...'
  try {
    await api('POST', '/api/report', { image_path: current()!.path || current()!.filename || '', reason: reportReason.value.trim() })
    reportStatus.value = '✅ 举报已提交'
    setTimeout(() => { showReport.value = false; reportStatus.value = ''; reportReason.value = '' }, 1500)
  } catch (e: any) { reportStatus.value = '提交失败: ' + e.message }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <Teleport to="body">
    <div v-if="lbOpen" id="lb-root" class="open" @click.self="close">
      <button id="lb-close" @click="close" class="absolute top-2 right-3 bg-transparent text-white border-0 text-2xl cursor-pointer z-10">×</button>
      <button v-if="lbState.items.length > 1" id="lb-prev" @click="prev" class="lb-nav left-2">‹</button>
      <button v-if="lbState.items.length > 1" id="lb-next" @click="next" class="lb-nav right-2">›</button>
      <div id="lb-img-wrap" class="flex-1 flex items-center justify-center overflow-hidden p-2 min-h-0" @click.self="close">
        <img v-if="current()" :src="current()!.url" id="lb-img" class="max-w-full max-h-full w-auto h-auto object-contain select-auto" alt="" />
      </div>
      <div id="lb-bar" class="text-white px-4 py-3 flex items-center gap-3 flex-wrap text-sm" style="background:rgba(15,23,42,.85);backdrop-filter:blur(12px)">
        <span id="lb-title" class="text-sm mr-auto break-all">{{ current()?.title || '' }}</span>
        <span v-if="current()?.time" class="text-xs text-white/40">{{ current()!.time }}</span>
        <span v-if="lbCreator || current()?.creator" class="text-xs text-amber-300">{{ lbCreator || current()?.creator }}</span>
        <a v-if="current()?.filename" :href="'/api/output/file?path=' + encodeURIComponent(current()!.path || current()!.filename || '') + '&full=1'" target="_blank" class="text-white/60 hover:text-white no-underline text-base" title="下载原图">⬇️</a>
        <button @click="doFork" class="text-pink-300 hover:text-pink-100 cursor-pointer border-0 bg-transparent text-base" title="Fork 工作流">🍴</button>
        <button @click="doCopyLink" class="text-white/50 hover:text-white cursor-pointer border-0 bg-transparent text-base" title="复制链接">🔗</button>
        <button @click="showReport=true" class="text-white/50 hover:text-red-400 cursor-pointer border-0 bg-transparent text-base" title="举报">📮</button>
      </div>
    </div>

    <!-- Report Modal -->
    <div v-if="showReport" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.self="showReport=false">
      <div class="bg-white rounded-2xl shadow-xl max-w-sm w-full p-5">
        <h3 class="text-base font-bold text-gray-700 mb-3">📮 举报图片</h3>
        <textarea v-model="reportReason" placeholder="请描述举报原因..." rows="3" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 resize-y box-border"></textarea>
        <div class="flex gap-2 mt-3">
          <button @click="showReport=false" class="flex-1 py-2 bg-gray-100 rounded-xl hover:bg-gray-200 text-sm text-gray-600 transition-all cursor-pointer border-0">取消</button>
          <button @click="doReport" class="flex-1 py-2 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-sm font-semibold transition-all cursor-pointer border-0">提交举报</button>
        </div>
        <span v-if="reportStatus" class="text-xs mt-2 block text-center" :class="reportStatus.startsWith('✅')?'text-green-500':'text-red-400'">{{ reportStatus }}</span>
      </div>
    </div>
    <!-- Fork loading overlay -->
    <div v-if="forkLoading" class="fixed inset-0 z-[80] bg-black/40 backdrop-blur-sm flex items-center justify-center">
      <div class="bg-white/95 rounded-2xl px-8 py-6 shadow-2xl flex items-center gap-3">
        <span class="animate-spin inline-block w-5 h-5 border-2 border-pink-500 border-t-transparent rounded-full"></span>
        <span class="text-gray-700 font-medium">🍴 Fork 信息加载中...</span>
      </div>
    </div>
  </Teleport>
</template>
