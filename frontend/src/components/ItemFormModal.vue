<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { api, photoUrl } from '../api'
import { isPending, optimistic, tempId } from '../optimistic'
import { confirm as askConfirm } from '../composables/useConfirm'
import { prompt as askPrompt } from '../composables/usePrompt'
import { ATTACHMENT_LABEL, MATERIAL_LABEL, SHAPE_LABEL, STATUS_LABEL, TYPE_LABEL } from '../labels'
import { settings } from '../settings'
import { flattenedClasses } from '../classes'
import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'
import PhotoLightbox from './PhotoLightbox.vue'

const props = defineProps({
  item: { type: Object, default: null },
  enums: { type: Object, default: null },
  open: { type: Boolean, default: false },
  /** 'default' (collection) ou 'wishlist' (pièce recherchée : champs adaptés). */
  mode: { type: String, default: 'default' },
})
const emit = defineEmits(['close', 'create', 'update', 'remove'])

const isEdit = computed(() => Boolean(props.item?.id))
const isWishlist = computed(() => props.mode === 'wishlist')

// Liens : brouillons sur un objet à créer, appels immédiats en modification.
const linkDraft = reactive({ url: '', label: '' })
const pendingLinks = ref([])
const links = ref([])
const formId = `item-form-${Math.random().toString(36).slice(2, 7)}`

const error = ref('')
const photos = ref([])
const pendingFiles = ref([])
const lightboxIndex = ref(null)

const form = reactive({
  name: '',
  item_type: 'DIECAST',
  country: '',
  aircraft_model: '',
  storage_location: '',
  status: 'STORED_BOX',
  purchase_date: '',
  purchase_price: '',
  estimated_value: '',
  notes: '',
  tags: '',
  currency: '',
  class_id: '',
  preorder_release_date: '',
  preorder_shop: '',
  preorder_deposit: '',
  diecast: { scale: '', manufacturer: '', part_number: '', registration_number: '', configuration: '' },
  patch: { unit_squadron: '', base: '', material: '', attachment_type: '', shape: '', event_or_mission: '' },
})

const dragIndex = ref(null)
const photoKey = computed(() => `photos:${props.item?.id ?? 'new'}`)

function nullify(obj) {
  return Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, v === '' ? null : v]))
}

function toNum(value) {
  if (value === '' || value === null || value === undefined) return null
  const n = Number(value)
  return Number.isNaN(n) ? null : n
}

const classOptions = computed(() => flattenedClasses())

/** Intitulés adaptés au mode (collection ou pièce recherchée). */
const titre = computed(() => {
  if (isWishlist.value) return isEdit.value ? 'Modifier la pièce recherchée' : 'Nouvelle pièce recherchée'
  return isEdit.value ? 'Modifier l’objet' : 'Nouvel objet'
})

const sousTitre = computed(() =>
  isWishlist.value
    ? 'Ce que vous cherchez : les champs d’acquisition viendront une fois la pièce trouvée.'
    : 'Renseignez la fiche : les détails changent selon le type.',
)

const currencyOptions = computed(() =>
  settings.currencies.length
    ? settings.currencies
    : [
        { code: 'EUR', label: 'Euro' },
        { code: 'USD', label: 'Dollar américain' },
        { code: 'GBP', label: 'Livre sterling' },
        { code: 'CHF', label: 'Franc suisse' },
      ],
)

