<script setup lang="ts">
import { useUserStore } from './stores/user'
import { onMounted } from 'vue'

const userStore = useUserStore()

onMounted(async () => {
  await userStore.fetchWhoami()
})
</script>

<template>
  <router-view />
  <div id="toast-container" class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none max-w-[calc(100vw-2rem)]"></div>
</template>
