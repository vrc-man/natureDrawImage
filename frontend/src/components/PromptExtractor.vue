<script setup lang="ts">
import { ref, computed } from 'vue'

const previewUrl = ref('')
const positive = ref('')
const negative = ref('')
const status = ref('')
const ok = ref(false)
const copied = ref<'pos' | 'neg' | null>(null)

const hasPrompt = computed(() => ok.value)

function setStatus(msg: string, isOk = false) {
  status.value = msg
  ok.value = isOk
}

function readPromptText(data: Uint8Array): string {
  const sig = [137, 80, 78, 71, 13, 10, 26, 10]
  if (data.length < 8) throw new Error('文件过短')
  for (let i = 0; i < 8; i++) {
    if (data[i] !== sig[i]) throw new Error('不是 PNG 文件')
  }
  let offset = 8
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength)
  while (offset + 12 <= data.length) {
    const len = dv.getUint32(offset)
    const type = String.fromCharCode(data[offset + 4], data[offset + 5], data[offset + 6], data[offset + 7])
    const dataStart = offset + 8
    const dataEnd = dataStart + len
    if (dataEnd + 4 > data.length) break
    if (type === 'tEXt' || type === 'iTXt') {
      let keyEnd = dataStart
      while (keyEnd < dataEnd && data[keyEnd] !== 0) keyEnd++
      const keyword = new TextDecoder('latin1').decode(data.subarray(dataStart, keyEnd))
      if (keyword === 'prompt') {
        const raw = data.subarray(keyEnd + 1, dataEnd)
        if (type === 'iTXt') {
          // iTXt: keyword\0 compflag(1) compmethod(1) lang\0 translated\0 text
          // 简化处理：压缩标志为 0 时直接读 text
          const text = new TextDecoder('utf-8').decode(raw)
          // 从第一个 NUL 后的文本段里找实际内容
          const parts = text.split('\u0000')
          if (parts.length >= 4) return parts.slice(3).join('\u0000')
          return text
        }
        return new TextDecoder('latin1').decode(raw)
      }
    }
    offset = dataEnd + 4 // 跳过 CRC
  }
  throw new Error('未找到 prompt 元数据')
}

function extractFromPrompt(promptObj: Record<string, any>): { pos: string; neg: string } {
  const nodes = Object.values(promptObj).filter((n: any) => n && typeof n === 'object')
  // 找 CLIPTextEncode 节点
  const encNodes: { id: string; text: string }[] = []
  const idMap: Record<string, any> = {}
  Object.entries(promptObj).forEach(([id, n]: [string, any]) => {
    idMap[id] = n
    if (n && n.class_type === 'CLIPTextEncode' && n.inputs && typeof n.inputs.text === 'string') {
      encNodes.push({ id, text: n.inputs.text })
    }
  })
  if (!encNodes.length) throw new Error('未找到提示词节点')

  // 从采样器/指导器节点的 positive/negative 连线判定
  const posNegFrom = (n: any): { pos: string; neg: string } => {
    const inputs = n.inputs || {}
    let pos = ''
    let neg = ''
    if (Array.isArray(inputs.positive) && idMap[inputs.positive[0]]) {
      const t = idMap[inputs.positive[0]].inputs?.text
      if (typeof t === 'string') pos = t
    }
    if (Array.isArray(inputs.negative) && idMap[inputs.negative[0]]) {
      const t = idMap[inputs.negative[0]].inputs?.text
      if (typeof t === 'string') neg = t
    }
    return { pos, neg }
  }

  // 优先看 CFGGuider（Flux 系），再看 KSampler / KSamplerAdvanced
  for (const [id, n] of Object.entries(promptObj)) {
    if (!n || typeof n !== 'object') continue
    const ct = n.class_type
    if (ct === 'CFGGuider') return posNegFrom(n)
  }
  for (const [id, n] of Object.entries(promptObj)) {
    if (!n || typeof n !== 'object') continue
    const ct = n.class_type
    if (ct !== 'KSampler' && ct !== 'KSamplerAdvanced') continue
    return posNegFrom(n)
  }

  // 退化：无采样器/指导器时，跳过空文本，取第一个非空为正向、第二个非空为负向
  const nonEmpty = encNodes.map(e => e.text).filter(t => t.trim())
  return { pos: nonEmpty[0] || '', neg: nonEmpty[1] || '' }
}

