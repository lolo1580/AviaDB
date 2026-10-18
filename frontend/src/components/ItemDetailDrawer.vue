<script setup>
/**
 * Panneau latéral de consultation d'un objet : photos, détails techniques,
 * historique d'acquisition, notes et tags.
 *
 * Ouvre en lecture seule pour tout le monde ; le bouton « Modifier » n'apparaît
 * que pour les administrateurs.
 */
import { computed, reactive, ref, watch } from 'vue'
import { api, photoUrl } from '../api'
import {
  ATTACHMENT_LABEL,
  MATERIAL_LABEL,
  SHAPE_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  TYPE_BADGE,
  TYPE_LABEL,
  formatMoney,
} from '../labels'
import { settings, toBase } from '../settings'
import { classPath } from '../classes'
import { chartSeries, priceSummary } from '../prices'
import { optimistic, tempId, isPending } from '../optimistic'
import { toast } from '../toast'
import PriceChart from './PriceChart.vue'
import AppDrawer from './ui/AppDrawer.vue'
import AppButton from './ui/AppButton.vue'
import PhotoLightbox from './PhotoLightbox.vue'

const props = defineProps({
  item: { type: Object, default: null },
  open: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'edit'])

const lightboxIndex = ref(null)
const error = ref('')

// Formulaires en ligne (liens et relevés de prix)
const linkDraft = reactive({ url: '', label: '' })
const priceDraft = reactive({ price: '', currency: '', recorded_on: '', note: '', source_url: null })
const fetchState = ref({ busy: false, message: '' })

const links = computed(() => props.item?.links || [])
const pricePoints = computed(() => props.item?.price_points || [])
const summary = computed(() => priceSummary(props.item))
const series = computed(() => chartSeries(props.item))
const pendingKey = computed(() => `annotations:${props.item?.id ?? 'none'}`)

watch(
  () => props.open,
  (value) => {
    if (!value) lightboxIndex.value = null
  },
)

const base = computed(() => settings.default_currency)
const foreign = computed(() => Boolean(props.item?.currency && props.item.currency !== base.value))
const classLabel = computed(() => classPath(props.item?.class_id))

/** Détails techniques, selon le type d'objet. */
const technical = computed(() => {
  const it = props.item
  if (!it) return []
  if (it.item_type === 'DIECAST' && it.diecast) {
    const d = it.diecast
    return [
      ['Échelle', d.scale],
      ['Fabricant', d.manufacturer],
      ['Référence', d.part_number],
      ['Immatriculation réelle', d.registration_number],
      ['Configuration', d.configuration],
    ].filter(([, value]) => value)
  }
  if (it.item_type === 'PATCH' && it.patch) {
    const p = it.patch
    return [
      ['Unité / escadron', p.unit_squadron],
      ['Base', p.base],
      ['Événement / mission', p.event_or_mission],
      ['Matière', MATERIAL_LABEL[p.material]],
      ['Fixation', ATTACHMENT_LABEL[p.attachment_type]],
      ['Forme', SHAPE_LABEL[p.shape]],
    ].filter(([, value]) => value)
  }
  return []
})

