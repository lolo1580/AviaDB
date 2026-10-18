<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import { api } from '../api'
import { isDark } from '../theme'
import { MATERIAL_LABEL, STATUS_LABEL, TYPE_LABEL, formatMoney } from '../labels'
import { settings } from '../settings'

const stats = ref(null)
const loading = ref(false)
const error = ref('')

const base = computed(() => settings.default_currency)
const ratesNote = computed(() => {
  const meta = settings.rates_updated_at
  if (!meta) return `Converti en ${base.value}`
  return `Converti en ${base.value} — taux ${settings.rates_source || 'saisis'}`
})

const typeCanvas = ref(null)
const statusCanvas = ref(null)
const countryCanvas = ref(null)
const scaleCanvas = ref(null)
const materialCanvas = ref(null)
const yearCanvas = ref(null)
const valueCanvas = ref(null)

let instances = []

const PALETTE = [
  '#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444',
  '#14b8a6', '#6366f1', '#ec4899', '#84cc16', '#f97316',
]

function themeColors() {
  return {
    text: isDark.value ? '#cbd5e1' : '#475569',
    grid: isDark.value ? 'rgba(148,163,184,0.18)' : 'rgba(100,116,139,0.18)',
  }
}

function cartesian(colors, { horizontal = false } = {}) {
  const valueAxis = {
    beginAtZero: true,
    ticks: { color: colors.text },
    grid: { color: colors.grid },
  }
  const categoryAxis = {
    ticks: { color: colors.text },
    grid: { display: false },
  }
  return {
    x: horizontal ? valueAxis : categoryAxis,
    y: horizontal ? categoryAxis : valueAxis,
  }
}

function mount(element, config) {
  if (!element) return
  instances.push(new Chart(element, config))
}

async function build() {
  // Les <canvas> n'existent qu'après le rendu conditionnel `v-if="stats"` :
  // sans attendre la mise à jour du DOM, les références sont encore vides et
  // aucun graphique n'est créé (cas d'un watcher déclenché avant le rendu).
  await nextTick()

  instances.forEach((chart) => chart.destroy())
  instances = []
  if (!stats.value) return

  const colors = themeColors()
  const s = stats.value

  const doughnut = (labels, values, element) =>
    mount(element, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{ data: values, backgroundColor: PALETTE, borderWidth: 0 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { color: colors.text, boxWidth: 12 } } },
      },
    })

  const bar = (labels, values, element, horizontal = false) =>
    mount(element, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ data: values, backgroundColor: PALETTE, borderRadius: 4 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: horizontal ? 'y' : 'x',
        plugins: { legend: { display: false } },
        scales: cartesian(colors, { horizontal }),
      },
    })

  doughnut(s.by_type.map((b) => TYPE_LABEL[b.key] || b.key), s.by_type.map((b) => b.count), typeCanvas.value)
  doughnut(s.by_status.map((b) => STATUS_LABEL[b.key] || b.key), s.by_status.map((b) => b.count), statusCanvas.value)
  doughnut(s.by_scale.map((b) => b.key), s.by_scale.map((b) => b.count), scaleCanvas.value)
  doughnut(
    s.by_material.map((b) => MATERIAL_LABEL[b.key] || b.key),
    s.by_material.map((b) => b.count),
    materialCanvas.value,
  )

  bar(s.by_country.slice(0, 10).map((b) => b.key), s.by_country.slice(0, 10).map((b) => b.count), countryCanvas.value)
  bar(
    s.value_by_country.slice(0, 10).map((b) => b.key),
    s.value_by_country.slice(0, 10).map((b) => b.value),
    valueCanvas.value,
    true,
  )

  mount(yearCanvas.value, {
    type: 'line',
    data: {
      labels: s.by_year.map((b) => b.key),
      datasets: [
        {
          label: 'Acquisitions',
          data: s.by_year.map((b) => b.count),
          borderColor: '#0ea5e9',
          backgroundColor: 'rgba(14,165,233,0.2)',
          fill: true,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: cartesian(colors),
    },
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    stats.value = await api.getStats()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
// `flush: 'post'` : on construit après le rendu, quand les canvas existent.
watch(stats, build, { flush: 'post' })
watch(isDark, build, { flush: 'post' })
onBeforeUnmount(() => {
  instances.forEach((chart) => chart.destroy())
  instances = []
})

const cardClass =
  'rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900'
const titleClass = 'text-sm font-semibold text-slate-800 dark:text-slate-200'
</script>

<template>
  <div class="flex flex-col gap-6">
    <div>
      <h2 class="text-lg font-semibold text-slate-900 dark:text-slate-100">Statistiques</h2>
      <p class="text-sm text-slate-500 dark:text-slate-400">
        Répartition de la collection · <span class="text-slate-400 dark:text-slate-500">{{ ratesNote }}</span>
      </p>
    </div>

    <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
      {{ error }}
    </p>
    <p v-if="loading" class="py-10 text-center text-sm text-slate-400 dark:text-slate-500">Chargement…</p>

    <template v-if="stats">
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div :class="cardClass">
          <p class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Pièces</p>
          <p class="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">{{ stats.total_items }}</p>
        </div>
        <div :class="cardClass">
          <p class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Valeur estimée ({{ base }})
          </p>
          <p class="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
            {{ formatMoney(stats.total_estimated_value, base) }}
          </p>
        </div>
        <div :class="cardClass">
          <p class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Valeur d’achat ({{ base }})
          </p>
          <p class="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
            {{ formatMoney(stats.total_purchase_value, base) }}
          </p>
        </div>
        <div :class="cardClass">
          <p class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Photos</p>
          <p class="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">{{ stats.total_photos }}</p>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        <section :class="cardClass">
          <h3 :class="titleClass">Par type</h3>
          <div class="mt-3 h-64"><canvas ref="typeCanvas" /></div>
        </section>
        <section :class="cardClass">
          <h3 :class="titleClass">Par statut</h3>
          <div class="mt-3 h-64"><canvas ref="statusCanvas" /></div>
        </section>
        <section :class="cardClass">
          <h3 :class="titleClass">Par pays (nombre de pièces)</h3>
          <div class="mt-3 h-64"><canvas ref="countryCanvas" /></div>
        </section>
        <section :class="cardClass">
          <h3 :class="titleClass">Valeur par pays (en {{ base }})</h3>
          <div class="mt-3 h-64"><canvas ref="valueCanvas" /></div>
        </section>
        <section :class="cardClass">
          <h3 :class="titleClass">Acquisitions par année</h3>
          <div class="mt-3 h-64"><canvas ref="yearCanvas" /></div>
        </section>
        <section :class="cardClass">
          <h3 :class="titleClass">Par échelle</h3>
          <div class="mt-3 h-64"><canvas ref="scaleCanvas" /></div>
        </section>
        <section :class="cardClass">
          <h3 :class="titleClass">Patchs par matière</h3>
          <div class="mt-3 h-64"><canvas ref="materialCanvas" /></div>
        </section>
      </div>
    </template>
  </div>
</template>
