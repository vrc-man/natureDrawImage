import { ref } from 'vue'

const STORAGE_KEYS = {
  soundNotify: 'soundNotify',
  soundVolume: 'soundVolume',
}

export function useSound() {
  const soundEnabled = ref(localStorage.getItem(STORAGE_KEYS.soundNotify) === 'true')
  const volume = ref(parseFloat(localStorage.getItem(STORAGE_KEYS.soundVolume) || '0.7'))

  function setEnabled(v: boolean) {
    soundEnabled.value = v
    localStorage.setItem(STORAGE_KEYS.soundNotify, String(v))
  }

  function setVolume(v: number) {
    volume.value = v
    localStorage.setItem(STORAGE_KEYS.soundVolume, String(v))
  }

  function loadCustomSound(type: string): { data: string; name: string } {
    return {
      data: localStorage.getItem(`customSound_${type}_data`) || '',
      name: localStorage.getItem(`customSound_${type}_name`) || '',
    }
  }

  function saveCustomSound(type: string, data: string, name: string) {
    if (data) {
      localStorage.setItem(`customSound_${type}_data`, data)
      localStorage.setItem(`customSound_${type}_name`, name)
    } else {
      localStorage.removeItem(`customSound_${type}_data`)
      localStorage.removeItem(`customSound_${type}_name`)
    }
  }

  async function play(type: 'done' | 'error' | 'queued') {
    if (!soundEnabled.value) return
    try {
      if (!window._sndCtx) window._sndCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
      const ctx = window._sndCtx
      if (ctx.state === 'suspended') await ctx.resume()
      const now = ctx.currentTime
      const vol = Math.max(0, Math.min(1, volume.value))
      const cs = loadCustomSound(type)
      if (cs.data) {
        try {
          const b64 = cs.data.split(',')[1]
          const bin = atob(b64)
          const buf = new Uint8Array(bin.length)
          for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
          ctx.decodeAudioData(buf.buffer).then(data => {
            const src = ctx.createBufferSource()
            src.buffer = data
            const vGain = ctx.createGain()
            vGain.gain.value = vol
            src.connect(vGain)
            vGain.connect(ctx.destination)
            src.start(now + 0.05)
          }).catch(() => {})
        } catch (e) { console.warn('[sound] decode', e) }
        return
      }
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      gain.gain.setValueAtTime(Math.min(1, vol * 1.5), now)
      if (type === 'done') {
        osc.frequency.value = 880
        osc.type = 'sine'
        osc.start(now + 0.05)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2)
        osc.stop(now + 0.25)
      } else if (type === 'error') {
        osc.frequency.value = 330
        osc.type = 'sawtooth'
        osc.start(now + 0.05)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4)
        osc.stop(now + 0.45)
      } else if (type === 'queued') {
        osc.frequency.value = 660
        osc.type = 'sine'
        osc.start(now + 0.05)
        gain.gain.setValueAtTime(Math.min(1, vol * 1.5), now + 0.05)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 1)
        osc.stop(now + 1.05)
      }
    } catch (e) { console.warn('[sound]', e) }
  }

  function sendNotification(text: string) {
    if (!soundEnabled.value) return
    if (Notification.permission === 'granted') {
      new Notification('🎨 二次元绘梦', { body: text, icon: '/static/favicon.avif' })
    } else if (Notification.permission === 'default') {
      Notification.requestPermission().then(granted => {
        if (granted === 'granted') {
          new Notification('🎨 二次元绘梦', { body: text, icon: '/static/favicon.avif' })
        }
      })
    }
  }

  return { soundEnabled, volume, setEnabled, setVolume, play, sendNotification, loadCustomSound, saveCustomSound }
}

declare global {
  interface Window { _sndCtx?: AudioContext }
}
