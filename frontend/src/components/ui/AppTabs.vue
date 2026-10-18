<script setup>
/**
 * Barre d'onglets réutilisable — Tailwind uniquement.
 *
 * Accessibilité : `role="tablist"`, `role="tab"` avec `aria-selected` et
 * `aria-controls`, index de tabulation glissant (une seule tabulation arrête
 * le groupe) et navigation aux flèches / Début / Fin.
 *
 * @example
 * <AppTabs v-model="ui.adminTab" :tabs="[{ id: 'items', label: 'Objets', icon: 'collection', badge: 12 }]" />
 */
import { ref } from 'vue'
import AppIcon from '../layout/AppIcon.vue'

const props = defineProps({
  tabs: { type: Array, required: true },
  modelValue: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue'])

const buttons = ref([])

function select(id) {
  emit('update:modelValue', id)
}

function onKeydown(event, index) {
  const keys = ['ArrowRight', 'ArrowLeft', 'Home', 'End']
  if (!keys.includes(event.key)) return
  event.preventDefault()

  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % props.tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + props.tabs.length) % props.tabs.length
  else if (event.key === 'Home') next = 0
  else next = props.tabs.length - 1

  select(props.tabs[next].id)
  buttons.value[next]?.focus()
}
</script>

<template>
  <div
    role="tablist"
    class="thin-scroll flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800"
  >
    <button
      v-for="(tab, index) in tabs"
      :key="tab.id"
      ref="buttons"
      type="button"
      role="tab"
      :id="`tab-${tab.id}`"
      :aria-selected="modelValue === tab.id"
      :aria-controls="`panel-${tab.id}`"
      :tabindex="modelValue === tab.id ? 0 : -1"
      class="-mb-px flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
      :class="
        modelValue === tab.id
          ? 'border-sky-600 text-sky-700 dark:border-sky-400 dark:text-sky-300'
          : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700 dark:text-slate-400 dark:hover:border-slate-700 dark:hover:text-slate-200'
      "
      @click="select(tab.id)"
      @keydown="onKeydown($event, index)"
    >
      <AppIcon v-if="tab.icon" :name="tab.icon" size="h-4 w-4" />
      {{ tab.label }}
      <span
        v-if="tab.badge !== undefined && tab.badge !== null"
        class="rounded-full px-1.5 py-0.5 text-xs font-semibold"
        :class="
          modelValue === tab.id
            ? 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300'
            : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
        "
      >
        {{ tab.badge }}
      </span>
    </button>
  </div>
</template>
