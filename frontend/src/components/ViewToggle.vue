<script setup>
import AppIcon from './layout/AppIcon.vue'
import AppTooltip from './layout/AppTooltip.vue'

defineProps({
  modelValue: { type: String, default: 'grid' },
})
const emit = defineEmits(['update:modelValue'])

const OPTIONS = [
  { value: 'grid', icon: 'grid', label: 'Vue grille' },
  { value: 'list', icon: 'list', label: 'Vue liste' },
]
</script>

<template>
  <div
    class="inline-flex rounded-lg border border-slate-300 p-0.5 dark:border-slate-700"
    role="group"
    aria-label="Mode d’affichage"
  >
    <button
      v-for="option in OPTIONS"
      :key="option.value"
      type="button"
      class="group relative grid h-8 w-8 place-items-center rounded-md transition"
      :class="
        modelValue === option.value
          ? 'bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100'
          : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
      "
      :aria-pressed="modelValue === option.value"
      :aria-label="option.label"
      @click="emit('update:modelValue', option.value)"
    >
      <AppIcon :name="option.icon" size="h-4 w-4" />
      <AppTooltip :label="option.label" placement="bottom" />
    </button>
  </div>
</template>
