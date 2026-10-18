<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { canWrite } from '../auth'
import { ui, setViewMode } from '../ui'
import { isPending } from '../optimistic'
import { confirm as askConfirm } from '../composables/useConfirm'
import { useItemList } from '../composables/useItemList'
import StatsPanel from '../components/StatsPanel.vue'
import FilterBar from '../components/FilterBar.vue'
import ItemCard from '../components/ItemCard.vue'
import ItemListRow from '../components/ItemListRow.vue'
import ViewToggle from '../components/ViewToggle.vue'
import ItemFormModal from '../components/ItemFormModal.vue'
import ItemDetailDrawer from '../components/ItemDetailDrawer.vue'

const stats = ref(null)
const enums = ref(null)
const facets = ref({
  countries: [], aircraft_models: [], storage_locations: [],
  scales: [], manufacturers: [], tags: [],
})
const metaError = ref('')

const filters = reactive({
  q: '', item_type: [], status: [], country: [], scale: [],
  manufacturer: [], tag: [], class_id: '', sort: 'name', order: 'asc',
})

// Les agrégats sont rafraîchis en arrière-plan après chaque mutation :
// l'interface n'attend jamais le serveur.
async function loadStats() {
  try {
    stats.value = await api.getStats()
  } catch {
    /* silencieux : le panneau garde ses valeurs précédentes */
  }
}

const list = useItemList({ limit: 200, refreshStats: loadStats })
const { items, total, loading, error } = list

async function loadMeta() {
  try {
    const [facetList, options] = await Promise.all([api.getFacets(), api.getEnums()])
    facets.value = facetList
    enums.value = options
  } catch (e) {
    metaError.value = e.message
  }
}

onMounted(() => {
  list.load({ ...filters })
  loadMeta()
  loadStats()
})

let debounce
watch(
  filters,
  () => {
    clearTimeout(debounce)
    debounce = setTimeout(() => list.load({ ...filters }), 250)
  },
  { deep: true },
)
onBeforeUnmount(() => clearTimeout(debounce))

// --------------------------------------------------------------------------- #
// Modales
// --------------------------------------------------------------------------- #
const showForm = ref(false)
const editing = ref(null)
const detail = ref(null)

function openCreate() {
  editing.value = null
  showForm.value = true
}

/**
 * Clic sur une carte : le panneau latéral s'ouvre pour tout le monde
 * (consultation), l'édition restant accessible depuis son bouton « Modifier ».
 */
function openItem(item) {
  detail.value = item
}

/** Depuis le panneau : on ferme la consultation et on ouvre le formulaire. */
function editItem(item) {
  detail.value = null
  editing.value = item
  showForm.value = true
}

// La modale se ferme tout de suite : la mutation locale part avant le serveur.
function onCreate({ payload, files }) {
  showForm.value = false
  list.create(payload, files)
}

function onUpdate({ id, payload }) {
  showForm.value = false
  list.update(id, payload)
}

async function onRemove(item) {
  const accepted = await askConfirm({
    title: 'Supprimer cet objet ?',
    message: `« ${item.name} » et ses photos seront définitivement supprimés.`,
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return
  showForm.value = false
  detail.value = null
  list.remove(item.id)
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <StatsPanel :stats="stats" />

    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Collection
          <span v-if="loading" class="ml-2 text-sm font-normal text-slate-400 dark:text-slate-500">
            chargement…
          </span>
        </h2>
        <span class="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {{ total }}
        </span>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <ViewToggle :model-value="ui.viewMode" @update:model-value="setViewMode" />
        <button
          v-if="canWrite()"
          type="button"
          class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-700"
          @click="openCreate"
        >
          + Nouvel objet
        </button>
        <p v-else class="text-sm text-slate-500 dark:text-slate-400">
          Consultation seule — connectez-vous dans l’administration pour modifier.
        </p>
      </div>
    </div>

    <FilterBar :filters="filters" :facets="facets" :enums="enums" :total="total" />

    <p v-if="error || metaError" class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
      {{ error || metaError }}
    </p>

    <main class="flex-1">
      <!-- Vue grille -->
      <TransitionGroup
        v-if="items.length && ui.viewMode === 'grid'"
        tag="div"
        name="card"
        class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4"
      >
        <div
          v-for="item in items"
          :key="item.id"
          class="relative transition-opacity"
          :class="isPending(`item:${item.id}`) ? 'syncing' : ''"
        >
          <ItemCard :item="item" @edit="openItem" />
          <span
            v-if="item._optimistic"
            class="pointer-events-none absolute right-2 top-2 rounded-full bg-slate-900/70 px-2 py-0.5 text-xs font-medium text-white"
          >
            envoi…
          </span>
          <span
            v-else-if="isPending(`item:${item.id}`)"
            class="pointer-events-none absolute right-2 top-2 h-4 w-4 animate-spin rounded-full border-2 border-white/70 border-t-sky-500"
            title="Synchronisation"
          />
        </div>
      </TransitionGroup>

      <!-- Vue liste -->
      <TransitionGroup
        v-else-if="items.length"
        tag="div"
        name="card"
        class="flex flex-col gap-2"
      >
        <div
          v-for="item in items"
          :key="item.id"
          class="relative transition-opacity"
          :class="isPending(`item:${item.id}`) ? 'syncing' : ''"
        >
          <ItemListRow :item="item" @edit="openItem" />
          <span
            v-if="item._optimistic"
            class="pointer-events-none absolute right-3 top-2 rounded-full bg-slate-900/70 px-2 py-0.5 text-xs font-medium text-white"
          >
            envoi…
          </span>
        </div>
      </TransitionGroup>

      <div
        v-else
        class="rounded-xl border border-dashed border-slate-300 py-20 text-center dark:border-slate-700"
      >
        <p class="text-slate-500 dark:text-slate-400">Aucun objet ne correspond.</p>
        <button
          v-if="canWrite()"
          type="button"
          class="mt-3 text-sm font-medium text-sky-600 hover:underline dark:text-sky-400"
          @click="openCreate"
        >
          Ajouter le premier objet
        </button>
      </div>
    </main>

    <ItemFormModal
      v-if="canWrite()"
      :open="showForm"
      :item="editing"
      :enums="enums"
      @close="showForm = false"
      @create="onCreate"
      @update="onUpdate"
      @remove="onRemove"
    />

    <ItemDetailDrawer
      :open="detail !== null"
      :item="detail"
      :can-edit="canWrite()"
      @close="detail = null"
      @edit="editItem"
    />
  </div>
</template>
