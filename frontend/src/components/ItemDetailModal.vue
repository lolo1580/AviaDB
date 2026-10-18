<script setup>
import { computed } from 'vue'
import { photoUrl } from '../api'
import { ATTACHMENT_LABEL, MATERIAL_LABEL, SHAPE_LABEL, STATUS_BADGE, STATUS_LABEL, TYPE_LABEL, formatMoney } from '../labels'
import { settings, toBase } from '../settings'
import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'

const props = defineProps({
  item: { type: Object, default: null },
  open: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'edit'])

const rows = computed(() => {
  const it = props.item
  if (!it) return []
  const baseCurrency = settings.default_currency
  const foreign = it.currency && it.currency !== baseCurrency
  const base = [
    ['Type', TYPE_LABEL[it.item_type]],
    ['Pays', it.country],
    ['Modèle', it.aircraft_model],
    ['Statut', STATUS_LABEL[it.status]],
    ['Emplacement', it.storage_location],
    ['Date d’achat', it.purchase_date],
    [foreign ? `Prix d’achat (${it.currency})` : 'Prix d’achat', formatMoney(it.purchase_price, it.currency)],
    [foreign ? `Valeur estimée (${it.currency})` : 'Valeur estimée', formatMoney(it.estimated_value, it.currency)],
  ]

  if (foreign) {
    const rateNote = it.purchase_rate_date ? ` — taux du ${it.purchase_rate_date}` : ''
    base.push(
      [
        `Prix d’achat en ${baseCurrency}${rateNote}`,
        formatMoney(toBase(it.purchase_eur_value ?? it.purchase_price, 'EUR'), baseCurrency),
      ],
      [`Valeur estimée en ${baseCurrency}`, formatMoney(toBase(it.estimated_value, it.currency), baseCurrency)],
    )
  }

  if (it.item_type === 'DIECAST' && it.diecast) {
    base.push(
      ['Échelle', it.diecast.scale],
      ['Fabricant', it.diecast.manufacturer],
      ['Référence', it.diecast.part_number],
      ['Immatriculation', it.diecast.registration_number],
      ['Configuration', it.diecast.configuration],
    )
  }
  if (it.item_type === 'PATCH' && it.patch) {
    base.push(
      ['Unité / escadron', it.patch.unit_squadron],
      ['Base', it.patch.base],
      ['Événement / mission', it.patch.event_or_mission],
      ['Matière', MATERIAL_LABEL[it.patch.material]],
      ['Fixation', ATTACHMENT_LABEL[it.patch.attachment_type]],
      ['Forme', SHAPE_LABEL[it.patch.shape]],
    )
  }
  base.push(['Notes', it.notes])
  return base.filter(([, value]) => value !== null && value !== undefined && value !== '')
})
</script>

<template>
  <AppModal
    :open="open"
    size="lg"
    :title="item?.name || ''"
    @update:open="$emit('close')"
  >
    <template #header>
      <div class="min-w-0">
        <h2 class="truncate text-lg font-semibold text-slate-900 dark:text-slate-100">{{ item?.name }}</h2>
        <div v-if="item" class="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <span class="rounded px-2 py-0.5 font-semibold ring-1 ring-inset" :class="STATUS_BADGE[item.status]">
            {{ STATUS_LABEL[item.status] }}
          </span>
          <span
            v-for="tag in item.tags"
            :key="tag.id"
            class="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
          >
            {{ tag.name }}
          </span>
        </div>
      </div>
    </template>

    <div v-if="item" class="space-y-5">
      <div v-if="item.photos.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <figure
          v-for="photo in item.photos"
          :key="photo.id"
          class="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800"
        >
          <img :src="photoUrl(photo.thumb_path || photo.file_path)" alt="" class="aspect-square w-full object-cover" />
          <figcaption v-if="photo.caption" class="truncate px-2 py-1 text-xs text-slate-500 dark:text-slate-400">
            {{ photo.caption }}
          </figcaption>
        </figure>
      </div>
      <p
        v-else
        class="rounded-lg bg-slate-50 px-3 py-6 text-center text-sm text-slate-400 dark:bg-slate-800 dark:text-slate-500"
      >
        Aucune photo
      </p>

      <dl class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        <div v-for="[label, value] in rows" :key="label">
          <dt class="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ label }}</dt>
          <dd class="text-sm text-slate-800 dark:text-slate-200">{{ value }}</dd>
        </div>
      </dl>
    </div>

    <template #footer>
      <AppButton variant="secondary" @click="$emit('close')">Fermer</AppButton>
      <AppButton v-if="canEdit" variant="primary" @click="$emit('edit', item)">Modifier</AppButton>
    </template>
  </AppModal>
</template>
