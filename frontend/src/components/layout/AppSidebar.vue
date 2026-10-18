<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ui, toggleSidebar, closeMobileSidebar } from '../../ui'
import { visibleNavItems, isActiveRoute } from '../../layout/navItems'
import AppIcon from './AppIcon.vue'
import AppTooltip from './AppTooltip.vue'

const route = useRoute()
const items = computed(() => visibleNavItems())
const collapsed = computed(() => ui.sidebarCollapsed)

function followRoute() {
  closeMobileSidebar()
}

const buildStamp = __BUILD_STAMP__
</script>

<template>
  <aside
    class="fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col border-r border-slate-200 bg-white transition-[width,transform] duration-200 ease-out dark:border-slate-800 dark:bg-slate-900 lg:static lg:translate-x-0"
    :class="[
      collapsed ? 'w-[4.75rem]' : 'w-64',
      ui.mobileOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full lg:shadow-none',
    ]"
    aria-label="Navigation principale"
  >
    <!-- Marque -->
    <div class="flex h-16 items-center gap-3 px-4">
      <span class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sky-600 text-base font-bold text-white">
        A
      </span>
      <span v-if="!collapsed" class="min-w-0">
        <span class="block truncate text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100">AviaDB</span>
        <span class="block truncate text-xs text-slate-500 dark:text-slate-400">Collection aviation</span>
      </span>
      <button
        type="button"
        class="ml-auto rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 lg:hidden dark:hover:bg-slate-800 dark:hover:text-slate-200"
        aria-label="Fermer le menu"
        @click="closeMobileSidebar"
      >
        <AppIcon name="collapseLeft" size="h-4 w-4" />
      </button>
    </div>

    <!-- Entrées -->
    <nav class="flex-1 space-y-1 overflow-y-auto px-2 py-2">
      <RouterLink
        v-for="item in items"
        :key="item.name"
        :to="item.to"
        class="group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors"
        :class="[
          isActiveRoute(item, route.path)
            ? 'bg-sky-50 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300'
            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100',
          collapsed ? 'justify-center px-0' : '',
        ]"
        :aria-current="isActiveRoute(item, route.path) ? 'page' : undefined"
        @click="followRoute"
      >
        <AppIcon :name="item.icon" size="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">{{ item.label }}</span>
        <AppTooltip v-if="collapsed" :label="item.label" />
      </RouterLink>
    </nav>

    <!-- Pied : repli (bureau), thème, version -->
    <div class="border-t border-slate-200 p-2 dark:border-slate-800">
      <button
        type="button"
        class="group relative hidden w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 lg:flex dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        :class="collapsed ? 'justify-center px-0' : ''"
        :aria-label="collapsed ? 'Déplier le menu' : 'Replier le menu'"
        @click="toggleSidebar"
      >
        <AppIcon :name="collapsed ? 'collapseRight' : 'collapseLeft'" size="h-5 w-5 shrink-0" />
        <span v-if="!collapsed">Replier</span>
        <AppTooltip v-if="collapsed" :label="'Déplier le menu'" />
      </button>

      <p
        v-if="!collapsed"
        class="px-3 pt-2 text-[0.65rem] leading-tight text-slate-400 dark:text-slate-600"
      >
        build {{ buildStamp }}
      </p>
    </div>
  </aside>
</template>
