<script setup>
/**
 * Étiquettes de rangement imprimables.
 *
 * Chaque étiquette porte un QR code qui rouvre directement la fiche de l'objet
 * dans l'application (`/?item=<id>`), le nom, le type, l'emplacement et la
 * classe. Le rendu est optimisé pour l'impression (une couleur par page,
 * bordures fines) ; le navigateur produit ensuite un PDF si besoin.
 */
import { computed, onMounted, ref, watch } from 'vue'
import QRCode from 'qrcode'
import { api } from '../api'
import { classPath } from '../classes'
import { TYPE_LABEL } from '../labels'
import AppIcon from '../components/layout/AppIcon.vue'

const items = ref([])
const storageLocations = ref([])
const selectedLocation = ref('')
const search = ref('')
const loading = ref(false)
const error = ref('')
// QR rendus à la demande : id de l'objet -> data-URL PNG.
const codes = ref({})

const filtered = computed(() => {
  const query = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    if (selectedLocation.value && item.storage_location !== selectedLocation.value) return false
    if (query && !item.name.toLowerCase().includes(query)) return false
    return true
  })
})

/** Adresse encodée dans le QR : ouvre la fiche de l'objet. */
function deepLink(id) {
  return `${window.location.origin}/?item=${id}`
}

async function renderCodes() {
  const entries = await Promise.all(
    filtered.value.map(async (item) => [
      item.id,
      await QRCode.toDataURL(deepLink(item.id), { margin: 0, width: 240 }),
    ]),
  )
  codes.value = Object.fromEntries(entries)
}

watch(filtered, renderCodes)

onMounted(async () => {
  loading.value = true
  try {
    const [list, facets] = await Promise.all([
      api.listItems({ limit: 500, sort: 'name' }),
      api.getFacets(),
    ])
    items.value = list.items
    storageLocations.value = facets.storage_locations || []
    await renderCodes()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function printLabels() {
  window.print()
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <!-- Barre d'outils : masquée à l'impression -->
    <div class="flex flex-wrap items-end justify-between gap-3 print:hidden">
      <div>
        <h2 class="text-lg font-semibold text-slate-900 dark:text-slate-100">Étiquettes</h2>
        <p class="text-sm text-slate-500 dark:text-slate-400">
          {{ filtered.length }} étiquette(s) — QR code de la fiche, à imprimer et coller sur les
          boîtes.
        </p>
      </div>
      <button
        type="button"
        class="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-700"
        @click="printLabels"
      >
        <AppIcon name="print" size="h-4 w-4" />
        Imprimer
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 print:hidden">
      <label class="flex flex-col gap-1">
        <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Emplacement</span>
        <select
          v-model="selectedLocation"
          class="rounded-lg border border-slate-300 px-2 py-2 text-sm shadow-sm outline-none focus:border-sky-500 dark:border-slate-700"
        >
          <option value="">Tous les emplacements</option>
          <option v-for="loc in storageLocations" :key="loc" :value="loc">{{ loc }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1">
        <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Recherche</span>
        <input
          v-model="search"
          type="search"
          placeholder="Nom de l’objet…"
          class="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-sky-500 dark:border-slate-700"
        />
      </label>
      <span v-if="loading" class="text-sm text-slate-400">chargement…</span>
    </div>

    <p
      v-if="error"
      class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
    >
      {{ error }}
    </p>

    <div
      v-if="filtered.length"
      class="grid grid-cols-[repeat(auto-fill,minmax(88mm,1fr))] gap-3 print:grid-cols-2 print:gap-2"
    >
      <article
        v-for="item in filtered"
        :key="item.id"
        class="label-card flex items-center gap-3 rounded-lg border border-slate-300 bg-white p-3 text-slate-900"
      >
        <img
          v-if="codes[item.id]"
          :src="codes[item.id]"
          :alt="`QR ${item.name}`"
          class="h-20 w-20 shrink-0"
        />
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold" :title="item.name">{{ item.name }}</p>
          <p class="text-xs text-slate-600">
            {{ TYPE_LABEL[item.item_type] || item.item_type }}
            <span v-if="item.country"> · {{ item.country }}</span>
          </p>
          <p class="mt-1 text-xs font-medium text-slate-700">
            {{ item.storage_location || 'Sans emplacement' }}
          </p>
          <p v-if="classPath(item.class_id)" class="truncate text-[11px] text-slate-500">
            {{ classPath(item.class_id) }}
          </p>
          <p class="mt-0.5 font-mono text-[10px] text-slate-400">#{{ item.id }}</p>
        </div>
      </article>
    </div>

    <div
      v-else
      class="rounded-xl border border-dashed border-slate-300 py-20 text-center dark:border-slate-700 print:hidden"
    >
      <p class="text-slate-500 dark:text-slate-400">Aucun objet à étiqueter.</p>
    </div>
  </div>
</template>