/** Historique d'acquisition et suivi. */
const history = computed(() => {
  const it = props.item
  if (!it) return []
  const rows = [['Date d’achat', it.purchase_date]]

  if (it.purchase_price != null) {
    rows.push([
      foreign.value ? `Prix d’achat (${it.currency})` : 'Prix d’achat',
      formatMoney(it.purchase_price, it.currency),
    ])
    if (foreign.value) {
      const note = it.purchase_rate_date ? ` — taux du ${it.purchase_rate_date}` : ' — taux actuel'
      rows.push([
        `Équivalent en ${base.value}${note}`,
        formatMoney(toBase(it.purchase_eur_value ?? it.purchase_price, 'EUR'), base.value),
      ])
    }
  }

  if (it.estimated_value != null) {
    rows.push([
      foreign.value ? `Valeur estimée (${it.currency})` : 'Valeur estimée',
      formatMoney(it.estimated_value, it.currency),
    ])
    if (foreign.value) {
      rows.push([
        `Équivalent en ${base.value}`,
        formatMoney(toBase(it.estimated_value, it.currency), base.value),
      ])
    }
  }

  rows.push(['Emplacement', it.storage_location])
  if (it.loaned_to) {
    rows.push(
      ['Prêté à', it.loaned_to],
      ['Prêt depuis le', it.loan_date],
      ['Retour prévu le', it.loan_due_date],
    )
  }
  if (it.created_at) {
    rows.push(['Ajouté le', new Date(it.created_at).toLocaleDateString('fr-FR')])
  }
  if (it.updated_at) {
    rows.push(['Modifié le', new Date(it.updated_at).toLocaleDateString('fr-FR')])
  }
  return rows.filter(([, value]) => value !== null && value !== undefined && value !== '')
})

const cell = 'text-sm'
const inputClass =
  'w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm shadow-sm outline-none focus:border-sky-500 dark:border-slate-700'
const linkAction = 'text-xs text-slate-400 transition hover:text-slate-600 dark:hover:text-slate-200'
const linkDanger = 'text-xs text-rose-500 transition hover:text-rose-700 dark:hover:text-rose-400'

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/* eslint-disable no-param-reassign -- la liste appartient au parent, on la met
   à jour localement puis on restaure en cas d'échec (comme pour les photos). */

async function addLink() {
  const url = linkDraft.url.trim()
  if (!url || !props.item) return

  const placeholder = { id: tempId('link'), url, label: linkDraft.label.trim() || null }
  links.value.push(placeholder)
  linkDraft.url = ''
  linkDraft.label = ''

  await optimistic({
    key: pendingKey.value,
    label: 'Ajout du lien',
    apply: () => () => {
      const index = links.value.findIndex((entry) => entry.id === placeholder.id)
      if (index !== -1) links.value.splice(index, 1)
    },
    request: () => api.addLink(props.item.id, { url, label: placeholder.label }),
    onSuccess: (created) => {
      const index = links.value.findIndex((entry) => entry.id === placeholder.id)
      if (index !== -1) links.value.splice(index, 1, created)
    },
  })
}

async function removeLink(link) {
  const index = links.value.findIndex((entry) => entry.id === link.id)
  if (index === -1) return
  const [removed] = links.value.splice(index, 1)

  await optimistic({
    key: pendingKey.value,
    label: 'Suppression du lien',
    apply: () => () => {
      links.value.splice(index, 0, removed)
    },
    request: () => api.deleteLink(link.id),
  })
}

function insertPoint(point) {
  const points = pricePoints.value
  const at = points.findIndex((entry) => entry.recorded_on > point.recorded_on)
  if (at === -1) points.push(point)
  else points.splice(at, 0, point)
}

async function addPrice() {
  if (!props.item) return
  const amount = Number(String(priceDraft.price).replace(',', '.'))
  if (!amount || amount <= 0) {
    error.value = 'Montant invalide'
    return
  }
  error.value = ''

  const currency = (priceDraft.currency || props.item.currency || settings.default_currency).toUpperCase()
  const recorded = priceDraft.recorded_on || new Date().toISOString().slice(0, 10)
  const placeholder = {
    id: tempId('price'),
    price: amount,
    currency,
    eur_value: toBase(amount, currency),
    recorded_on: recorded,
    source_url: priceDraft.source_url,
    note: priceDraft.note.trim() || null,
    _optimistic: true,
  }
  insertPoint(placeholder)
  Object.assign(priceDraft, { price: '', recorded_on: '', note: '', source_url: null })

  await optimistic({
    key: pendingKey.value,
    label: 'Enregistrement du relevé',
    apply: () => () => {
      const index = pricePoints.value.findIndex((entry) => entry.id === placeholder.id)
      if (index !== -1) pricePoints.value.splice(index, 1)
    },
    request: () => api.addPrice(props.item.id, {
      price: amount,
      currency,
      recorded_on: recorded,
      source_url: placeholder.source_url,
      note: placeholder.note,
    }),
    onSuccess: (created) => {
      const index = pricePoints.value.findIndex((entry) => entry.id === placeholder.id)
      if (index !== -1) pricePoints.value.splice(index, 1)
      insertPoint(created)
    },
  })
}

