<script setup>
/**
 * Infobulle Tailwind pure.
 *
 * Le parent doit porter la classe `group` (et `relative` pour le placement).
 * Elle apparaît au survol **et** au focus clavier, ce qui la rend utilisable
 * avec la barre latérale repliée en rail d'icônes.
 */
defineProps({
  label: { type: String, required: true },
  placement: { type: String, default: 'right' }, // 'right' | 'bottom'
})
</script>

<template>
  <span
    role="tooltip"
    class="pointer-events-none absolute z-50 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 dark:bg-slate-700"
    :class="
      placement === 'right'
        ? 'left-full top-1/2 ml-2 -translate-y-1/2'
        : 'left-1/2 top-full mt-2 -translate-x-1/2'
    "
  >
    {{ label }}
  </span>
</template>