/** Réinitialise le formulaire à chaque ouverture (la modale reste montée). */
async function initialize() {
  error.value = ''
  pendingFiles.value = []
  pendingLinks.value = []
  links.value = []
  lightboxIndex.value = null
  photos.value = []

  Object.assign(form, {
    name: '',
    item_type: 'DIECAST',
    country: '',
    aircraft_model: '',
    storage_location: '',
    status: 'STORED_BOX',
    purchase_date: '',
    purchase_price: '',
    estimated_value: '',
    notes: '',
    tags: '',
    currency: settings.default_currency,
    class_id: '',
    preorder_release_date: '',
    preorder_shop: '',
    preorder_deposit: '',
    diecast: { scale: '', manufacturer: '', part_number: '', registration_number: '', configuration: '' },
    patch: { unit_squadron: '', base: '', material: '', attachment_type: '', shape: '', event_or_mission: '' },
  })

  const it = props.item
  if (!it) return

  Object.assign(form, {
    name: it.name ?? '',
    item_type: it.item_type ?? 'DIECAST',
    country: it.country ?? '',
    aircraft_model: it.aircraft_model ?? '',
    storage_location: it.storage_location ?? '',
    status: it.status ?? 'STORED_BOX',
    purchase_date: it.purchase_date ?? '',
    purchase_price: it.purchase_price ?? '',
    estimated_value: it.estimated_value ?? '',
    notes: it.notes ?? '',
    tags: (it.tags || []).map((tag) => tag.name).join(', '),
    currency: it.currency ?? settings.default_currency,
    class_id: it.class_id ?? '',
    preorder_release_date: it.preorder_release_date ?? '',
    preorder_shop: it.preorder_shop ?? '',
    preorder_deposit: it.preorder_deposit ?? '',
  })
  if (it.diecast) Object.assign(form.diecast, it.diecast)
  if (it.patch) Object.assign(form.patch, it.patch)

  links.value = it.links ? [...it.links] : []

  if (isEdit.value) {
    try {
      photos.value = await api.listPhotos(it.id)
    } catch (e) {
      error.value = e.message
    }
  }
}

watch(
  () => [props.open, props.item?.id],
  ([open]) => {
    if (open) initialize()
  },
  { immediate: true },
)

function buildPayload() {
  const preorder = !isWishlist.value && form.status === 'PREORDER'
  const payload = {
    name: form.name.trim(),
    item_type: form.item_type,
    country: form.country || null,
    aircraft_model: form.aircraft_model || null,
    storage_location: isWishlist.value ? null : form.storage_location || null,
    // Une pièce recherchée reste « Recherché » : le statut n'est pas éditable ici.
    status: isWishlist.value ? 'WANTED' : form.status,
    purchase_date: isWishlist.value ? null : form.purchase_date || null,
    purchase_price: isWishlist.value ? null : toNum(form.purchase_price),
    estimated_value: toNum(form.estimated_value),
    preorder_release_date: preorder ? form.preorder_release_date || null : null,
    preorder_shop: preorder ? form.preorder_shop || null : null,
    preorder_deposit: preorder ? toNum(form.preorder_deposit) : null,
    currency: form.currency || settings.default_currency,
    class_id: form.class_id === '' || form.class_id === null ? null : Number(form.class_id),
    notes: form.notes || null,
    tags: form.tags.split(',').map((s) => s.trim()).filter(Boolean),
    diecast: null,
    patch: null,
  }
  if (form.item_type === 'DIECAST') payload.diecast = nullify(form.diecast)
  if (form.item_type === 'PATCH') payload.patch = nullify(form.patch)
  return payload
}

/**
 * Validation locale immédiate puis délégation au parent : la modale se ferme
 * aussitôt et l'objet apparaît dans la liste pendant que le serveur travaille.
 */
function submit() {
  if (!form.name.trim()) {
    error.value = 'Le nom est obligatoire'
    return
  }
  // Contrôle en français (le formulaire est en `novalidate` : on ne laisse pas
  // la validation native du navigateur afficher son propre message).
  const year = Number(String(form.purchase_date).slice(0, 4))
  if (form.purchase_date && !(year >= 1900 && year <= 2100)) {
    error.value = 'Date d’achat invalide : l’année doit être comprise entre 1900 et 2100.'
    return
  }
  error.value = ''
  const payload = buildPayload()
  if (isEdit.value) emit('update', { id: props.item.id, payload })
  else emit('create', { payload, files: [...pendingFiles.value], links: [...pendingLinks.value] })
}

