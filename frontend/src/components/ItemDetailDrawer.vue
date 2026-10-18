<script setup>
/**
 * Panneau latéral de consultation d'un objet : photos, détails techniques,
 * historique d'acquisition, notes et tags.
 *
 * Ouvre en lecture seule pour tout le monde ; le bouton « Modifier » n'apparaît
 * que pour les administrateurs.
 */
import { computed, ref, watch } from 'vue'
import { photoUrl } from '../api'
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

watch(
  () => props.open,
  (value) => {
    if (!value) lightboxIndex.value = null
  },
)

const base = computed(() => settings.default_currency)
const foreign = computed(() => Boolean(props.item?.currency && props.item.currency !== base.value))

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
