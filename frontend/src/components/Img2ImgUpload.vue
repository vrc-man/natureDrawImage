<script setup lang="ts">
import { ref } from 'vue'

interface AccImg { name: string; file: File; previewUrl: string; progress: number; done: boolean }
const images = ref<AccImg[]>([])
const show = ref(false)

function addImage(file: File) {
  const previewUrl = URL.createObjectURL(file)
  images.value.push({ name: file.name, file, previewUrl, progress: 0, done: false })
  uploadImage(images.value.length - 1, file)
}

function compressImage(file: File): Promise<Blob> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.onload = () => {
        let w = img.width, h = img.height
        const maxShort = 1440, maxLong = 2560, maxBytes = 3 * 1024 * 1024
        if (w > h) { if (h > maxShort) { h = maxShort; w = Math.round(w * maxShort / img.height) } if (w > maxLong) { w = maxLong; h = Math.round(h * maxLong / w) } }
        else { if (w > maxShort) { w = maxShort; h = Math.round(h * maxShort / img.width) } if (h > maxLong) { h = maxLong; w = Math.round(w * maxLong / h) } }
        let quality = 0.85
        const canvas = document.createElement('canvas')
        canvas.width = w; canvas.height = h
        const ctx = canvas.getContext('2d')!
        ctx.drawImage(img, 0, 0, w, h)
        const tryCompress = () => {
          canvas.toBlob(blob => {
            if (!blob) { resolve(file); return }
            if (blob.size > maxBytes && quality > 0.1) { quality -= 0.1; tryCompress(); return }
            resolve(blob)
          }, 'image/jpeg', quality)
        }
        tryCompress()
      }
      img.src = e.target!.result as string
    }
    reader.readAsDataURL(file)
  })
}

async function uploadImage(idx: number, file: File) {
  try {
    const compressed = await compressImage(file)
    const formData = new FormData()
    formData.append('file', compressed, file.name)
    const xhr = new XMLHttpRequest()
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) images.value[idx].progress = Math.round(e.loaded * 100 / e.total)
    }
    xhr.onload = () => {
      if (xhr.status === 200) {
        images.value[idx].done = true
        images.value[idx].progress = 100
      }
    }
    xhr.onerror = () => { images.value.splice(idx, 1) }
    xhr.open('POST', '/api/img2img/upload')
    xhr.send(formData)
  } catch {
    images.value.splice(idx, 1)
  }
}

function removeImage(idx: number) { images.value.splice(idx, 1) }

function clearAll() { images.value = [] }

function pickFile() {
  const inp = document.createElement('input')
  inp.type = 'file'; inp.accept = 'image/*'; inp.multiple = true
  inp.onchange = () => {
    for (const f of Array.from(inp.files || [])) addImage(f)
  }
  inp.click()
}
</script>

<template>
  <div>
    <div v-if="!images.length" class="border-2 border-dashed border-pink-200 rounded-2xl p-6 text-center text-xs text-gray-400 cursor-pointer hover:bg-pink-50/50 transition-all" @click="pickFile">
      📤 点击上传参考图（支持多张）
    </div>
    <div v-else id="img-preview" class="flex flex-wrap gap-2">
      <div v-for="(img, i) in images" :key="i" class="relative" style="width:128px;height:128px">
        <img :src="img.previewUrl" class="w-full h-full object-cover rounded-xl border border-pink-100" style="width:128px;height:128px" />
        <button @click="removeImage(i)" class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-red-500/80 text-white text-[10px] leading-none hover:bg-red-700 cursor-pointer border-0">✕</button>
        <div v-if="!img.done" class="upload-progress">
          <div class="upload-progress-bar" :style="{ width: img.progress + '%' }"></div>
        </div>
      </div>
      <div class="border-2 border-dashed border-pink-200 rounded-xl flex items-center justify-center text-lg text-gray-300 cursor-pointer hover:bg-pink-50/50" style="width:128px;height:128px" @click="pickFile">+</div>
    </div>
  </div>
</template>