// --------------------------------------------------------------------------- #
// Photos — mutations optimistes (l'objet existe déjà en mode édition)
// --------------------------------------------------------------------------- #
function onFilesSelected(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  if (isEdit.value) files.forEach((file) => uploadNow(file))
  else pendingFiles.value.push(...files)
}

async function uploadNow(file) {
  const placeholder = {
    id: tempId('photo'),
    file_path: '',
    thumb_path: null,
    caption: '',
    is_primary: false,
    _uploading: true,
    _preview: URL.createObjectURL(file),
  }
  photos.value = [...photos.value, placeholder]

  await optimistic({
    key: photoKey.value,
    label: 'Envoi de la photo',
    apply: () => () => {
      URL.revokeObjectURL(placeholder._preview)
      photos.value = photos.value.filter((entry) => entry.id !== placeholder.id)
    },
    request: () => api.uploadPhoto(props.item.id, file),
    onSuccess: (photo) => {
      URL.revokeObjectURL(placeholder._preview)
      photos.value = photos.value.map((entry) => (entry.id === placeholder.id ? photo : entry))
    },
  })
}

async function setPrimary(photo) {
  const before = photos.value.map((entry) => ({ id: entry.id, is_primary: entry.is_primary }))
  photos.value = photos.value.map((entry) => ({ ...entry, is_primary: entry.id === photo.id }))

  await optimistic({
    key: photoKey.value,
    label: 'Photo de couverture',
    apply: () => () => {
      photos.value = photos.value.map((entry) => ({
        ...entry,
        is_primary: before.find((snapshot) => snapshot.id === entry.id)?.is_primary ?? false,
      }))
    },
    request: () => api.setPrimaryPhoto(photo.id),
  })
}

async function editCaption(photo) {
  const caption = await askPrompt({
    title: 'Légende de la photo',
    label: 'Légende',
    value: photo.caption || '',
    placeholder: 'Gros plan dérive, dos velcro…',
    multiline: true,
    required: false,
    maxLength: 255,
    confirmLabel: 'Enregistrer',
  })
  if (caption === null) return
  const before = photo.caption
  photos.value = photos.value.map((entry) => (entry.id === photo.id ? { ...entry, caption } : entry))

  await optimistic({
    key: photoKey.value,
    label: 'Légende',
    apply: () => () => {
      photos.value = photos.value.map((entry) =>
        entry.id === photo.id ? { ...entry, caption: before } : entry,
      )
    },
    request: () => api.updatePhoto(photo.id, { caption }),
  })
}

