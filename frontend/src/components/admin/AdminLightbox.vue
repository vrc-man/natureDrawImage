<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { api, fmt } from './useAdminApi'

const lbOpen = ref(false)
const lbItems = ref<any[]>([]), lbIndex = ref(0), lbCur = ref<any>(null), lbGhUser = ref(''), lbBanGid = ref('')

function closeLb() { lbOpen.value = false; document.body.style.overflow = '' }

function collectLbItems() {
  const items: any[] = []
  document.querySelectorAll('.lb-thumb').forEach(el => {
    const h = el as HTMLElement
    const isAnchor = el.tagName === 'A'
    const href = isAnchor ? (el as HTMLAnchorElement).getAttribute('href') || '' : ''
    items.push({
      url: h.dataset.delThumb || href || '/api/output/file?path=' + encodeURIComponent(h.dataset.path || '') + '&full=1',
      path: h.dataset.path || '', mtime: h.dataset.mtime || '', ip: h.dataset.ip || '',
      isGenlog: !!h.dataset.genlog, delThumb: h.dataset.delThumb || '',
    })
  })
  return items
}

function showLb() {
  const it = lbItems.value[lbIndex.value]
  if (!it) return; lbCur.value = it
  if (it.path) {
    api('GET', '/api/output/creator?path=' + encodeURIComponent(it.path))
      .then(d => { lbGhUser.value = d.github_id ? 'GitHub: ' + (d.github_login || d.github_id) + (d.github_email ? ' <' + d.github_email + '>' : '') : ''; lbBanGid.value = d.github_id || '' })
      .catch(() => { lbGhUser.value = ''; lbBanGid.value = '' })
  }
}

function openLb(path: string) {
  lbItems.value = collectLbItems()
  lbIndex.value = Math.max(0, lbItems.value.findIndex((it: any) => it.path === path))
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

function handleKeydown(e: KeyboardEvent) { if (!lbOpen.value) return; if (e.key === 'Escape') closeLb(); if (e.key === 'ArrowLeft') lbPrev(); if (e.key === 'ArrowRight') lbNext() }
function handleThumbClick(e: Event) {
  const target = e.target as HTMLElement; const img = target.closest('.lb-thumb') as HTMLElement
  if (!img) return; if (target.closest('button, .btn-del-row, .btn-ban-row')) return
  e.preventDefault(); openLb(img.dataset.path || '')
}

document.addEventListener('keydown', handleKeydown)
document.addEventListener('click', handleThumbClick)
onUnmounted(() => { document.body.style.overflow = ''; document.removeEventListener('keydown', handleKeydown); document.removeEventListener('click', handleThumbClick) })
</script>

<template>
  <div v-if="lbOpen" class="fixed inset-0 z-[60] bg-black flex flex-col" @click.self="closeLb">
    <button class="absolute top-2 right-3 bg-transparent text-white text-3xl z-10 cursor-pointer border-0" @click="closeLb">&times;</button>
    <button v-if="lbIndex > 0" class="absolute top-1/2 left-2 -translate-y-1/2 bg-black/40 text-white w-11 h-16 text-3xl cursor-pointer border-0 hover:bg-black/70 z-10" @click="lbPrev">&lsaquo;</button>
    <button v-if="lbIndex < lbItems.length - 1" class="absolute top-1/2 right-2 -translate-y-1/2 bg-black/40 text-white w-11 h-16 text-3xl cursor-pointer border-0 hover:bg-black/70 z-10" @click="lbNext">&rsaquo;</button>
    <div class="flex-1 flex items-center justify-center overflow-hidden p-2 min-h-0">
      <img v-if="lbCur" :src="lbCur.url" class="max-w-full max-h-full w-auto h-auto object-contain select-auto" alt="" />
    </div>
    <div class="flex items-center gap-2 flex-wrap p-2 bg-black/50 text-white text-xs">
      <span class="text-gray-300 mr-auto break-all">{{ lbCur?.path?.split('/').pop() || '' }}</span>
      <span class="text-gray-400">{{ lbCur?.mtime ? fmt(parseInt(lbCur.mtime)) : '' }}</span>
      <span class="text-amber-300">{{ lbCur?.ip ? 'IP: ' + lbCur.ip : '' }}</span>
      <span v-if="lbGhUser" class="text-emerald-300">{{ lbGhUser }}</span>
      <button v-if="lbBanGid" class="text-xs px-2 py-0.5 bg-red-600 text-white rounded hover:bg-red-700 cursor-pointer border-0" @click="lbBanUser">&#x1F6AB; 封禁用户</button>
      <a v-if="lbCur && !lbCur.isGenlog" :href="lbCur.url" target="_blank" rel="noopener" download class="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">&#x2B07; 下载原图</a>
    </div>
  </div>
</template>