async function removePrice(point) {
  const index = pricePoints.value.findIndex((entry) => entry.id === point.id)
  if (index === -1) return
  const [removed] = pricePoints.value.splice(index, 1)

  await optimistic({
    key: pendingKey.value,
    label: 'Suppression du relevé',
    apply: () => () => {
      pricePoints.value.splice(index, 0, removed)
    },
    request: () => api.deletePrice(point.id),
  })
}

/** Lit le prix sur la page du lien et le propose — sans jamais l'enregistrer. */
async function recoverPrice(link) {
  fetchState.value = { busy: true, message: '' }
  try {
    const found = await api.fetchPrice(link.url)
    priceDraft.price = String(found.price).replace('.', ',')
    if (found.currency) priceDraft.currency = found.currency
    priceDraft.recorded_on = new Date().toISOString().slice(0, 10)
    priceDraft.source_url = link.url
    priceDraft.note = found.title ? `relevé sur ${hostOf(link.url)}` : null
    fetchState.value = {
      busy: false,
      message: `Prix lu (${found.strategy}) : ${found.price} ${found.currency || ''}`.trim(),
    }
    toast.info('Prix relevé : vérifiez puis validez')
  } catch (e) {
    fetchState.value = { busy: false, message: e.message }
  }
}

/* eslint-enable no-param-reassign */
</script>

