<script setup>
import { computed } from 'vue'
import { formatMoney } from '../labels'
import { settings } from '../settings'

const props = defineProps({ stats: { type: Object, default: null } })

const base = computed(() => settings.default_currency)

const cards = computed(() => {
  const s = props.stats
  if (!s) return []
  const gain = s.total_estimated_value - s.total_purchase_value
  return [
    { label: 'Pièces', value: s.total_items },
    { label: `Valeur estimée (${base.value})`, value: formatMoney(s.total_estimated_value, base.value) ?? '—' },
    { label: `Valeur d’achat (${base.value})`, value: formatMoney(s.total_purchase_value, base.value) ?? '—' },
    {
      label: `Plus-value (${base.value})`,
      value: formatMoney(gain, base.value) ?? '—',
      tone:
        gain > 0
          ? 'text-emerald-600 dark:text-emerald-400'
          : gain < 0
            ? 'text-rose-600 dark:text-rose-400'
            : '',
    },
    { label: 'Photos', value: s.total_photos },
  ]
})

function total(buckets) {
  return (buckets || []).reduce((acc, b) => acc + b.count, 0) || 1
}
</script>

<template>
  <section v-if="stats" class="grid gap-4 lg:grid-cols-[repeat(5,minmax(0,1fr))_2fr]">
    <div
      v-for="card in cards"
      :key="card.label"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <p class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ card.label }}</p>
      <p
        class="mt-1 text-2xl font-semibold"
        :class="card.tone || 'text-slate-900 dark:text-slate-100'"
      >
        {{ card.value }}
      </p>
    </div>

    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Répartition par pays
      </p>
      <ul v-if="stats.by_country.length" class="mt-3 space-y-2">
        <li v-for="row in stats.by_country.slice(0, 5)" :key="row.key">
          <div class="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400">
            <span class="font-medium text-slate-700 dark:text-slate-300">{{ row.key }}</span>
            <span>{{ row.count }}</span>
          </div>
          <div class="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              class="h-full rounded-full bg-sky-500"
              :style="{ width: `${(row.count / total(stats.by_country)) * 100}%` }"
            />
          </div>
        </li>
      </ul>
      <p v-else class="mt-3 text-sm text-slate-400 dark:text-slate-500">Aucune donnée</p>
    </div>
  </section>
</template>
