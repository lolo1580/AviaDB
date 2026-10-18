<script setup>
import { toasts, dismissToast, toast } from '../toast'

const STYLES = {
  success: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-200',
  error: 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/80 dark:text-rose-200',
  info: 'border-slate-300 bg-white text-slate-700 dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-200',
}
</script>

<template>
  <TransitionGroup
    tag="div"
    name="toast"
    class="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
  >
    <div
      v-for="entry in toasts"
      :key="entry.id"
      class="pointer-events-auto flex items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-lg backdrop-blur"
      :class="STYLES[entry.type] || STYLES.info"
      role="status"
    >
      <span class="mt-0.5 shrink-0">
        <svg v-if="entry.type === 'success'" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.6l7.3-7.3a1 1 0 0 1 1.4 0Z" clip-rule="evenodd" />
        </svg>
        <svg v-else-if="entry.type === 'error'" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm1-11a1 1 0 1 0-2 0v4a1 1 0 1 0 2 0V7Zm-1 7a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z" clip-rule="evenodd" />
        </svg>
        <svg v-else class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 0-2 0v4a1 1 0 1 0 2 0V6Zm-1 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" clip-rule="evenodd" />
        </svg>
      </span>

      <p class="flex-1 leading-snug">{{ entry.message }}</p>

      <button
        v-if="entry.action"
        type="button"
        class="shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold underline-offset-2 hover:underline"
        @click="toast.runAction(entry)"
      >
        {{ entry.action.label }}
      </button>
      <button
        type="button"
        class="shrink-0 text-current/60 transition hover:text-current"
        aria-label="Fermer"
        @click="dismissToast(entry.id)"
      >
        ✕
      </button>
    </div>
  </TransitionGroup>
</template>
