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

export interface WorkflowItem {
  path: string
  name?: string
  thumb?: string
  thumbnail?: boolean
  category?: string
}

export interface StyleItem {
  name: string
  tags: string
  image?: string
  thumb?: string
  category?: string
}

export interface CharacterItem {
  name: string
  tags: string
  image?: string
  thumb?: string
  category?: string
}

export interface ResolutionPreset {
  w: number
  h: number
  label?: string
}

export interface QueueItem {
  id: number
  status: 'waiting' | 'running' | 'done' | 'failed' | 'cancelled'
  created_at: number
  position?: number
  error_message?: string
}

export interface NotificationResponse {
  my_queue_count?: number
  unread_notifications?: number
  online_count?: number
}

export interface ImageItem {
  url: string
  filename: string
  subfolder?: string
  image_type?: string
}

export interface AnnouncementData {
  announcement?: { title?: string; content?: string; enabled?: boolean }
}
