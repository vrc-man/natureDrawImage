import { ref, reactive } from 'vue'

export interface LbItem {
  url: string
  title?: string
  time?: string
  creator?: string
  path?: string
  filename?: string
  downloadUrl?: string
}

const lbState = reactive({ items: [] as LbItem[], index: 0 })
const lbOpen = ref(false)

export function useLightbox() {
  function open(items: LbItem[], index = 0) {
    lbState.items = items
    lbState.index = index
    lbOpen.value = true
    document.body.style.overflow = 'hidden'
  }

  function close() {
    lbOpen.value = false
    document.body.style.overflow = ''
  }

  function prev() {
    if (lbState.items.length > 0) {
      lbState.index = (lbState.index - 1 + lbState.items.length) % lbState.items.length
    }
  }

  function next() {
    if (lbState.items.length > 0) {
      lbState.index = (lbState.index + 1) % lbState.items.length
    }
  }

  const current = () => lbState.items[lbState.index] || null

  return { lbOpen, lbState, current, open, close, prev, next }
}
