import { ref } from 'vue'

export async function api(method: string, url: string, body?: any) {
  const opt: RequestInit = { method, headers: {} }
  if (body) { opt.headers = { 'Content-Type': 'application/json' }; opt.body = JSON.stringify(body) }
  const r = await fetch(url, opt)
  const d = await r.json().catch(() => ({}))
  if (r.status === 401) { alert('登录已过期'); location.href = '/'; throw new Error('x') }
  if (r.status === 403) { alert(d.detail || d.error || '权限不足'); throw new Error('x') }
  if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status))
  return d
}

export function fmt(ts: number) { return ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '' }
export function fmtShort(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
export function relTime(ts: number) {
  if (!ts) return '从未'
  const n = Date.now(), t = ts * 1000, dm = Math.floor((n - t) / 60000)
  if (dm < 1) return '刚刚'
  if (dm < 60) return dm + ' 分钟前'
  if (dm < 1440) return Math.floor(dm / 60) + ' 小时前'
  return fmt(ts)
}
export function copyText(text: string, btn: HTMLElement | null) {
  navigator.clipboard.writeText(text).then(() => {
    if (btn) {
      const o = btn.textContent
      btn.textContent = '✓ 已复制'
      btn.classList.add('bg-green-100', 'text-green-600')
      setTimeout(() => { btn.textContent = o; btn.classList.remove('bg-green-100', 'text-green-600') }, 1500)
    }
  }).catch(() => {})
}
export async function scanThumbnails(type: string) {
  return api('POST', '/api/admin/scan-thumbnails', { type })
}

export async function resizeImage(file: File): Promise<File> {
  return new Promise((resolve, reject) => {
    const img = new Image(), url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      const c = document.createElement('canvas')
      c.width = 128; c.height = 128
      c.getContext('2d')!.drawImage(img, 0, 0, 128, 128)
      c.toBlob(b => {
        if (b) resolve(new File([b], file.name.replace(/\.\w+$/i, '.webp'), { type: 'image/webp' }))
        else reject(new Error('缩略图生成失败'))
      }, 'image/webp', 0.85)
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片加载失败')) }
    img.src = url
  })
}

export const onlineGithubIds = ref<Set<string>>(new Set())
export function setOnlineUsers(users: any[]) {
  onlineGithubIds.value = new Set((users || []).map((u: any) => u.github_id))
}