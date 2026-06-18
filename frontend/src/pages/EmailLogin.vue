<script setup lang="ts">
import { ref, onMounted } from 'vue'

function togglePw(id: string, btn: HTMLElement) {
  const i = document.getElementById(id) as HTMLInputElement
  if (!i) return
  i.type = i.type === 'password' ? 'text' : 'password'
  btn.textContent = i.type === 'password' ? '👁' : '🙈'
}

const tab = ref<'login'|'register'|'forgot'>('login')
const loginEmail = ref('')
const loginPwd = ref('')
const loginTotp = ref('')
const loginStatus = ref('')
const loginLoading = ref(false)

const regEmail = ref('')
const regPwd = ref('')
const regPwd2 = ref('')
const regCode = ref('')
const regStatus = ref('')
const regLoading = ref(false)

const fgEmail = ref('')
const fgStatus = ref('')
const fgLoading = ref(false)

const showSuccess = ref(false)
const successMsg = ref('')

// Cloudflare Turnstile
let turnstileWidget: any = null
declare const turnstile: any

onMounted(() => {
  if (tab.value === 'register') renderTurnstile()
})

function switchTab(t: 'login' | 'register' | 'forgot') {
  tab.value = t
  if (t === 'register') setTimeout(renderTurnstile, 100)
  if (t === 'forgot') setTimeout(renderForgotTurnstile, 200)
}

function renderTurnstile() {
  const c = document.getElementById('turnstile-container')
  if (!c || typeof turnstile === 'undefined') return
  c.innerHTML = ''
  try {
    turnstileWidget = turnstile.render('#turnstile-container', {
      sitekey: '0x4AAAAAADWvaKWEsnuGl7oU',
      theme: 'light',
    })
  } catch {
    c.innerHTML = '<p style="font-size:12px;color:#ef4444">验证组件加载失败，请刷新重试</p>'
  }
}

function getTurnstileToken(container: string): string {
  if (typeof turnstile !== 'undefined') {
    try { return turnstile.getResponse(container) || '' } catch {}
  }
  return ''
}

async function doLogin() {
  if (loginLoading.value) return
  loginLoading.value = true
  loginStatus.value = ''
  try {
    const r = await fetch('/api/auth/login-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: loginEmail.value.trim(),
        password: loginPwd.value,
        totp_code: loginTotp.value.trim(),
      }),
    })
    const d = await r.json()
    if (!r.ok) throw new Error(d.detail || '登录失败')
    location.href = '/'
  } catch (e: any) {
    loginStatus.value = e.message
  } finally {
    loginLoading.value = false
  }
}

async function doRegister() {
  if (regLoading.value) return
  if (regPwd.value.length < 6) { regStatus.value = '密码至少6位'; return }
  if (regPwd.value !== regPwd2.value) { regStatus.value = '两次密码不一致'; return }
  regLoading.value = true
  regStatus.value = ''
  try {
    const token = getTurnstileToken(turnstileWidget)
    const r = await fetch('/api/auth/register-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: regEmail.value.trim(),
        password: regPwd.value,
        invite_code: regCode.value.trim(),
        turnstile_token: token,
      }),
    })
    const d = await r.json()
    if (!r.ok) throw new Error(d.detail || '注册失败')
    successMsg.value = d.message || '注册成功！请查收验证邮件并点击链接激活账号后登录。'
    showSuccess.value = true
  } catch (e: any) {
    regStatus.value = e.message
  } finally {
    regLoading.value = false
  }
}

function closeSuccess() {
  showSuccess.value = false
  switchTab('login')
}

function renderForgotTurnstile() {
  const c = document.getElementById('turnstile-forgot-container')
  if (!c || typeof turnstile === 'undefined' || c.hasChildNodes()) return
  try { turnstile.render('#turnstile-forgot-container', { sitekey: '0x4AAAAAADWvaKWEsnuGl7oU', theme: 'light' }) } catch {}
}

