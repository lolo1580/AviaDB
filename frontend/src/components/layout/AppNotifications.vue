<script setup>
import { ref } from 'vue'
import {
  notifications,
  unreadCount,
  markAllRead,
  clearNotifications,
  relativeTime,
} from '../../notifications'
import { useClickOutside } from '../../composables/useClickOutside'
import AppIcon from './AppIcon.vue'

const open = ref(false)
const root = ref(null)

useClickOutside(root, () => {
  open.value = false
})

const TYPE_STYLES = {
  success: 'text-emerald-600 dark:text-emerald-400',
  error: 'text-rose-600 dark:text-rose-400',
  info: 'text-sky-600 dark:text-sky-400',
}

const TYPE_ICONS = {
  success: 'check',
  error: 'alert',
  info: 'info',
}

function toggle() {
  open.value = !open.value
  if (open.value && unreadCount.value) markAllRead()
}
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="group relative grid h-9 w-9 place-items-center rounded-lg border border-slate-300 text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      :aria-expanded="open"
      aria-haspopup="menu"
      :aria-label="`Notifications${unreadCount ? ` (${unreadCount} non lues)` : ''}`"
      @click="toggle"
    >
      <AppIcon name="bell" size="h-4 w-4" />
      <span
        v-if="unreadCount"
        class="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[0.6rem] font-bold text-white ring-2 ring-white dark:ring-slate-900"
      >
        {{ unreadCount > 9 ? '9+' : unreadCount }}
      </span>
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      leave-active-class="transition duration-100 ease-in"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="open"
        role="menu"
        class="absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div class="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">Notifications</p>
          <button
            v-if="notifications.length"
            type="button"
            class="text-xs font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            @click="clearNotifications"
          >
            Vider
          </button>
        </div>

        <ul v-if="notifications.length" class="max-h-80 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
          <li v-for="entry in notifications" :key="entry.id" class="flex gap-3 px-4 py-3">
            <AppIcon
              :name="TYPE_ICONS[entry.type] || 'info'"
              size="h-4 w-4 shrink-0"
              class="mt-0.5"
              :class="TYPE_STYLES[entry.type] || TYPE_STYLES.info"
            />
            <div class="min-w-0">
              <p class="text-sm leading-snug text-slate-700 dark:text-slate-200">{{ entry.message }}</p>
              <p class="mt-0.5 text-xs text-slate-400 dark:text-slate-500">{{ relativeTime(entry.at) }}</p>
            </div>
          </li>
        </ul>

        <div v-else class="flex flex-col items-center gap-2 px-4 py-10 text-center">
          <AppIcon name="inbox" size="h-8 w-8 text-slate-300 dark:text-slate-600" />
          <p class="text-sm text-slate-400 dark:text-slate-500">Aucune notification</p>
        </div>
      </div>
    </Transition>
  </div>
</template>
