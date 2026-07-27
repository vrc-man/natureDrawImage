<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { api, fmt } from './useAdminApi'

const lbOpen = ref(false)
const lbItems = ref<any[]>([]), lbIndex = ref(0), lbCur = ref<any>(null), lbGhUser = ref(''), lbBanGid = ref('')
const forkLoading = ref(false)
const shareOpen = ref(false)
const shareMaxDownloads = ref(1)
const shareExpiresHours = ref(24)
const shareLoading = ref(false)
const shareResult = ref('')
const imgLoading = ref(true)

function closeLb() { lbOpen.value = false; document.body.style.overflow = '' }

function collectLbItems() {
  const items: any[] = []
  document.querySelectorAll('.lb-thumb').forEach(el => {
    const h = el as HTMLElement
    const isAnchor = el.tagName === 'A'
    const href = isAnchor ? (el as HTMLAnchorElement).getAttribute('href') || '' : ''
    const delThumb = h.dataset.delThumb || ''
    const path = h.dataset.path || ''
    const url = delThumb || (isAnchor ? href : (path ? '/api/output/file?path=' + encodeURIComponent(path) : ''))
    items.push({
      url,
      _key: path || url,
      path, mtime: h.dataset.mtime || '', ip: h.dataset.ip || '',
      author: h.dataset.author || '',
      delThumb,
      isGenlog: !!h.dataset.genlog,
      isDeletion: !!delThumb,
    })
  })
  return items
}

function showLb() {
  const it = lbItems.value[lbIndex.value]
  if (!it) return; lbCur.value = it; imgLoading.value = true
  // 删除记录已有创建者信息，不调 /api/output/creator
  if (it.path && !it.delThumb) {
    api('GET', '/api/output/creator?path=' + encodeURIComponent(it.path))
      .then(d => { lbGhUser.value = d.github_id ? 'GitHub: ' + (d.github_login || d.github_id) + (d.github_email ? ' <' + d.github_email + '>' : '') : ''; lbBanGid.value = d.github_id || '' })
      .catch(() => { lbGhUser.value = ''; lbBanGid.value = '' })
  } else {
    lbGhUser.value = ''; lbBanGid.value = ''
  }
}

function openLb(path: string, url: string = '') {
  lbItems.value = collectLbItems()
  const key = path || url
  lbIndex.value = Math.max(0, lbItems.value.findIndex((it: any) => it._key === key))
  lbOpen.value = true; document.body.style.overflow = 'hidden'; showLb()
}

function lbPrev() { if (lbIndex.value > 0) { lbIndex.value--; showLb() } }
function lbNext() { if (lbIndex.value < lbItems.value.length - 1) { lbIndex.value++; showLb() } }

async function lbBanUser() {
  const gid = lbBanGid.value; if (!gid) return
  if (!confirm('确定封禁用户 ' + gid + ' ？')) return
  const i = prompt('即将封禁用户，请输入"确认封禁"以继续：')
  if (i !== '确认封禁') { alert('输入不匹配'); return }
  const r = prompt('封禁原因（可选）：')
  try { await api('POST', '/api/admin/users/ban', { github_id: gid, reason: r || '' }); alert('已封禁用户 ' + gid); lbBanGid.value = '' } catch (e: any) { alert('封禁失败: ' + e.message) }
}

async function doFork() {
  const path = lbCur.value?.path
  if (!path || forkLoading.value) return
  forkLoading.value = true
  try {
    const d = await api('POST', '/api/output/fork', { path })
    localStorage.setItem('forkedWorkflow', JSON.stringify(d.workflow || null))
    localStorage.setItem('forkedMeta', JSON.stringify(d))
    closeLb()
    location.href = '/'
  } catch (e: any) {
    forkLoading.value = false
    alert('Fork 失败: ' + e.message)
  }
}

function openShare() {
  const cur = lbCur.value
  if (!cur?.path) return
  shareMaxDownloads.value = 1
  shareExpiresHours.value = 24
  shareResult.value = ''
  shareOpen.value = true
}

