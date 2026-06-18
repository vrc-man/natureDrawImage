import { api, apiRaw } from './client'
import type {
  WorkflowItem, StyleItem, CharacterItem, ResolutionPreset,
  QueueItem, NotificationResponse, AnnouncementData
} from './types'

// === Auth ===
export const whoami = () => api('GET', '/api/whoami')
export const claimKey = (key: string) => api('POST', '/api/auth/claim-key', { key })
export const logout = () => apiRaw('/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' } })

// === Workflows ===
export const loadWorkflows = () =>
  api<{ workflows?: WorkflowItem[]; all?: WorkflowItem[]; txt2img_dir?: string; img2img_dir?: string }>('GET', '/api/workflows')

// === Styles & Characters ===
export const loadStyles = () => api<{ styles?: StyleItem[]; characters?: CharacterItem[] }>('GET', '/api/styles')
export const loadCharacters = () => api<{ styles?: StyleItem[]; characters?: CharacterItem[] }>('GET', '/api/characters')

// === Resolutions ===
export const loadResolutions = () => api<ResolutionPreset[]>('GET', '/api/resolutions')

// === Queue ===
export const myQueue = () => api<{ items: QueueItem[]; total: number }>('GET', '/api/my-queue')

// === Gallery ===
export const loadGallery = (params?: { offset?: number; limit?: number }) =>
  api<{ items: any[]; total: number; output_dir?: string }>('GET', '/api/output/list' + (params ? '?' + new URLSearchParams({ offset: String(params.offset || 0), limit: String(params.limit || 30) }) : ''))

export const loadFeatured = () => api<{ items: any[]; tip?: string }>('GET', '/api/output/featured')

export const loadMyImages = (params?: { offset?: number; limit?: number }) =>
  api<{ items: any[]; total: number }>('GET', '/api/my-images' + (params ? '?' + new URLSearchParams({ offset: String(params.offset || 0), limit: String(params.limit || 30) }) : ''))

export const deleteMyImage = (path: string) =>
  api('DELETE', '/api/my-images', { path })

// === Notifications ===
export const fetchNotifications = () => api<NotificationResponse>('GET', '/api/notifications')
export const markNotificationsRead = () => api('POST', '/api/whoami/read-notifications')

// === GPU ===
export const fetchGPU = () => api('GET', '/api/gpu')

// === Announcement ===
export const fetchAnnouncement = () => api<AnnouncementData>('GET', '/api/announcement')

// === Report ===
export const submitReport = (data: { path: string; reason?: string }) =>
  api('POST', '/api/report', data)

// === TOTP ===
export const totpStatus = () => api<{ totp_enabled: boolean }>('GET', '/api/auth/totp-status')
export const totpSetup = () => api<{ secret: string; enabled?: boolean }>('POST', '/api/auth/totp-setup')
export const totpEnable = (code: string) => api('POST', '/api/auth/totp-enable', { code })
export const totpDisable = () => api('POST', '/api/auth/totp-disable')

// === Fork ===
export const forkWorkflow = (data: { path: string; inline_workflow?: any }) =>
  api('POST', '/api/output/fork', data)