<template>
  <AppDrawer
    :open="open"
    size="lg"
    title=""
    :subtitle="item ? `${TYPE_LABEL[item.item_type]} · ${item.country || 'pays non renseigné'}` : ''"
    @update:open="$emit('close')"
  >
    <template #header="{ titleId, descriptionId }">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded px-2 py-0.5 text-xs font-semibold ring-1 ring-inset" :class="TYPE_BADGE[item?.item_type]">
            {{ TYPE_LABEL[item?.item_type] }}
          </span>
          <span class="rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset" :class="STATUS_BADGE[item?.status]">
            {{ STATUS_LABEL[item?.status] }}
          </span>
        </div>
        <h2 :id="titleId" class="mt-1.5 text-lg font-semibold text-slate-900 dark:text-slate-100">
          {{ item?.name }}
        </h2>
        <p :id="descriptionId" class="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
          {{ item?.aircraft_model || 'Modèle non renseigné' }}
        </p>
      </div>
    </template>

    <div v-if="item" class="flex flex-col gap-6">
      <!-- Photos -->
      <section>
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Photos ({{ item.photos.length }})
        </h3>
        <div v-if="item.photos.length" class="mt-2 grid grid-cols-3 gap-2">
          <button
            v-for="(photo, index) in item.photos"
            :key="photo.id"
            type="button"
            class="group relative overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800"
            :title="photo.caption || 'Agrandir'"
            @click="lightboxIndex = index"
          >
            <img :src="photoUrl(photo.thumb_path || photo.file_path)" :alt="photo.caption || ''" class="aspect-square w-full object-cover transition group-hover:scale-105" />
            <span
              v-if="photo.is_primary"
              class="absolute left-1 top-1 rounded bg-emerald-600/90 px-1.5 py-0.5 text-[0.6rem] font-semibold text-white"
            >
              couverture
            </span>
          </button>
        </div>
        <p v-else class="mt-2 rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-400 dark:bg-slate-800/60 dark:text-slate-500">
          Aucune photo
        </p>
      </section>

      <!-- Détails techniques -->
      <section>
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Détails techniques
        </h3>
        <dl v-if="technical.length" class="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          <div v-for="[label, value] in technical" :key="label" class="flex gap-4 py-2">
            <dt class="w-40 shrink-0 text-sm text-slate-500 dark:text-slate-400">{{ label }}</dt>
            <dd :class="[cell, 'text-slate-800 dark:text-slate-200']">{{ value }}</dd>
          </div>
        </dl>
        <p v-else class="mt-2 text-sm text-slate-400 dark:text-slate-500">
          Aucun détail technique renseigné.
        </p>
      </section>

      <!-- Historique & acquisition -->
      <section>
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Historique &amp; acquisition
        </h3>
        <dl v-if="history.length" class="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          <div v-for="[label, value] in history" :key="label" class="flex gap-4 py-2">
            <dt class="w-40 shrink-0 text-sm text-slate-500 dark:text-slate-400">{{ label }}</dt>
            <dd :class="[cell, 'text-slate-800 dark:text-slate-200']">{{ value }}</dd>
          </div>
        </dl>
        <p v-else class="mt-2 text-sm text-slate-400 dark:text-slate-500">
          Aucune information d’acquisition.
        </p>
      </section>

      <!-- Liens externes -->
      <section>
        <div class="flex items-center justify-between">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Liens ({{ links.length }})
          </h3>
          <span
            v-if="isPending(pendingKey)"
            class="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-sky-500 dark:border-slate-700 dark:border-t-sky-400"
          />
        </div>

        <ul v-if="links.length" class="mt-2 space-y-1">
          <li
            v-for="link in links"
            :key="link.id"
            class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800"
          >
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm text-slate-800 dark:text-slate-200">
                {{ link.label || hostOf(link.url) }}
              </p>
              <a
                :href="link.url"
                target="_blank"
                rel="noopener noreferrer"
                class="block truncate text-xs text-sky-600 hover:underline dark:text-sky-400"
              >{{ link.url }}</a>
            </div>
            <button
              v-if="canEdit"
              type="button"
              class="shrink-0 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              :disabled="fetchState.busy"
              title="Lire le prix sur cette page"
              @click="recoverPrice(link)"
            >
              Récupérer le prix
            </button>
            <button v-if="canEdit" type="button" :class="linkDanger" title="Supprimer" @click="removeLink(link)">
              ✕
            </button>
          </li>
        </ul>
        <p v-else class="mt-2 text-sm text-slate-400 dark:text-slate-500">Aucun lien enregistré.</p>

        <form v-if="canEdit" class="mt-2 flex flex-wrap items-center gap-2" @submit.prevent="addLink">
          <input v-model="linkDraft.url" placeholder="https://boutique.fr/rafale" :class="[inputClass, 'min-w-48 flex-1']" />
          <input v-model="linkDraft.label" placeholder="Libellé (facultatif)" :class="[inputClass, 'w-40']" />
          <AppButton type="submit" variant="secondary" size="sm" :disabled="!linkDraft.url.trim()">Ajouter</AppButton>
        </form>
      </section>

      <!-- Suivi du prix -->
      <section>
        <div class="flex items-center justify-between">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Suivi du prix ({{ pricePoints.length }})
          </h3>
          <p v-if="summary" class="text-xs text-slate-500 dark:text-slate-400">
            {{ summary.label }}
            <span
              v-if="summary.trend"
              class="ml-1 font-semibold"
              :class="{
                'text-emerald-600 dark:text-emerald-400': summary.trend === 'down',
                'text-rose-600 dark:text-rose-400': summary.trend === 'up',
                'text-slate-400': summary.trend === 'flat',
              }"
            >
              {{ summary.trend === 'down' ? '▼' : summary.trend === 'up' ? '▲' : '=' }}
              {{ Math.abs(summary.variation).toFixed(0) }} %
            </span>
          </p>
        </div>

        <PriceChart class="mt-2" :series="series" :currency="settings.default_currency" />

        <ul v-if="pricePoints.length" class="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          <li
            v-for="point in pricePoints"
            :key="point.id"
            class="flex flex-wrap items-center gap-2 py-1.5 text-sm text-slate-700 dark:text-slate-300"
          >
            <span class="w-24 shrink-0 text-xs text-slate-500 dark:text-slate-400">{{ point.recorded_on }}</span>
            <span class="font-medium">{{ formatMoney(point.price, point.currency) }}</span>
            <span v-if="point.note" class="truncate text-xs text-slate-400 dark:text-slate-500">{{ point.note }}</span>
            <button v-if="canEdit" type="button" :class="[linkDanger, 'ml-auto']" @click="removePrice(point)">✕</button>
          </li>
        </ul>

        <form v-if="canEdit" class="mt-2 space-y-2" @submit.prevent="addPrice">
          <div class="flex flex-wrap items-center gap-2">
            <input
              v-model="priceDraft.price"
              type="text"
              inputmode="decimal"
              placeholder="Montant"
              :class="[inputClass, 'w-28']"
            />
            <select v-model="priceDraft.currency" :class="[inputClass, 'w-28']">
              <option value="">{{ item?.currency || settings.default_currency }}</option>
              <option v-for="option in settings.currencies" :key="option.code" :value="option.code">
                {{ option.code }}
              </option>
            </select>
            <input v-model="priceDraft.recorded_on" type="date" :class="[inputClass, 'w-40']" />
            <input v-model="priceDraft.note" placeholder="Note (facultatif)" :class="[inputClass, 'min-w-32 flex-1']" />
            <AppButton type="submit" variant="secondary" size="sm" :disabled="!priceDraft.price">Relever</AppButton>
          </div>
          <p v-if="fetchState.busy" class="text-xs text-slate-400 dark:text-slate-500">Lecture de la page…</p>
          <p v-else-if="fetchState.message" class="text-xs text-slate-500 dark:text-slate-400">
            {{ fetchState.message }}
          </p>
        </form>
        <p v-else-if="!pricePoints.length" class="mt-2 text-sm text-slate-400 dark:text-slate-500">
          Aucun relevé de prix.
        </p>
      </section>

      <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
        {{ error }}
      </p>

      <!-- Classification -->
      <section>
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Classification
        </h3>
        <p v-if="classLabel" class="mt-2 text-sm text-slate-800 dark:text-slate-200">{{ classLabel }}</p>
        <p v-else class="mt-2 text-sm text-slate-400 dark:text-slate-500">Aucune classe attribuée.</p>
      </section>

      <!-- Notes -->
      <section>
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Notes</h3>
        <p
          v-if="item.notes"
          class="mt-2 whitespace-pre-line rounded-lg bg-slate-50 px-3 py-2 text-sm leading-relaxed text-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
        >
          {{ item.notes }}
        </p>
        <p v-else class="mt-2 text-sm text-slate-400 dark:text-slate-500">Aucune note.</p>
      </section>

      <!-- Tags -->
      <section v-if="item.tags.length">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Tags</h3>
        <ul class="mt-2 flex flex-wrap gap-1.5">
          <li
            v-for="tag in item.tags"
            :key="tag.id"
            class="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
          >
            {{ tag.name }}
          </li>
        </ul>
      </section>
    </div>

    <template #footer>
      <AppButton variant="secondary" @click="$emit('close')">Fermer</AppButton>
      <AppButton v-if="canEdit" variant="primary" @click="$emit('edit', item)">Modifier</AppButton>
    </template>

    <PhotoLightbox
      :photos="item?.photos || []"
      :open="lightboxIndex !== null"
      :start-index="lightboxIndex ?? 0"
      @close="lightboxIndex = null"
    />
  </AppDrawer>
</template>
