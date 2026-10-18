<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ui, toggleSidebar, openMobileSidebar } from '../../ui'
import { anyPending } from '../../optimistic'
import AppIcon from './AppIcon.vue'
import AppNotifications from './AppNotifications.vue'
import AppUserMenu from './AppUserMenu.vue'
import ThemeToggle from '../ThemeToggle.vue'

const route = useRoute()
const title = computed(() => route.meta?.title || 'AviaDB')
const subtitle = computed(() => route.meta?.subtitle || '')
</script>

<template>
  <header
    class="sticky top-0 z-30 flex h-16 items-center gap-2 border-b border-slate-200 bg-white/85 px-3 backdrop-blur sm:gap-3 sm:px-6 dark:border-slate-800 dark:bg-slate-900/85"
  >
    <!-- Menu (mobile) -->
    <button
      type="button"
      class="group grid h-9 w-9 place-items-center rounded-lg border border-slate-300 text-slate-600 transition hover:bg-slate-100 lg:hidden dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      aria-label="Ouvrir le menu"
      @click="openMobileSidebar"
    >
      <AppIcon name="menu" size="h-4 w-4" />
    </button>

    <!-- Repli (bureau) -->
    <button
      type="button"
      class="group hidden h-9 w-9 place-items-center rounded-lg border border-slate-300 text-slate-600 transition hover:bg-slate-100 lg:grid dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      :aria-label="ui.sidebarCollapsed ? 'Déplier le menu' : 'Replier le menu'"
      @click="toggleSidebar"
    >
      <AppIcon :name="ui.sidebarCollapsed ? 'collapseRight' : 'collapseLeft'" size="h-4 w-4" />
    </button>

    <div class="min-w-0">
      <h1 class="truncate text-sm font-semibold text-slate-900 sm:text-base dark:text-slate-100">
        {{ title }}
      </h1>
      <p v-if="subtitle" class="hidden truncate text-xs text-slate-500 sm:block dark:text-slate-400">
        {{ subtitle }}
      </p>
    </div>

    <div class="ml-auto flex items-center gap-2">
      <span
        v-if="anyPending"
        class="hidden items-center gap-2 rounded-lg px-2 py-1 text-xs text-slate-500 sm:flex dark:text-slate-400"
        title="Enregistrement en cours côté serveur"
      >
        <span
          class="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-sky-500 dark:border-slate-700 dark:border-t-sky-400"
        />
        Synchronisation…
      </span>

      <AppNotifications />
      <ThemeToggle />
      <AppUserMenu />
    </div>
  </header>
</template>
