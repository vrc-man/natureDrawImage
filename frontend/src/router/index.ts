import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('@/pages/Home.vue') },
    { path: '/admin', name: 'admin', component: () => import('@/pages/Admin.vue') },
    { path: '/auth/email-login', name: 'emailLogin', component: () => import('@/pages/EmailLogin.vue') },
    { path: '/privacy', name: 'privacy', component: () => import('@/pages/Privacy.vue') },
    { path: '/maintenance', name: 'maintenance', component: () => import('@/pages/Maintenance.vue') },
  ],
})

export default router