async function doShare() {
  if (shareLoading.value) return
  const cur = lbCur.value
  if (!cur?.path) return
  shareLoading.value = true
  try {
    const d = await api('POST', '/api/output/share', { path: cur.path, max_downloads: shareMaxDownloads.value, expires_hours: shareExpiresHours.value })
    const url = location.origin + d.url
    await navigator.clipboard.writeText(url)
    const exp = d.expires_hours ? (d.expires_hours < 1 ? (d.expires_hours * 60) + ' 分钟' : d.expires_hours + ' 小时') : '无限（重启后失效）'
    shareResult.value = '✅ 链接已复制到剪贴板\n' + url + '\n有效期：' + exp + ' · 下载次数：' + (d.max_downloads ? d.max_downloads + ' 次' : '不限')
  } catch (e: any) {
    shareResult.value = '❌ 生成失败: ' + (e.message || '')
  } finally {
    shareLoading.value = false
  }
}

function handleKeydown(e: KeyboardEvent) { if (!lbOpen.value) return; if (e.key === 'Escape') closeLb(); if (e.key === 'ArrowLeft') lbPrev(); if (e.key === 'ArrowRight') lbNext() }
function handleThumbClick(e: Event) {
  const target = e.target as HTMLElement; const img = target.closest('.lb-thumb') as HTMLElement
  if (!img) return; if (target.closest('button, .btn-del-row, .btn-ban-row')) return
  e.preventDefault()
  const path = img.dataset.path || ''
  const url = (img.tagName === 'A' ? (img as HTMLAnchorElement).href : (img.dataset.delThumb || '')) || ''
  openLb(path, url)
}

document.addEventListener('keydown', handleKeydown)
document.addEventListener('click', handleThumbClick)
onUnmounted(() => { document.body.style.overflow = ''; document.removeEventListener('keydown', handleKeydown); document.removeEventListener('click', handleThumbClick) })
</script>

