<script setup>
import { computed } from 'vue'
import { STATUS_LABEL, TYPE_LABEL } from '../labels'
import { flattenedClasses } from '../classes'

const props = defineProps({
  filters: { type: Object, required: true },
  facets: { type: Object, required: true },
  enums: { type: Object, default: null },
  total: { type: Number, default: 0 },
})

const classOptions = computed(() => flattenedClasses())

const SORTS = [
  { value: 'name', label: 'Nom' },
  { value: 'estimated_value', label: 'Valeur estimée' },
  { value: 'country', label: 'Pays' },
  { value: 'aircraft_model', label: 'Modèle' },
  { value: 'purchase_date', label: 'Date d’achat' },
  { value: 'created_at', label: 'Ajout' },
]

const labelClass = 'text-xs font-medium text-slate-500 dark:text-slate-400'
const selectClass =
  'rounded-lg border border-slate-300 px-2 py-2 text-sm shadow-sm outline-none focus:border-sky-500 dark:border-slate-700'

// Les filtres sont des tableaux côté API : un select simple en met 0 ou 1.
function setSingle(key, value) {
  props.filters[key] = value ? [value] : []
}

/** La classe est un filtre simple (et englobe sa descendance côté serveur). */
function setClass(value) {
  props.filters.class_id = value === '' ? '' : Number(value)
}

function toggle(key, value) {
  const arr = props.filters[key]
  const idx = arr.indexOf(value)
  if (idx === -1) arr.push(value)
  else arr.splice(idx, 1)
}

function isActive(key, value) {
  return props.filters[key].includes(value)
}

function reset() {
  Object.assign(props.filters, {
    q: '', item_type: [], status: [], country: [], scale: [],
    manufacturer: [], tag: [], sort: 'name', order: 'asc',
  })
}
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
    <div class="flex flex-wrap items-end gap-3">
      <label class="flex min-w-56 flex-1 flex-col gap-1">
        <span :class="labelClass">Recherche</span>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Nom, immatriculation, unité, base…"
          class="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-200 dark:border-slate-700 dark:focus:ring-sky-900"
        />
      </label>

      <label class="flex flex-col gap-1">
        <span :class="labelClass">Pays</span>
        <select
          :value="filters.country[0] || ''"
          :class="selectClass"
          @change="setSingle('country', $event.target.value)"
        >
          <option value="">Tous</option>
          <option v-for="c in facets.countries" :key="c" :value="c">{{ c }}</option>
        </select>
      </label>

      <label class="flex flex-col gap-1">
        <span :class="labelClass">Statut</span>
        <select
          :value="filters.status[0] || ''"
          :class="selectClass"
          @change="setSingle('status', $event.target.value)"
        >
          <option value="">Tous</option>
          <option v-for="s in enums?.statuses || []" :key="s" :value="s">{{ STATUS_LABEL[s] }}</option>
        </select>
      </label>

      <label class="flex flex-col gap-1">
        <span :class="labelClass">Échelle</span>
        <select
          :value="filters.scale[0] || ''"
          :class="selectClass"
          @change="setSingle('scale', $event.target.value)"
        >
          <option value="">Toutes</option>
          <option v-for="s in facets.scales" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>

      <label class="flex flex-col gap-1">
        <span :class="labelClass">Fabricant</span>
        <select
          :value="filters.manufacturer[0] || ''"
          :class="selectClass"
          @change="setSingle('manufacturer', $event.target.value)"
        >
          <option value="">Tous</option>
          <option v-for="m in facets.manufacturers" :key="m" :value="m">{{ m }}</option>
        </select>
      </label>

      <label v-if="classOptions.length" class="flex flex-col gap-1">
        <span :class="labelClass">Classe</span>
        <select
          :value="filters.class_id === '' || filters.class_id === undefined ? '' : String(filters.class_id)"
          :class="selectClass"
          @change="setClass($event.target.value)"
        >
          <option value="">Toutes</option>
          <option v-for="node in classOptions" :key="node.id" :value="node.id">
            {{ '— '.repeat(node.depth) }}{{ node.name }}
          </option>
        </select>
      </label>

      <label class="flex flex-col gap-1">
        <span :class="labelClass">Tag</span>
        <select
          :value="filters.tag[0] || ''"
          :class="selectClass"
          @change="setSingle('tag', $event.target.value)"
        >
          <option value="">Tous</option>
          <option v-for="t in facets.tags" :key="t" :value="t">{{ t }}</option>
        </select>
      </label>

      <label class="flex flex-col gap-1">
        <span :class="labelClass">Tri</span>
        <select v-model="filters.sort" :class="selectClass">
          <option v-for="s in SORTS" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </label>

      <button
        type="button"
        class="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        :class="filters.order === 'desc' ? 'bg-slate-50 dark:bg-slate-800' : ''"
        :title="filters.order === 'asc' ? 'Croissant' : 'Décroissant'"
        @click="filters.order = filters.order === 'asc' ? 'desc' : 'asc'"
      >
        {{ filters.order === 'asc' ? '↑ Croissant' : '↓ Décroissant' }}
      </button>
    </div>

    <div class="mt-3 flex flex-wrap items-center gap-2">
      <span :class="labelClass">Type&nbsp;:</span>
      <button
        v-for="t in enums?.item_types || []"
        :key="t"
        type="button"
        class="rounded-full border px-3 py-1 text-xs font-medium transition"
        :class="isActive('item_type', t)
          ? 'border-sky-500 bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300'
          : 'border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'"
        @click="toggle('item_type', t)"
      >
        {{ TYPE_LABEL[t] }}
      </button>

      <span class="ml-auto flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
        <span>{{ total }} résultat{{ total > 1 ? 's' : '' }}</span>
        <button type="button" class="font-medium text-sky-600 hover:underline dark:text-sky-400" @click="reset">
          Réinitialiser
        </button>
      </span>
    </div>
  </section>
</template>
