<script setup>
/**
 * Courbe d'évolution d'un prix.
 *
 * Le composant reste volontairement bête : il reçoit une série déjà convertie
 * (`{ label, value }`) et se contente de la tracer.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import { isDark } from '../theme'

const props = defineProps({
  series: { type: Array, default: () => [] },
  currency: { type: String, default: 'EUR' },
  heightClass: { type: String, default: 'h-40' },
})

const canvas = ref(null)
let chart = null

function build() {
  if (!canvas.value) return
  chart?.destroy()
  chart = null
  if (!props.series.length) return

  const colors = {
    text: isDark.value ? '#cbd5e1' : '#475569',
    grid: isDark.value ? 'rgba(148,163,184,0.18)' : 'rgba(100,116,139,0.18)',
  }

  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels: props.series.map((point) => point.label),
      datasets: [
        {
          label: `Prix (${props.currency})`,
          data: props.series.map((point) => point.value),
          borderColor: '#0ea5e9',
          backgroundColor: 'rgba(14,165,233,0.18)',
          fill: true,
          tension: 0.25,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: colors.text }, grid: { display: false } },
        y: {
          beginAtZero: false,
          ticks: { color: colors.text },
          grid: { color: colors.grid },
        },
      },
    },
  })
}

onMounted(build)
watch(() => [props.series, isDark.value], build, { deep: true, flush: 'post' })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div :class="heightClass">
    <canvas v-if="series.length > 1" ref="canvas" />
    <p v-else class="pt-6 text-sm text-slate-400 dark:text-slate-500">
      {{ series.length === 1 ? 'Un seul relevé : la courbe apparaîtra au suivant.' : 'Aucun relevé de prix.' }}
    </p>
  </div>
</template>
