import { defineStore } from 'pinia'
import { api } from '@/api/client'

export interface UserInfo {
  logged_in: boolean
  is_admin?: boolean
  login?: string
  email?: string
  avatar_url?: string
  is_email_user?: boolean
  access_granted?: boolean
  key_status?: string
  key_info?: any
  unread_notifications?: number
  my_queue_count?: number
}

export const useUserStore = defineStore('user', {
  state: () => ({
    currentUser: null as UserInfo | null,
  }),
  getters: {
    isLoggedIn: (s) => !!s.currentUser?.logged_in,
    isAdmin: (s) => !!s.currentUser?.is_admin,
  },
  actions: {
    async fetchWhoami() {
      try {
        this.currentUser = await api<UserInfo>('GET', '/api/whoami')
      } catch {
        this.currentUser = { logged_in: false }
      }
    },
  },
})