async function doForgot() {
  if (fgLoading.value) return
  renderForgotTurnstile()
  fgLoading.value = true
  fgStatus.value = ''
  try {
    const token = getTurnstileToken('#turnstile-forgot-container')
    const r = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: fgEmail.value.trim(),
        turnstile_token: token,
      }),
    })
    const d = await r.json()
    fgStatus.value = d.message || '发送成功'
  } catch (e: any) {
    fgStatus.value = '发送失败，请重试'
  } finally {
    fgLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-5" style="background:linear-gradient(135deg,#fef2f4,#fdf2f8,#faf5ff,#fff1f2,#fef2f4);background-size:400% 400%;animation:bgShift 30s ease infinite">
    <style scoped>
      .card { background: linear-gradient(180deg, rgba(255,245,247,0.98), rgba(255,255,255,0.96), rgba(255,241,242,0.95)); border: 1px solid rgba(244,114,182,0.12); border-radius: 24px; box-shadow: 0 4px 30px rgba(244,114,182,0.15), 0 0 80px rgba(244,114,182,0.06); max-width: 420px; width: 100%; padding: 32px 24px; }
      .pw-wrap { position: relative; }
      .pw-toggle { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); cursor: pointer; font-size: 16px; user-select: none; color: #9ca3af; background: none; border: none; }
      .pw-toggle:hover { color: #f472b6; }
      .modal-overlay { position: fixed; inset: 0; z-index: 999; background: rgba(0,0,0,0.3); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; padding: 20px; }
      .modal-overlay.show { display: flex; }
      .modal-box { background: #fff; border-radius: 24px; max-width: 400px; width: 100%; padding: 32px 24px; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.15); }
    </style>
    <div class="card">
      <h2 class="text-center text-xl font-bold text-gray-800 mb-5">📧 邮箱注册登陆</h2>
      <div class="flex rounded-xl bg-pink-100 p-0.5 mb-5">
        <button :class="['flex-1 py-2 text-sm font-medium rounded-xl transition-all cursor-pointer border-0', tab==='login'?'bg-white text-pink-500 shadow-sm':'text-gray-400 bg-transparent']" @click="switchTab('login')">登录</button>
        <button :class="['flex-1 py-2 text-sm font-medium rounded-xl transition-all cursor-pointer border-0', tab==='register'?'bg-white text-pink-500 shadow-sm':'text-gray-400 bg-transparent']" @click="switchTab('register')">注册</button>
      </div>

      <!-- Login -->
      <div v-show="tab==='login'">
        <input v-model="loginEmail" type="email" placeholder="邮箱地址" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" />
        <div class="pw-wrap">
          <input id="el-pwd" v-model="loginPwd" type="password" placeholder="密码" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" style="padding-right:36px" />
          <button type="button" class="pw-toggle" @click="togglePw('el-pwd', $event.target as HTMLElement)">👁</button>
        </div>
        <input v-model="loginTotp" type="text" placeholder="两步验证码（未开启请留空）" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" />
        <button @click="doLogin" :disabled="loginLoading" class="w-full py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl font-semibold hover:from-pink-300 hover:to-rose-300 transition-all disabled:opacity-50 cursor-pointer border-0 shadow-md shadow-pink-300/30">
          {{ loginLoading ? '登录中...' : '登录' }}
        </button>
        <span class="block text-xs text-center mt-1.5 min-h-[18px]" :class="loginStatus.includes('失败')?'text-red-500':'text-gray-400'">{{ loginStatus }}</span>
        <p class="text-center mt-1.5"><a href="#" class="text-xs text-gray-400 no-underline hover:text-pink-500" @click.prevent="tab='forgot'">忘记密码？</a></p>
      </div>

      <!-- Forgot Password -->
      <div v-show="tab==='forgot'">
        <p class="text-center text-sm text-gray-500 mb-3">输入注册邮箱，我们将发送重置链接</p>
        <input v-model="fgEmail" type="email" placeholder="邮箱地址" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" />
        <div id="turnstile-forgot-container" class="mb-2.5 min-h-[65px]"></div>
        <button @click="doForgot" :disabled="fgLoading" class="w-full py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl font-semibold hover:from-pink-300 hover:to-rose-300 transition-all disabled:opacity-50 cursor-pointer border-0 shadow-md shadow-pink-300/30">
          {{ fgLoading ? '发送中...' : '发送重置链接' }}
        </button>
        <span class="block text-xs text-center mt-1.5 min-h-[18px]" :class="fgStatus.includes('失败')?'text-red-500':'text-green-600'">{{ fgStatus }}</span>
        <p class="text-center mt-2"><a href="#" class="text-xs text-gray-400 no-underline hover:text-pink-500" @click.prevent="tab='login'">← 返回登录</a></p>
      </div>

      <!-- Register -->
      <div v-show="tab==='register'">
        <input v-model="regEmail" type="email" placeholder="邮箱地址" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" />
        <div class="pw-wrap">
          <input id="er-pwd" v-model="regPwd" type="password" placeholder="密码（至少6位）" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" style="padding-right:36px" />
          <button type="button" class="pw-toggle" @click="togglePw('er-pwd', $event.target as HTMLElement)">👁</button>
        </div>
        <div class="pw-wrap">
          <input id="er-pwd2" v-model="regPwd2" type="password" placeholder="确认密码" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" style="padding-right:36px" />
          <button type="button" class="pw-toggle" @click="togglePw('er-pwd2', $event.target as HTMLElement)">👁</button>
        </div>
        <input v-model="regCode" type="text" placeholder="邀请码（可选，有码无需邮箱验证）" class="w-full border border-pink-100 rounded-xl px-3.5 py-2.5 text-sm mb-2.5 outline-none focus:border-pink-400 focus:ring-3 focus:ring-pink-100 transition-all box-border" />
        <div id="turnstile-container" class="mb-2.5 min-h-[65px]"></div>
        <button @click="doRegister" :disabled="regLoading" class="w-full py-2.5 bg-gradient-to-r from-emerald-400 to-green-500 text-white rounded-xl font-semibold hover:from-emerald-300 hover:to-green-400 transition-all disabled:opacity-50 cursor-pointer border-0 shadow-md shadow-emerald-300/30">
          {{ regLoading ? '注册中...' : '注册' }}
        </button>
        <p class="text-center mt-1.5 text-[11px] text-gray-400">📨 验证邮件通常在 1 分钟内送达</p>
        <span class="block text-xs text-center mt-1.5 min-h-[18px]" :class="regStatus.includes('失败')?'text-red-500':'text-gray-400'">{{ regStatus }}</span>
      </div>

      <a href="/" class="block text-center mt-4 text-sm text-gray-400 no-underline hover:text-pink-500">← 返回首页</a>
    </div>

    <!-- Success Modal -->
    <Teleport to="body">
      <div :class="['modal-overlay', {show: showSuccess}]">
        <div class="modal-box">
          <div class="text-5xl mb-3">📧</div>
          <h3 class="text-lg font-bold text-gray-800 mb-2">注册成功！</h3>
          <p class="text-sm text-gray-500 mb-5">{{ successMsg }}</p>
          <button @click="closeSuccess" class="w-full py-2.5 bg-gradient-to-r from-pink-400 to-rose-400 text-white rounded-xl font-semibold cursor-pointer border-0 shadow-md">前往登录</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
