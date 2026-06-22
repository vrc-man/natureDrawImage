function _doneNotifyEnabled(): boolean {
  return localStorage.getItem('doneNotify') !== 'false'
}

export function showToast(text: string, duration?: number) {
  if (!_doneNotifyEnabled()) return
  const el = document.createElement('div')
  el.className = 'toast-el bg-white/95 backdrop-blur border border-pink-100 rounded-2xl shadow-xl px-5 py-4 text-sm sm:text-base text-gray-700 cursor-pointer select-none'
  el.textContent = text
  el.onclick = () => { el.style.animation = 'toastOut 0.25s ease-in'; setTimeout(() => el.remove(), 250) }
  const container = document.getElementById('toast-container')
  if (container) container.appendChild(el)
  setTimeout(() => {
    el.style.animation = 'toastOut 0.25s ease-in'
    setTimeout(() => { try { el.remove() } catch {} }, 250)
  }, duration || 3000)
}

export function showCenterToast(text: string, duration = 1500) {
  const container = document.createElement('div')
  container.id = 'center-toast-container'
  const el = document.createElement('div')
  el.className = 'center-toast-el'
  el.textContent = text
  container.appendChild(el)
  document.body.appendChild(container)
  setTimeout(() => {
    el.style.animation = 'centerToastOut 0.2s ease-in forwards'
    setTimeout(() => { try { container.remove() } catch {} }, 200)
  }, duration)
}

export function showErrorToast(text: string) {
  const el = document.createElement('div')
  el.className = 'toast-el bg-white/95 backdrop-blur border border-red-200 rounded-2xl shadow-xl px-5 py-4 text-sm sm:text-base text-red-700 cursor-pointer select-none'
  el.textContent = '❌ ' + text
  el.onclick = () => { el.style.animation = 'toastOut 0.25s ease-in'; setTimeout(() => el.remove(), 250) }
  const tc = document.getElementById('toast-container')
  if (tc) tc.appendChild(el)
}
