<script setup>
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { ui, closeMobileSidebar } from '../../ui'
import AppSidebar from './AppSidebar.vue'
import AppTopbar from './AppTopbar.vue'

// Referme le tiroir mobile à chaque changement de page.
const route = useRoute()
watch(
  () => route.path,
  () => closeMobileSidebar(),
)
</script>

<template>
  <div class="flex min-h-screen bg-slate-100 dark:bg-slate-950">
    <AppSidebar />

    <!-- Voile du tiroir mobile -->
    <Transition
      enter-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      leave-active-class="transition-opacity duration-150"
      leave-to-class="opacity-0"
    >
      <div
        v-if="ui.mobileOpen"
        class="fixed inset-0 z-30 bg-slate-900/50 lg:hidden"
        aria-hidden="true"
        @click="closeMobileSidebar"
      />
    </Transition>

    <div class="flex min-w-0 flex-1 flex-col">
      <AppTopbar />
      <main class="mx-auto w-full flex-1 px-4 py-6 sm:px-6 lg:px-8">
        <slot />
      </main>
      <footer class="px-4 pb-4 text-center text-xs text-slate-400 lg:hidden dark:text-slate-600">
        AviaDB · build {{ __BUILD_STAMP__ }}
      </footer>
    </div>
  </div>
</template>
