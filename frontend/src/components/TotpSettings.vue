<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { totpStatus, totpSetup, totpEnable, totpDisable } from '@/api/endpoints'

const emit = defineEmits<{ back: [] }>()
const enabled = ref(false)
const secret = ref('')
const verifyCode = ref('')
const statusMsg = ref('')
const loading = ref(true)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const st = await totpStatus()
    enabled.value = st.totp_enabled
    if (!st.totp_enabled) {
      const setup = await totpSetup()
      if (setup.enabled) { enabled.value = true }
      else { secret.value = setup.secret }
    }
  } catch {}
  loading.value = false
}

async function doEnable() {
  if (verifyCode.value.length !== 6) { statusMsg.value = '请输入6位验证码'; return }
  statusMsg.value = ''
  try {
    await totpEnable(verifyCode.value)
    enabled.value = true
    statusMsg.value = '✅ 已启用'
  } catch (e: any) { statusMsg.value = '验证失败: ' + e.message }
}

async function doDisable() {
  try {
    await totpDisable()
    enabled.value = false
    await load()
  } catch {}
}
</script>

<template>
  <div>
    <div class="flex items-center gap-2 pb-3 border-b border-pink-100">
      <button @click="emit('back')" class="text-lg text-gray-400 hover:text-gray-600 cursor-pointer border-0 bg-transparent">&larr;</button>
      <h3 class="text-base font-bold text-gray-700">🔐 两步验证 (2FA)</h3>
    </div>
    <div v-if="loading" class="pt-4 text-center text-sm text-gray-400">加载中...</div>
    <div v-else-if="enabled" class="pt-4 space-y-3">
      <p class="text-sm text-green-600">✅ 两步验证已启用</p>
      <p class="text-xs text-gray-500">每次登录时需要输入 6 位验证码。</p>
      <button @click="doDisable" class="w-full py-2.5 bg-red-100 text-red-500 rounded-xl hover:bg-red-200 text-sm font-medium transition-all cursor-pointer border-0">关闭 2FA</button>
    </div>
    <div v-else class="pt-4 space-y-3">
      <p class="text-sm text-gray-600">请在 Google Authenticator / Microsoft Authenticator 等 App 中手动输入以下密钥：</p>
      <div class="flex justify-center"><img :src="'/api/auth/totp-qrcode?t=' + Date.now()" class="rounded-xl border border-pink-100" style="width:180px;height:180px" /></div>
      <p class="text-xs text-gray-400">扫描二维码，或手动输入密钥：</p>
      <div class="bg-gray-100 rounded-xl px-4 py-3 text-center font-mono text-sm tracking-widest text-gray-800 select-all">{{ secret }}</div>
      <label class="text-sm text-gray-600">输入 App 中显示的 6 位验证码：</label>
      <input v-model="verifyCode" type="text" inputmode="numeric" maxlength="6" placeholder="000000" class="w-full border border-pink-200 rounded-xl px-4 py-3 text-sm text-center tracking-widest bg-white focus:border-pink-400 focus:ring-2 focus:ring-pink-200 outline-none transition-all box-border" />
      <button @click="doEnable" class="w-full py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl hover:from-pink-300 hover:to-rose-300 text-sm font-semibold transition-all cursor-pointer border-0">验证并启用</button>
      <span class="text-xs text-red-400 block min-h-[18px]">{{ statusMsg }}</span>
    </div>
  </div>
</template>