function handleFile(file: File) {
  positive.value = ''
  negative.value = ''
  status.value = ''
  ok.value = false
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)

  const reader = new FileReader()
  reader.onload = () => {
    try {
      const data = new Uint8Array(reader.result as ArrayBuffer)
      const promptRaw = readPromptText(data)
      let promptObj: Record<string, any> = {}
      try {
        // 容错：ComfyUI 某些自定义节点会序列化出 NaN（非标准 JSON），先替换为 null
        const sanitized = promptRaw
          .replace(/NaN/g, 'null')
          .replace(/Infinity/g, 'null')
          .replace(/-Infinity/g, 'null')
        promptObj = JSON.parse(sanitized)
      } catch {
        throw new Error('提示词数据格式无法解析')
      }
      if (!promptObj || typeof promptObj !== 'object') throw new Error('提示词数据格式异常')
      const { pos, neg } = extractFromPrompt(promptObj)
      positive.value = pos
      negative.value = neg
      if (!pos && !neg) {
        setStatus('已解析，但未找到提示词内容', false)
      } else {
        setStatus('提取成功', true)
      }
    } catch (e: any) {
      setStatus(e?.message || '无法解析该图片')
    }
  }
  reader.onerror = () => setStatus('读取文件失败')
  reader.readAsArrayBuffer(file)
}

function onDrop(e: DragEvent) {
  const f = e.dataTransfer?.files?.[0]
  if (f) handleFile(f)
}

async function copyText(text: string, key: 'pos' | 'neg') {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    setTimeout(() => { if (copied.value === key) copied.value = null }, 1500)
  } catch {
    alert('复制失败，请手动选中复制')
  }
}
</script>

<template>
  <div class="space-y-3">
    <!-- 上传区 -->
    <label class="block cursor-pointer">
      <input type="file" accept="image/png" class="hidden" @change="(e) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) handleFile(f) }" />
      <div
        class="flex flex-col items-center justify-center gap-2 py-8 border-2 border-dashed border-gray-200 rounded-2xl hover:border-pink-300 transition-colors text-gray-400"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <span class="text-3xl">🖼️</span>
        <span class="text-xs">点击或拖拽上传 ComfyUI PNG 图片</span>
        <span class="text-[10px] text-gray-300">请上传原始 PNG（未压缩、未重编码）以保留提示词元数据</span>
      </div>
    </label>

    <!-- 缩略图 -->
    <div v-if="previewUrl" class="flex items-start gap-3">
      <img :src="previewUrl" class="w-24 h-24 object-cover rounded-xl border border-gray-200 shrink-0" />
      <div class="text-xs leading-relaxed" :class="ok ? 'text-green-600' : 'text-red-400'">
        <p v-if="ok" class="font-semibold">✅ {{ status }}</p>
        <p v-else-if="status" class="font-semibold">⚠️ {{ status }}</p>
        <p class="text-gray-400 mt-1">PNG 图片 · 可重新上传</p>
      </div>
    </div>

    <!-- 正向卡片 -->
    <div v-if="previewUrl" class="border border-gray-100 rounded-xl bg-white">
      <div class="flex items-center justify-between px-3 py-2 bg-gray-50/80 border-b border-gray-100 rounded-t-xl">
        <span class="text-xs font-semibold text-gray-600">➕ 正向提示词</span>
        <button
          v-if="positive"
          @click="copyText(positive, 'pos')"
          class="text-[10px] px-2 py-1 bg-pink-100 text-pink-600 rounded hover:bg-pink-200 cursor-pointer border-0"
        >{{ copied === 'pos' ? '✓ 已复制' : '📋 复制' }}</button>
      </div>
      <textarea :value="positive" readonly rows="5" placeholder="未提取到正向提示词" class="w-full border-0 rounded-b-xl px-3 py-2.5 text-sm font-mono bg-white resize-y outline-none text-gray-700 placeholder-gray-300 box-border"></textarea>
    </div>

    <!-- 负向卡片 -->
    <div v-if="previewUrl" class="border border-gray-100 rounded-xl bg-white">
      <div class="flex items-center justify-between px-3 py-2 bg-gray-50/80 border-b border-gray-100 rounded-t-xl">
        <span class="text-xs font-semibold text-gray-600">➖ 负向提示词</span>
        <button
          v-if="negative"
          @click="copyText(negative, 'neg')"
          class="text-[10px] px-2 py-1 bg-pink-100 text-pink-600 rounded hover:bg-pink-200 cursor-pointer border-0"
        >{{ copied === 'neg' ? '✓ 已复制' : '📋 复制' }}</button>
      </div>
      <textarea :value="negative" readonly rows="3" placeholder="未提取到负向提示词" class="w-full border-0 rounded-b-xl px-3 py-2.5 text-sm font-mono bg-white resize-y outline-none text-gray-700 placeholder-gray-300 box-border"></textarea>
    </div>
  </div>
</template>
