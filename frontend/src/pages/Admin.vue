<script setup lang="ts">
import { ref, onMounted, type Component } from 'vue'
import { api } from '@/components/admin/useAdminApi'
import AdminLightbox from '@/components/admin/AdminLightbox.vue'
import QueueSection from '@/components/admin/QueueSection.vue'
import AnnSection from '@/components/admin/AnnSection.vue'
import ResSection from '@/components/admin/ResSection.vue'
import StyleSection from '@/components/admin/StyleSection.vue'
import CharacterSection from '@/components/admin/CharacterSection.vue'
import WfMetaSection from '@/components/admin/WfMetaSection.vue'
import LlmSection from '@/components/admin/LlmSection.vue'
import LlmTemplateSection from '@/components/admin/LlmTemplateSection.vue'
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
import StatsSection from '@/components/admin/StatsSection.vue'
import LeaderBoardSection from '@/components/admin/LeaderBoardSection.vue'

const isAdmin = ref(false), loading = ref(true)
const expanded = ref<Record<string, boolean>>({})

interface SectionDef { key: string; title: string; comp: Component }
interface GroupDef { id: string; title: string; sections: SectionDef[] }

const groups: GroupDef[] = [
  {
    id: 'overview', title: '📊 概览',
    sections: [
      { key: 'stats', title: '📊 系统统计', comp: StatsSection },
      { key: 'queue', title: '🏃 队列管理', comp: QueueSection },
      { key: 'leaderboard', title: '🏆 生图排行榜', comp: LeaderBoardSection },
    ],
  },
  {
    id: 'content', title: '🎨 内容设置',
    sections: [
      { key: 'ann', title: '📢 公告管理', comp: AnnSection },
      { key: 'res', title: '📐 分辨率管理', comp: ResSection },
      { key: 'styles', title: '🖌️ 画风管理', comp: StyleSection },
      { key: 'characters', title: '🎭 角色管理', comp: CharacterSection },
      { key: 'wfmeta', title: '🔗 工作流缩略图 & Lora 链接', comp: WfMetaSection },
      { key: 'featured', title: '⭐ 精选管理', comp: FeaturedSection },
    ],
  },
  {
    id: 'system', title: '⚙️ 系统设置',
    sections: [
      { key: 'llm', title: '🤖 LLM 配置', comp: LlmSection },
      { key: 'llm-templates', title: '🧩 LLM 提示词模板', comp: LlmTemplateSection },
      { key: 'limits', title: '⚙️ 限流配置', comp: LimitsSection },
      { key: 'maint', title: '🔧 维护模式', comp: MaintSection },
      { key: 'chead', title: '📎 自定义 Head', comp: CheadSection },
    ],
  },
  {
    id: 'security', title: '👤 用户与安全',
    sections: [
      { key: 'users', title: '👤 用户管理', comp: UsersSection },
      { key: 'email', title: '📧 邮箱认证管理', comp: EmailSection },
      { key: 'keys', title: '🔑 访问密钥管理', comp: AccessKeySection },
      { key: 'bans', title: '🛡️ IP 封禁管理', comp: BanSection },
      { key: 'reports', title: '🚩 举报管理', comp: ReportSection },
    ],
  },
  {
    id: 'moderation', title: '🗂️ 内容审核',
    sections: [
      { key: 'genlogs', title: '📋 生图日志', comp: GenLogSection },
      { key: 'recent', title: '📋 生图记录', comp: RecentSection },
      { key: 'images', title: '🖼️ 图片管理', comp: ImageSection },
      { key: 'dellog', title: '🗑️ 删除记录', comp: DeletionLogSection },
      { key: 'gc', title: '🧹 GC 系统', comp: GcSection },
    ],
  },
]

onMounted(async () => {
  try { isAdmin.value = (await api('GET', '/api/admin/whoami')).is_admin } catch { isAdmin.value = false }
  loading.value = false
})

function toggle(k: string) { expanded.value[k] = !expanded.value[k] }

function setGroup(g: GroupDef, open: boolean) {
  for (const s of g.sections) expanded.value[s.key] = open
}

function scrollToGroup(id: string) {
  document.getElementById('grp-' + id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>
<template>
  <div class="admin-root min-h-screen bg-gray-100" style="overflow-y: auto; height: 100vh;">
    <AdminLightbox />
    <div class="admin-container max-w-6xl mx-auto p-4">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold">&#x1F6E1;&#xFE0F; 管理员控制台</h1>
        <a href="/" class="text-sm text-blue-600 hover:underline">&larr; 返回首页</a>
      </div>

      <div v-if="!isAdmin && !loading" class="max-w-md mx-auto mt-20 text-center p-8 bg-white rounded-2xl shadow-sm">
        <p class="text-4xl mb-4">&#x1F512;</p>
        <p class="text-gray-500">需要管理员权限</p>
      </div>

      <template v-if="isAdmin">
        <!-- 顶部分组锚点导航 -->
        <nav class="sticky top-0 z-10 -mx-4 px-4 py-2 mb-4 bg-gray-100/90 backdrop-blur border-b border-gray-200">
          <div class="flex flex-wrap gap-2">
            <button
              v-for="g in groups"
              :key="g.id"
              @click="scrollToGroup(g.id)"
              class="px-3 py-1 text-xs rounded-full bg-white border border-gray-200 text-gray-600 hover:bg-pink-50 hover:text-pink-600 hover:border-pink-200 cursor-pointer transition-colors"
            >{{ g.title }}</button>
          </div>
        </nav>

        <!-- 分组 + 手风琴 -->
        <section v-for="g in groups" :key="g.id" :id="'grp-' + g.id" class="mb-6 scroll-mt-16">
          <div class="flex items-center gap-3 mb-2">
            <h2 class="text-sm font-bold text-gray-400 tracking-wide uppercase">{{ g.title }}</h2>
            <div class="flex-1 border-t border-gray-200"></div>
            <button @click="setGroup(g, true)" class="text-[11px] text-gray-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">全部展开</button>
            <button @click="setGroup(g, false)" class="text-[11px] text-gray-400 hover:text-pink-500 cursor-pointer border-0 bg-transparent">全部折叠</button>
          </div>

          <div v-for="s in g.sections" :key="s.key" class="bg-white rounded shadow p-4 mb-3">
            <div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggle(s.key)">
              <h3 class="text-lg font-semibold">
                <span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded[s.key] ? 'rotate-90' : ''">&#x25B8;</span>
                {{ s.title }}
              </h3>
            </div>
            <div v-show="expanded[s.key]">
              <component :is="s.comp" :visible="expanded[s.key]" />
            </div>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>
