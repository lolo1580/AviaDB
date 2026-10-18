<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { canWrite } from '../auth'
import { isPending, optimistic } from '../optimistic'
import { confirm as askConfirm } from '../composables/useConfirm'
import { useItemList } from '../composables/useItemList'
import { formatMoney } from '../labels'
import { settings, toBase } from '../settings'
import ItemCard from '../components/ItemCard.vue'
import ItemFormModal from '../components/ItemFormModal.vue'
import ItemDetailDrawer from '../components/ItemDetailDrawer.vue'

const enums = ref(null)
const error = ref('')

const filters = { status: 'WANTED', sort: 'estimated_value', order: 'desc' }

const list = useItemList({ limit: 500 })
const { items, total, loading, error: listError } = list

const budget = computed(() =>
  items.value.reduce((acc, item) => acc + (toBase(item.estimated_value, item.currency) || 0), 0),
)

async function load() {
  await list.load(filters)
  if (!enums.value) {
    try {
      enums.value = await api.getEnums()
    } catch (e) {
      error.value = e.message
    }
  }
}

onMounted(load)

const showForm = ref(false)
const editing = ref(null)
const detail = ref(null)

function openItem(item) {
  detail.value = item
}

function editItem(item) {
  detail.value = null
  editing.value = item
  showForm.value = true
}

// La liste est filtrée sur le statut « Recherché » : toute création y arrive.
function onCreate({ payload, files }) {
  showForm.value = false
  list.create({ ...payload, status: 'WANTED' }, files)
}

function onUpdate({ id, payload }) {
  showForm.value = false
  list.update(id, payload).then(({ ok }) => {
    // L'objet quitte la liste de souhaits s'il n'est plus « Recherché ».
    if (ok && payload.status && payload.status !== 'WANTED') {
      const index = list.indexOf(id)
      if (index !== -1) {
        items.value.splice(index, 1)
        total.value = Math.max(0, total.value - 1)
      }
    }
  })
}

async function onRemove(item) {
  const accepted = await askConfirm({
    title: 'Supprimer cette pièce ?',
    message: `« ${item.name} » sera retiré de la liste de souhaits.`,
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return
  showForm.value = false
  detail.value = null
  list.remove(item.id)
}

/** L'objet entre en collection : il quitte immédiatement la liste de souhaits. */
async function markAcquired(item) {
  const index = list.indexOf(item.id)
  if (index === -1) return
  const [removed] = items.value.splice(index, 1)
  total.value = Math.max(0, total.value - 1)

  await optimistic({
    key: `item:${item.id}`,
    label: 'Passage en collection',
    apply: () => () => {
      items.value.splice(Math.min(index, items.value.length), 0, removed)
      total.value += 1
    },
    request: () => api.updateItem(item.id, { status: 'STORED_BOX' }),
    retry: () => markAcquired(item),
  })
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Liste de souhaits
          <span v-if="loading" class="ml-2 text-sm font-normal text-slate-400 dark:text-slate-500">
            chargement…
          </span>
        </h2>
        <p class="text-sm text-slate-500 dark:text-slate-400">
          {{ total }} pièce(s) recherchée(s) — budget estimé
          {{ formatMoney(budget, settings.default_currency) }}
        </p>
      </div>
      <button
        v-if="canWrite()"
        type="button"
        class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-sky-700"
        @click="editing = null; showForm = true"
      >
        + Ajouter une pièce recherchée
      </button>
    </div>

    <p
      v-if="error || listError"
      class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
    >
      {{ error || listError }}
    </p>

    <TransitionGroup
      v-if="items.length"
      tag="div"
      name="card"
      class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4"
    >
      <div
        v-for="item in items"
        :key="item.id"
        class="flex flex-col gap-2 transition-opacity"
        :class="isPending(`item:${item.id}`) ? 'syncing' : ''"
      >
        <ItemCard :item="item" @edit="openItem" />
        <button
          v-if="canWrite()"
          type="button"
          class="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-400 dark:hover:bg-emerald-950/50"
          @click="markAcquired(item)"
        >
          Marquer comme acquis
        </button>
      </div>
    </TransitionGroup>

    <div
      v-else
      class="rounded-xl border border-dashed border-slate-300 py-20 text-center dark:border-slate-700"
    >
      <p class="text-slate-500 dark:text-slate-400">
        Aucune pièce recherchée. Passez un objet au statut « Recherché » pour le voir ici.
      </p>
    </div>

    <ItemFormModal
      :open="showForm && canWrite()"
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