<template>
  <div v-if="lbOpen" class="fixed inset-0 z-[60] bg-black flex flex-col">
    <button class="absolute top-3 right-3 bg-black/50 hover:bg-black/80 text-white border-0 w-9 h-9 rounded-full flex items-center justify-center text-lg cursor-pointer z-10 transition-all" @click.stop="closeLb">✕</button>
    <button v-if="lbIndex > 0" class="absolute top-1/2 left-2 -translate-y-1/2 bg-black/45 hover:bg-black/75 text-white w-12 h-[72px] text-3xl cursor-pointer border-0 z-[5] backdrop-blur-[4px] transition-all" @click.stop="lbPrev">&lsaquo;</button>
    <button v-if="lbIndex < lbItems.length - 1" class="absolute top-1/2 right-2 -translate-y-1/2 bg-black/45 hover:bg-black/75 text-white w-12 h-[72px] text-3xl cursor-pointer border-0 z-[5] backdrop-blur-[4px] transition-all" @click.stop="lbNext">&rsaquo;</button>
    <div class="flex-1 flex items-center justify-center overflow-hidden p-2 min-h-0 relative">
      <div v-if="imgLoading" @click.stop class="absolute inset-0 flex flex-col items-center justify-center gap-2">
        <svg class="animate-spin h-8 w-8 text-pink-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <span class="text-white/60 text-xs">加载中请稍后...</span>
      </div>
      <img v-if="lbCur" :src="lbCur.url" class="max-w-full max-h-full w-auto h-auto object-contain select-auto transition-opacity duration-300" :class="imgLoading ? 'opacity-0' : 'opacity-100'" alt="" @load="imgLoading = false" @error="imgLoading = false" />
    </div>
    <div class="flex items-center gap-2 flex-wrap p-2 bg-black/50 text-white text-xs">
      <span class="text-gray-300 mr-auto break-all">{{ lbCur?.path?.split('/').pop() || '' }}</span>
      <span v-if="lbCur?.author" class="text-emerald-300">👤 {{ lbCur.author }}</span>
      <span v-else-if="lbGhUser" class="text-emerald-300">{{ lbGhUser }}</span>
      <span class="text-gray-400">{{ lbCur?.mtime ? fmt(parseInt(lbCur.mtime)) : '' }}</span>
      <span class="text-amber-300">{{ lbCur?.ip ? 'IP: ' + lbCur.ip : '' }}</span>
      <a v-if="lbCur?.path && !lbCur?.isGenlog && !lbCur?.isDeletion" :href="'/api/output/file?path=' + encodeURIComponent(lbCur.path) + '&full=1&download=1'" target="_blank" rel="noopener" class="text-white/60 hover:text-white no-underline text-base" title="下载原图">⬇️</a>
      <button v-if="lbCur?.path && !lbCur?.isDeletion" @click="doFork" class="text-pink-300 hover:text-pink-100 cursor-pointer border-0 bg-transparent text-base" title="Fork 工作流">🍴</button>
      <button v-if="lbCur?.path && !lbCur?.isGenlog && !lbCur?.isDeletion" @click="openShare" class="text-white/50 hover:text-white cursor-pointer border-0 bg-transparent text-base" title="分享">🔗</button>
      <button v-if="lbBanGid" class="text-white/50 hover:text-red-400 cursor-pointer border-0 bg-transparent text-base" @click="lbBanUser" title="封禁用户">🔨</button>
    </div>
    <div v-if="shareOpen" class="fixed inset-0 z-[70] bg-black/30 backdrop-blur-sm flex items-center justify-center p-4" @click.stop>
      <div class="bg-white rounded-2xl shadow-xl max-w-sm w-full p-5" @click.stop>
        <h3 class="text-base font-bold text-gray-700 mb-3">🔗 分享图片</h3>
        <div class="grid grid-cols-2 gap-2 mb-2">
          <label class="block text-sm text-gray-600">
            有效期（小时）
            <input v-model.number="shareExpiresHours" type="number" min="0" max="720" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
            <p class="text-xs text-gray-400 mt-1">0 = 不限（重启后失效）</p>
          </label>
          <label class="block text-sm text-gray-600">
            下载次数
            <input v-model.number="shareMaxDownloads" type="number" min="0" max="100" class="mt-1 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-pink-400 box-border" />
            <p class="text-xs text-gray-400 mt-1">0 = 不限次数</p>
          </label>
        </div>
        <div v-if="shareResult" class="mb-3 p-3 rounded-xl text-xs whitespace-pre-wrap break-all" :class="shareResult.startsWith('✅') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'">{{ shareResult }}</div>
        <div class="flex gap-2">
          <button @click="shareOpen=false" class="flex-1 py-2 bg-gray-100 rounded-xl hover:bg-gray-200 text-sm text-gray-600 transition-all cursor-pointer border-0">关闭</button>
          <button @click="doShare" :disabled="shareLoading" class="flex-1 py-2 rounded-xl text-sm font-semibold transition-all cursor-pointer border-0 flex items-center justify-center gap-1.5" :class="shareLoading ? 'bg-pink-300 text-white cursor-not-allowed' : 'bg-gradient-to-r from-pink-400 to-rose-400 text-white hover:from-pink-300 hover:to-rose-300'"><span v-if="shareLoading" class="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"></span>{{ shareLoading ? '生成中...' : '生成并复制链接' }}</button>
        </div>
      </div>
    </div>
    <div v-if="forkLoading" class="fixed inset-0 z-[80] bg-black/40 backdrop-blur-sm flex items-center justify-center">
      <div class="bg-white/95 rounded-2xl px-8 py-6 shadow-2xl flex items-center gap-3">
        <span class="animate-spin inline-block w-5 h-5 border-2 border-pink-500 border-t-transparent rounded-full"></span>
        <span class="text-gray-700 font-medium">🍴 Fork 信息加载中...</span>
      </div>
    </div>
  </div>
</template>