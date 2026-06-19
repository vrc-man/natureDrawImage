<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/components/admin/useAdminApi'
import AdminLightbox from '@/components/admin/AdminLightbox.vue'
import QueueSection from '@/components/admin/QueueSection.vue'
import AnnSection from '@/components/admin/AnnSection.vue'
import ResSection from '@/components/admin/ResSection.vue'
import StyleSection from '@/components/admin/StyleSection.vue'
import CharacterSection from '@/components/admin/CharacterSection.vue'
import WfMetaSection from '@/components/admin/WfMetaSection.vue'
import LlmSection from '@/components/admin/LlmSection.vue'
import LimitsSection from '@/components/admin/LimitsSection.vue'
import MaintSection from '@/components/admin/MaintSection.vue'
import CheadSection from '@/components/admin/CheadSection.vue'
import UsersSection from '@/components/admin/UsersSection.vue'
import EmailSection from '@/components/admin/EmailSection.vue'
import AccessKeySection from '@/components/admin/AccessKeySection.vue'
import GenLogSection from '@/components/admin/GenLogSection.vue'
import DeletionLogSection from '@/components/admin/DeletionLogSection.vue'
import BanSection from '@/components/admin/BanSection.vue'
import ReportSection from '@/components/admin/ReportSection.vue'
import FeaturedSection from '@/components/admin/FeaturedSection.vue'
import RecentSection from '@/components/admin/RecentSection.vue'
import ImageSection from '@/components/admin/ImageSection.vue'
import GcSection from '@/components/admin/GcSection.vue'

const isAdmin = ref(false), loading = ref(true)
const expanded = ref<Record<string, boolean>>({})

onMounted(async () => {
  try { isAdmin.value = (await api('GET', '/api/admin/whoami')).is_admin } catch { isAdmin.value = false }
  loading.value = false
})
function toggle(k: string) { expanded.value[k] = !expanded.value[k] }
</script>
<template>
  <div class="min-h-screen bg-gray-100" style="overflow-y: auto; height: 100vh;">
    <AdminLightbox />
    <div class="max-w-6xl mx-auto p-4">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold">&#x1F6E1;&#xFE0F; 管理员控制台</h1>
        <a href="/" class="text-sm text-blue-600 hover:underline">&larr; 返回首页</a>
      </div>
      <div v-if="!isAdmin && !loading" class="max-w-md mx-auto mt-20 text-center p-8 bg-white rounded-2xl shadow-sm"><p class="text-4xl mb-4">&#x1F512;</p><p class="text-gray-500">需要管理员权限</p></div>
      <template v-if="isAdmin">
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('queue')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.queue?'rotate-90':''">&#x25B8;</span> &#x1F3C3; 队列管理</h2></div><div v-show="expanded.queue"><QueueSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('ann')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.ann?'rotate-90':''">&#x25B8;</span> &#x1F4E2; 公告管理</h2></div><div v-show="expanded.ann"><AnnSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('res')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.res?'rotate-90':''">&#x25B8;</span> &#x1F4D0; 分辨率管理</h2></div><div v-show="expanded.res"><ResSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('styles')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.styles?'rotate-90':''">&#x25B8;</span> &#x1F58C;&#xFE0F; 画风管理</h2></div><div v-show="expanded.styles"><StyleSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('characters')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.characters?'rotate-90':''">&#x25B8;</span> &#x1F3AD; 角色管理</h2></div><div v-show="expanded.characters"><CharacterSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('wfmeta')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.wfmeta?'rotate-90':''">&#x25B8;</span> &#x1F517; 工作流缩略图 &amp; Lora 链接</h2></div><div v-show="expanded.wfmeta"><WfMetaSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('llm')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.llm?'rotate-90':''">&#x25B8;</span> &#x1F916; LLM 配置</h2></div><div v-show="expanded.llm"><LlmSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('limits')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.limits?'rotate-90':''">&#x25B8;</span> &#x2699;&#xFE0F; 限流配置</h2></div><div v-show="expanded.limits"><LimitsSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('maint')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.maint?'rotate-90':''">&#x25B8;</span> &#x1F527; 维护模式</h2></div><div v-show="expanded.maint"><MaintSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('chead')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.chead?'rotate-90':''">&#x25B8;</span> &#x1F4CE; 自定义 Head</h2></div><div v-show="expanded.chead"><CheadSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('users')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.users?'rotate-90':''">&#x25B8;</span> &#x1F464; 用户管理</h2></div><div v-show="expanded.users"><UsersSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('email')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.email?'rotate-90':''">&#x25B8;</span> &#x1F4E7; 邮箱认证管理</h2></div><div v-show="expanded.email"><EmailSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('keys')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.keys?'rotate-90':''">&#x25B8;</span> &#x1F511; 访问密钥管理</h2></div><div v-show="expanded.keys"><AccessKeySection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('genlogs')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.genlogs?'rotate-90':''">&#x25B8;</span> &#x1F4CB; 生图日志</h2></div><div v-show="expanded.genlogs"><GenLogSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('dellog')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.dellog?'rotate-90':''">&#x25B8;</span> &#x1F5D1;&#xFE0F; 删除记录</h2></div><div v-show="expanded.dellog"><DeletionLogSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('bans')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.bans?'rotate-90':''">&#x25B8;</span> &#x1F6E1;&#xFE0F; IP 封禁管理</h2></div><div v-show="expanded.bans"><BanSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('reports')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.reports?'rotate-90':''">&#x25B8;</span> &#x1F6A9; 举报管理</h2></div><div v-show="expanded.reports"><ReportSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('featured')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.featured?'rotate-90':''">&#x25B8;</span> &#x2B50; 精选管理</h2></div><div v-show="expanded.featured"><FeaturedSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('recent')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.recent?'rotate-90':''">&#x25B8;</span> &#x1F4CB; 生图记录</h2></div><div v-show="expanded.recent"><RecentSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('images')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.images?'rotate-90':''">&#x25B8;</span> &#x1F5BC;&#xFE0F; 图片管理</h2></div><div v-show="expanded.images"><ImageSection :visible="true" /></div></div>
        <div class="bg-white rounded shadow p-4 mb-4"><div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle('gc')"><h2 class="text-lg font-semibold"><span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.gc?'rotate-90':''">&#x25B8;</span> &#x1F9F9; GC 系统</h2></div><div v-show="expanded.gc"><GcSection :visible="true" /></div></div>
      </template>
    </div>
  </div>
</template>