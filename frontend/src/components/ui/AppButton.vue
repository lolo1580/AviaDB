<script setup>
/**
 * Bouton standard, utilisé notamment dans les pieds de modales.
 * Variantes : primary | secondary | danger | ghost — Tailles : sm | md
 */
import { computed } from 'vue'

const props = defineProps({
  variant: { type: String, default: 'secondary' },
  size: { type: String, default: 'md' },
  type: { type: String, default: 'button' },
  loading: { type: Boolean, default: false },
})

const VARIANTS = {
  primary: 'bg-sky-600 text-white shadow-sm hover:bg-sky-700',
  secondary:
    'border border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800',
  danger:
    'bg-rose-600 text-white shadow-sm hover:bg-rose-700',
  ghost: 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
}

const SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
}

const classes = computed(() => [VARIANTS[props.variant] || VARIANTS.secondary, SIZES[props.size] || SIZES.md])
</script>

<template>
  <button
    :type="type"
    :disabled="loading || undefined"
    class="inline-flex items-center justify-center gap-2 rounded-lg font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus-visible:ring-offset-slate-900"
    :class="classes"
  >
    <span
      v-if="loading"
      class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-60"
      aria-hidden="true"
    />
    <slot />
  </button>
</template>
