<script setup>
import { computed, ref } from 'vue'
import { auth, logout } from '../../auth'
import { useClickOutside } from '../../composables/useClickOutside'
import AppIcon from './AppIcon.vue'

const open = ref(false)
const root = ref(null)

useClickOutside(root, () => {
  open.value = false
})

const initials = computed(() => {
  const name = (auth.username || '?').trim()
  const parts = name.split(/[\s._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
})

const roleLabel = computed(() => (auth.role === 'ADMIN' ? 'Administrateur' : 'Lecteur'))
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="group flex items-center gap-2 rounded-full p-0.5 transition hover:bg-slate-100 dark:hover:bg-slate-800"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <span
        class="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-sky-500 to-indigo-500 text-xs font-bold text-white ring-2 ring-white dark:ring-slate-900"
      >
        {{ initials }}
      </span>
      <span class="hidden text-left sm:block">
        <span class="block text-xs font-semibold leading-tight text-slate-800 dark:text-slate-100">
          {{ auth.username }}
        </span>
        <span class="block text-[0.65rem] leading-tight text-slate-500 dark:text-slate-400">
          {{ roleLabel }}
        </span>
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
        class="absolute right-0 z-50 mt-2 w-56 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div class="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <p class="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{{ auth.username }}</p>
          <p class="text-xs text-slate-500 dark:text-slate-400">{{ roleLabel }}</p>
        </div>

        <div class="p-1">
          <RouterLink
            to="/admin"
            class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            role="menuitem"
            @click="open = false"
          >
            <AppIcon name="admin" size="h-4 w-4" />
            Administration
          </RouterLink>
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-rose-600 transition hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/50"
            role="menuitem"
            @click="open = false; logout()"
          >
            <AppIcon name="logout" size="h-4 w-4" />
            Déconnexion
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>
