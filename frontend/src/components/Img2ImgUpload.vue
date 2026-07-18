<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ onLog?: (msg: string) => void }>()

interface AccImg {
  id: string
  name: string
  previewUrl: string
  progress: number
  done: boolean
  error?: string
  upload?: Promise<void>
  xhr?: XMLHttpRequest
}
const images = ref<AccImg[]>([])
const MAX_SHORT = 1440, MAX_LONG = 2560, MAX_BYTES = 3000 * 1024

function makeId() {
  return globalThis.crypto?.randomUUID?.() || `img_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function isCurrent(item: AccImg) {
  return images.value.includes(item)
}

function addImage(file: File) {
  if (images.value.length >= 3) return
  const previewUrl = URL.createObjectURL(file)
  const item: AccImg = { id: makeId(), name: '', previewUrl, progress: 0, done: false }
  images.value.push(item)

  item.upload = new Promise<void>(async (resolve) => {
    const fail = (msg: string) => {
      if (isCurrent(item)) {
        item.error = msg
        item.done = false
      }
      resolve()
    }

    try {
      const blob = await compressImage(file)
      if (!isCurrent(item)) { resolve(); return }

      const fd = new FormData()
      fd.append('image1', blob, file.name || 'img.jpg')
      const xhr = new XMLHttpRequest()
      item.xhr = xhr
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && isCurrent(item)) item.progress = Math.round(e.loaded / e.total * 99)
      }
      xhr.onload = () => {
        if (!isCurrent(item)) { resolve(); return }
        item.xhr = undefined
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const d = JSON.parse(xhr.responseText)
            item.name = d.image1_name || ''
            item.progress = 100
            item.done = true
            item.error = ''
            resolve()
          } catch {
            fail('上传响应解析失败')
          }
        } else {
          let msg = '上传失败'
          try {
            const d = JSON.parse(xhr.responseText)
            msg = d.detail || d.error || msg
          } catch {}
          fail(msg)
        }
      }
      xhr.onerror = () => { item.xhr = undefined; fail('上传失败，请检查网络或反向代理连接') }
      xhr.onabort = () => { item.xhr = undefined; resolve() }
      xhr.open('POST', '/api/img2img/upload')
      xhr.timeout = 180000  // 3 分钟超时：慢速网络上传 + 后端转发 ComfyUI 都计入这段时间
      xhr.ontimeout = () => { item.xhr = undefined; fail('上传超时，请换更小图片或稍后重试') }
      xhr.send(fd)
    } catch (er: any) {
      fail(er?.message || '图片处理失败')
    }
  })
}

function compressImage(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      let w = img.width, h = img.height
      const short = Math.min(w, h), long = Math.max(w, h)
      if (short > MAX_SHORT || long > MAX_LONG) {
        const ratio = Math.min(MAX_SHORT / short, MAX_LONG / long)
        w = Math.round(w * ratio); h = Math.round(h * ratio)
      }
      const canvas = document.createElement('canvas')
      canvas.width = w; canvas.height = h
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, w, h)
      URL.revokeObjectURL(img.src)
      // 先尝试 0.98
      canvas.toBlob(async (blob) => {
        if (!blob) { resolve(file); return }
        let resultBlob: Blob = blob
        if (resultBlob.size > MAX_BYTES) {
          let lo = 0.7, hi = 0.98
          for (let i = 0; i < 6; i++) {
            const q = (lo + hi) / 2
            const b = await new Promise<Blob | null>(r => canvas.toBlob(r, 'image/jpeg', q))
            if (!b) break
            resultBlob = b
            if (b.size <= MAX_BYTES) lo = q; else hi = q
          }
        }
        if (resultBlob.size > MAX_BYTES) {
          const ratio2 = Math.sqrt(MAX_BYTES / resultBlob.size)
          const c2 = document.createElement('canvas')
          c2.width = Math.round(w * ratio2); c2.height = Math.round(h * ratio2)
          c2.getContext('2d')!.drawImage(canvas, 0, 0, c2.width, c2.height)
          resultBlob = await new Promise<Blob | null>(r => c2.toBlob(r, 'image/jpeg', 0.85)) || resultBlob
        }
        const origKB = (file.size / 1024).toFixed(0)
        const newKB = (resultBlob.size / 1024).toFixed(0)
        props.onLog?.(`📐 图片压缩: ${origKB}KB → ${newKB}KB (${w}x${h})`)
        resolve(resultBlob)
      }, 'image/jpeg', 0.98)
    }
    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = URL.createObjectURL(file)
  })
}

function removeImage(idx: number) {
  const item = images.value[idx]
  if (item) {
    item.xhr?.abort()
    URL.revokeObjectURL(item.previewUrl)
    images.value.splice(idx, 1)
  }
}
function clearAll() {
  images.value.forEach(item => {
    item.xhr?.abort()
    URL.revokeObjectURL(item.previewUrl)
  })
  images.value = []
}
function pickFile() {
  const inp = document.createElement('input')
  inp.type = 'file'; inp.accept = 'image/*'; inp.multiple = true
  inp.onchange = () => {
    for (const f of Array.from(inp.files || [])) addImage(f)
  }
  inp.click()
}
async function waitAllUploads() {
  const current = [...images.value]
  await Promise.all(current.map(i => i.upload).filter(Boolean) as Promise<void>[])
  const failed = images.value.find(i => i.error)
  if (failed) throw new Error(failed.error || '参考图上传失败')
  if (images.value.some(i => !i.done || !i.name)) throw new Error('参考图上传未完成')
}
const getImageNames = () => images.value.filter(i => i.done && i.name).map(i => i.name)
const hasPendingUploads = () => images.value.some(i => !i.done && !i.error)
defineExpose({ waitAllUploads, getImageNames, clearAll, hasPendingUploads })
</script>

<template>
  <div>
    <div v-if="!images.length" class="border-2 border-dashed border-pink-200 rounded-2xl p-6 text-center text-xs text-gray-400 cursor-pointer hover:bg-pink-50/50 transition-all" @click="pickFile">
      📤 点击上传参考图（支持多张）
    </div>
    <div v-else id="img-preview" class="flex flex-wrap gap-2">
      <div v-for="(img, i) in images" :key="img.id" class="relative" style="width:128px;height:128px">
        <img :src="img.previewUrl" class="w-full h-full object-cover rounded-xl border border-pink-100" style="width:128px;height:128px" />
        <button @click="removeImage(i)" class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-red-500/80 text-white text-[10px] leading-none hover:bg-red-700 cursor-pointer border-0">✕</button>
        <div v-if="img.error" class="absolute inset-x-1 bottom-6 rounded bg-red-500/80 px-1 py-0.5 text-center text-[10px] leading-tight text-white">上传失败</div>
        <div class="upload-progress">
          <div class="upload-progress-bar" :class="{ done: img.done, error: img.error }" :style="{ width: img.progress + '%' }"></div>
        </div>
      </div>
      <div class="border-2 border-dashed border-pink-200 rounded-xl flex items-center justify-center text-lg text-gray-300 cursor-pointer hover:bg-pink-50/50" style="width:128px;height:128px" @click="pickFile">+</div>
    </div>
  </div>
</template>