async function removePhoto(photo) {
  const accepted = await askConfirm({
    title: 'Supprimer cette photo ?',
    message: 'Le fichier image sera définitivement effacé.',
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return

  const snapshot = [...photos.value]
  const remaining = photos.value.filter((entry) => entry.id !== photo.id)
  if (photo.is_primary && remaining.length) {
    remaining[0] = { ...remaining[0], is_primary: true }
  }
  photos.value = remaining

  await optimistic({
    key: photoKey.value,
    label: 'Suppression de la photo',
    apply: () => () => {
      photos.value = snapshot
    },
    request: () => api.deletePhoto(photo.id),
  })
}

function onDragStart(index) {
  dragIndex.value = index
}

function onDrop(index) {
  const from = dragIndex.value
  dragIndex.value = null
  move(from, index)
}

async function move(from, to) {
  if (from === null || to === null || from === to || to < 0 || to >= photos.value.length) return
  const before = [...photos.value]
  const next = [...photos.value]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  photos.value = next

  await optimistic({
    key: photoKey.value,
    label: 'Réordonnancement',
    apply: () => () => {
      photos.value = before
    },
    request: () => api.reorderPhotos(props.item.id, next.map((entry) => entry.id)),
    onSuccess: (updated) => {
      photos.value = updated
    },
  })
}

async function addLink() {
  const url = linkDraft.url.trim()
  if (!url) return
  const label = linkDraft.label.trim() || null
  linkDraft.url = ''
  linkDraft.label = ''

  if (!isEdit.value) {
    pendingLinks.value.push({ url, label })
    return
  }

  const placeholder = { id: tempId('link'), url, label }
  links.value.push(placeholder)
  await optimistic({
    key: `links:${props.item.id}`,
    label: 'Ajout du lien',
    apply: () => () => {
      const index = links.value.findIndex((entry) => entry.id === placeholder.id)
      if (index !== -1) links.value.splice(index, 1)
    },
    request: () => api.addLink(props.item.id, { url, label }),
    onSuccess: (created) => {
      const index = links.value.findIndex((entry) => entry.id === placeholder.id)
      if (index !== -1) links.value.splice(index, 1, created)
    },
  })
}

async function removeLink(link) {
  if (!isEdit.value) {
    pendingLinks.value = pendingLinks.value.filter((entry) => entry !== link)
    return
  }
  const index = links.value.findIndex((entry) => entry.id === link.id)
  if (index === -1) return
  const [removed] = links.value.splice(index, 1)
  await optimistic({
    key: `links:${props.item.id}`,
    label: 'Suppression du lien',
    apply: () => () => {
      links.value.splice(index, 0, removed)
    },
    request: () => api.deleteLink(link.id),
  })
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function photoSource(photo) {
  if (photo._preview) return photo._preview
  return photoUrl(photo.thumb_path || photo.file_path)
}

const inputClass =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-200 dark:border-slate-700 dark:focus:ring-sky-900'
const labelClass = 'text-xs font-medium text-slate-500 dark:text-slate-400'
const linkDanger = 'text-rose-600 hover:underline dark:text-rose-400'
</script>

<template>
  <AppModal
    :open="open"
    size="lg"
    :title="titre"
    :subtitle="sousTitre"
    @update:open="$emit('close')"
  >
    <form :id="formId" novalidate class="space-y-6" @submit.prevent="submit">
      <!-- Socle commun -->
      <div class="grid gap-4 sm:grid-cols-2">
        <label class="sm:col-span-2 flex flex-col gap-1">
          <span :class="labelClass">Nom *</span>
          <input v-model="form.name" required :class="inputClass" placeholder="Rafale M 11F Tiger Meet 2024" />
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">Type *</span>
          <select v-model="form.item_type" :class="inputClass">
            <option v-for="t in enums?.item_types || ['DIECAST', 'PATCH', 'OTHER']" :key="t" :value="t">
              {{ TYPE_LABEL[t] }}
            </option>
          </select>
        </label>

        <label v-if="!isWishlist" class="flex flex-col gap-1">
          <span :class="labelClass">Statut</span>
          <select v-model="form.status" :class="inputClass">
            <option v-for="s in enums?.statuses || []" :key="s" :value="s">{{ STATUS_LABEL[s] }}</option>
          </select>
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">Pays</span>
          <input v-model="form.country" :class="inputClass" placeholder="France" />
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">Modèle d’aéronef</span>
          <input v-model="form.aircraft_model" :class="inputClass" placeholder="Rafale M" />
        </label>

        <label v-if="!isWishlist" class="flex flex-col gap-1">
          <span :class="labelClass">Emplacement</span>
          <input v-model="form.storage_location" :class="inputClass" placeholder="Vitrine Salon Étage 2" />
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">Tags (séparés par des virgules)</span>
          <input v-model="form.tags" :class="inputClass" placeholder="Tiger Meet, Marine" />
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">Classe</span>
          <select v-model="form.class_id" :class="inputClass">
            <option value="">— Aucune —</option>
            <option v-for="node in classOptions" :key="node.id" :value="node.id">
              {{ '— '.repeat(node.depth) }}{{ node.name }}
            </option>
          </select>
        </label>

        <label v-if="!isWishlist" class="flex flex-col gap-1">
          <span :class="labelClass">Date d’achat</span>
          <input
            v-model="form.purchase_date"
            type="date"
            min="1900-01-01"
            max="2100-12-31"
            :class="inputClass"
          />
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">Devise</span>
          <select v-model="form.currency" :class="inputClass">
            <option v-for="option in currencyOptions" :key="option.code" :value="option.code">
              {{ option.code }} — {{ option.label }}
            </option>
          </select>
        </label>

        <label v-if="!isWishlist" class="flex flex-col gap-1">
          <span :class="labelClass">Prix d’achat ({{ form.currency }})</span>
          <input v-model="form.purchase_price" type="number" min="0" step="0.01" :class="inputClass" />
        </label>

        <label class="flex flex-col gap-1">
          <span :class="labelClass">
            {{ isWishlist ? `Budget visé (${form.currency})` : `Valeur estimée (${form.currency})` }}
          </span>
          <input v-model="form.estimated_value" type="number" min="0" step="0.01" :class="inputClass" />
        </label>

        <label class="sm:col-span-2 flex flex-col gap-1">
          <span :class="labelClass">Notes</span>
          <textarea v-model="form.notes" rows="2" :class="inputClass" />
        </label>
      </div>

      <!-- Précommande : commandée mais pas encore reçue -->
      <section
        v-if="!isWishlist && form.status === 'PREORDER'"
        class="rounded-xl border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-900 dark:bg-amber-950/30"
      >
        <h3 class="text-sm font-semibold text-amber-800 dark:text-amber-300">Précommande</h3>
        <p class="mt-1 text-xs text-amber-700/80 dark:text-amber-400/80">
          La pièce n’est pas encore en votre possession : elle est exclue de la valeur estimée de
          la collection.
        </p>
        <div class="mt-3 grid gap-4 sm:grid-cols-3">
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Sortie prévue</span>
            <input
              v-model="form.preorder_release_date"
              type="date"
              min="1900-01-01"
              max="2100-12-31"
              :class="inputClass"
            />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Boutique / fournisseur</span>
            <input v-model="form.preorder_shop" :class="inputClass" placeholder="Boutique, revendeur…" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Acompte versé ({{ form.currency }})</span>
            <input v-model="form.preorder_deposit" type="number" min="0" step="0.01" :class="inputClass" />
          </label>
        </div>
      </section>

      <!-- Détails dynamiques selon le type -->
      <fieldset
        v-if="form.item_type === 'DIECAST'"
        class="rounded-xl border border-sky-200 bg-sky-50/50 p-4 dark:border-sky-900 dark:bg-sky-950/30"
      >
        <legend class="px-1 text-sm font-semibold text-sky-800 dark:text-sky-300">Détails maquette</legend>
        <div class="mt-2 grid gap-4 sm:grid-cols-3">
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Échelle</span>
            <input v-model="form.diecast.scale" :class="inputClass" placeholder="1/72" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Fabricant</span>
            <input v-model="form.diecast.manufacturer" :class="inputClass" placeholder="Hobby Master" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Référence</span>
            <input v-model="form.diecast.part_number" :class="inputClass" placeholder="HA6501" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Immatriculation réelle</span>
            <input v-model="form.diecast.registration_number" :class="inputClass" placeholder="11" />
          </label>
          <label class="sm:col-span-2 flex flex-col gap-1">
            <span :class="labelClass">Configuration</span>
            <input
              v-model="form.diecast.configuration"
              :class="inputClass"
              placeholder="Train sorti, réservoirs d'ailes"
            />
          </label>
        </div>
      </fieldset>

      <fieldset
        v-else-if="form.item_type === 'PATCH'"
        class="rounded-xl border border-violet-200 bg-violet-50/50 p-4 dark:border-violet-900 dark:bg-violet-950/30"
      >
        <legend class="px-1 text-sm font-semibold text-violet-800 dark:text-violet-300">Détails patch</legend>
        <div class="mt-2 grid gap-4 sm:grid-cols-3">
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Unité / escadron</span>
            <input v-model="form.patch.unit_squadron" :class="inputClass" placeholder="Flottille 11F" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Base</span>
            <input v-model="form.patch.base" :class="inputClass" placeholder="BAN Landivisiau" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Événement / mission</span>
            <input v-model="form.patch.event_or_mission" :class="inputClass" placeholder="NATO Tiger Meet 2024" />
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Matière</span>
            <select v-model="form.patch.material" :class="inputClass">
              <option value="">—</option>
              <option v-for="m in enums?.materials || []" :key="m" :value="m">{{ MATERIAL_LABEL[m] }}</option>
            </select>
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Fixation</span>
            <select v-model="form.patch.attachment_type" :class="inputClass">
              <option value="">—</option>
              <option v-for="a in enums?.attachment_types || []" :key="a" :value="a">
                {{ ATTACHMENT_LABEL[a] }}
              </option>
            </select>
          </label>
          <label class="flex flex-col gap-1">
            <span :class="labelClass">Forme</span>
            <select v-model="form.patch.shape" :class="inputClass">
              <option value="">—</option>
              <option v-for="s in enums?.shapes || []" :key="s" :value="s">{{ SHAPE_LABEL[s] }}</option>
            </select>
          </label>
        </div>
      </fieldset>

      <!-- Liens (une pièce recherchée vit souvent sur plusieurs boutiques) -->
      <section v-if="isWishlist" class="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Liens ({{ isEdit ? links.length : pendingLinks.length }})
        </h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Où vous avez repéré cette pièce. Le prix pourra y être relevé depuis le panneau de détail.
        </p>

        <ul v-if="isEdit && links.length" class="mt-3 space-y-1">
          <li
            v-for="link in links"
            :key="link.id"
            class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm dark:border-slate-800"
          >
            <span class="truncate text-slate-800 dark:text-slate-200">{{ link.label || hostOf(link.url) }}</span>
            <a :href="link.url" target="_blank" rel="noopener noreferrer" class="truncate text-xs text-sky-600 hover:underline dark:text-sky-400">
              {{ link.url }}
            </a>
            <button type="button" class="ml-auto text-rose-600 hover:underline dark:text-rose-400" @click="removeLink(link)">
              ✕
            </button>
          </li>
        </ul>

        <ul v-else-if="!isEdit && pendingLinks.length" class="mt-3 space-y-1">
          <li
            v-for="(link, index) in pendingLinks"
            :key="index"
            class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm dark:border-slate-800"
          >
            <span class="truncate text-slate-800 dark:text-slate-200">{{ link.label || hostOf(link.url) }}</span>
            <span class="truncate text-xs text-slate-400 dark:text-slate-500">{{ link.url }}</span>
            <button type="button" class="ml-auto text-rose-600 hover:underline dark:text-rose-400" @click="removeLink(link)">
              ✕
            </button>
          </li>
        </ul>

        <div class="mt-3 flex flex-wrap items-center gap-2">
          <input
            v-model="linkDraft.url"
            placeholder="https://boutique.fr/rafale"
            :class="[inputClass, 'min-w-48 flex-1']"
          />
          <input v-model="linkDraft.label" placeholder="Libellé (facultatif)" :class="[inputClass, 'w-40']" />
          <AppButton
            variant="secondary"
            size="sm"
            :disabled="!linkDraft.url.trim()"
            @click="addLink"
          >
            Ajouter le lien
          </AppButton>
        </div>
      </section>

      <!-- Photos -->
      <section class="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <div class="flex items-center justify-between">
          <h3 class="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-200">
            Photos
            <span
              v-if="isPending(photoKey)"
              class="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-sky-500 dark:border-slate-700 dark:border-t-sky-400"
            />
          </h3>
          <label
            class="cursor-pointer rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Ajouter des photos
            <input type="file" accept="image/*" multiple class="hidden" @change="onFilesSelected" />
          </label>
        </div>

        <div v-if="isEdit" class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <figure
            v-for="(photo, index) in photos"
            :key="photo.id"
            draggable="true"
            class="group overflow-hidden rounded-lg border border-slate-200 transition dark:border-slate-800"
            :class="[dragIndex === index ? 'opacity-40' : 'cursor-grab', photo._uploading ? 'syncing' : '']"
            @dragstart="onDragStart(index)"
            @dragover.prevent
            @drop="onDrop(index)"
            @dragend="dragIndex = null"
          >
            <button
              type="button"
              class="relative block w-full"
              title="Agrandir"
              @click="photo._uploading ? null : (lightboxIndex = index)"
            >
              <img :src="photoSource(photo)" alt="" class="aspect-square w-full object-cover" />
              <span
                v-if="photo._uploading"
                class="absolute inset-0 grid place-items-center bg-slate-900/40 text-xs font-medium text-white"
              >
                envoi…
              </span>
              <span
                v-else
                class="absolute right-1 top-1 rounded bg-slate-900/60 px-1.5 py-0.5 text-xs font-semibold text-white"
              >
                {{ index + 1 }}
              </span>
            </button>
            <figcaption class="space-y-1 p-2">
              <p v-if="photo.caption" class="truncate text-xs text-slate-500 dark:text-slate-400" :title="photo.caption">
                {{ photo.caption }}
              </p>
              <p v-if="photo.is_primary" class="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                Couverture
              </p>
              <div v-if="!photo._uploading" class="flex flex-wrap items-center gap-2 text-xs">
                <button
                  v-if="!photo.is_primary"
                  type="button"
                  class="text-sky-600 hover:underline dark:text-sky-400"
                  @click="setPrimary(photo)"
                >
                  Principale
                </button>
                <button
                  type="button"
                  class="text-slate-500 hover:underline dark:text-slate-400"
                  @click="editCaption(photo)"
                >
                  Légende
                </button>
                <button type="button" :class="linkDanger" @click="removePhoto(photo)">Suppr.</button>
                <span class="ml-auto flex gap-1">
                  <button
                    type="button"
                    class="rounded border border-slate-300 px-1 leading-none text-slate-500 disabled:opacity-30 dark:border-slate-700 dark:text-slate-400"
                    :disabled="index === 0"
                    title="Déplacer avant"
                    @click="move(index, index - 1)"
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-300 px-1 leading-none text-slate-500 disabled:opacity-30 dark:border-slate-700 dark:text-slate-400"
                    :disabled="index === photos.length - 1"
                    title="Déplacer après"
                    @click="move(index, index + 1)"
                  >
                    ›
                  </button>
                </span>
              </div>
            </figcaption>
          </figure>
        </div>

        <ul v-else-if="pendingFiles.length" class="mt-3 space-y-1 text-sm text-slate-600 dark:text-slate-300">
          <li v-for="(file, i) in pendingFiles" :key="i" class="flex items-center justify-between">
            <span>{{ file.name }}</span>
            <button type="button" :class="linkDanger" @click="pendingFiles.splice(i, 1)">retirer</button>
          </li>
        </ul>
        <p v-else class="mt-3 text-sm text-slate-400 dark:text-slate-500">
          {{ isEdit ? 'Aucune photo pour cet objet.' : 'Les photos seront envoyées après l’enregistrement.' }}
        </p>
        <p v-if="isEdit && photos.length > 1" class="mt-2 text-xs text-slate-400 dark:text-slate-500">
          Glissez-déposez les vignettes pour changer l’ordre affiché.
        </p>
      </section>

      <p
        v-if="error"
        class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
      >
        {{ error }}
      </p>
    </form>

    <template #footer>
      <AppButton
        v-if="isEdit"
        variant="ghost"
        class="mr-auto text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/50"
        @click="$emit('remove', item)"
      >
        Supprimer l’objet
      </AppButton>
      <AppButton variant="secondary" @click="$emit('close')">Annuler</AppButton>
      <AppButton type="submit" :form="formId" variant="primary">Enregistrer</AppButton>
    </template>

    <PhotoLightbox
      :photos="photos"
      :open="lightboxIndex !== null"
      :start-index="lightboxIndex ?? 0"
      @close="lightboxIndex = null"
    />
  </AppModal>
</template>
