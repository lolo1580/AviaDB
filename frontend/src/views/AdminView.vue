<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, backupUrl, excelUrl, exportCsvUrl, photoUrl, reportUrl } from '../api'
import { auth, canWrite, isAdmin, refreshSession } from '../auth'
import { ui, setAdminTab } from '../ui'
import { STATUS_LABEL, TYPE_LABEL, formatMoney } from '../labels'
import { currencyLabel, refreshRates, saveBaseCurrency, saveRates, settings } from '../settings'
import { classes, flattenedClasses, loadClasses, subtreeItemCount } from '../classes'
import { isPending, optimistic, tempId } from '../optimistic'
import { confirm as askConfirm } from '../composables/useConfirm'
import { prompt as askPrompt } from '../composables/usePrompt'
import { useItemList } from '../composables/useItemList'
import { toast } from '../toast'
import AppTabs from '../components/ui/AppTabs.vue'
import AppModal from '../components/ui/AppModal.vue'
import AppButton from '../components/ui/AppButton.vue'
import FilterBar from '../components/FilterBar.vue'
import ItemFormModal from '../components/ItemFormModal.vue'

const tags = ref([])
const enums = ref(null)
const facets = ref({
  countries: [], aircraft_models: [], storage_locations: [],
  scales: [], manufacturers: [], tags: [],
})
const error = ref('')
const notice = ref('')

const filters = reactive({
  q: '', item_type: [], status: [], country: [], scale: [],
  manufacturer: [], tag: [], class_id: '', sort: 'name', order: 'asc',
})

// Liste des objets + mutations optimistes (les facettes suivent en arrière-plan).
const list = useItemList({ limit: 500, refreshStats: async () => { await loadFacets() } })
const { items } = list
const total = computed(() => list.total.value)
const loading = computed(() => list.loading.value)
const listError = computed(() => list.error.value)

/** Devises réellement utilisées par la collection (pour ne pas afficher 25 taux). */
const usedCurrencies = ref([])

const selected = ref([])
const showForm = ref(false)
const editing = ref(null)

// Catalogue d'onglets : chaque catégorie regroupe une préoccupation.
const tabs = computed(() =>
  [
    { id: 'items', label: 'Objets', icon: 'collection', badge: total.value },
    { id: 'tags', label: 'Tags', icon: 'inbox', badge: tags.value.length },
    { id: 'classes', label: 'Classes', icon: 'book', badge: classes.list.length },
    { id: 'currencies', label: 'Devises & taux', icon: 'charts', badge: Object.keys(settings.rates || {}).length },
    isAdmin() ? { id: 'users', label: 'Comptes', icon: 'user', badge: users.value.length } : null,
    isAdmin() ? { id: 'api', label: 'API', icon: 'external', badge: apiKeys.value.length } : null,
    isAdmin() ? { id: 'journal', label: 'Journal', icon: 'alert', badge: activity.value.length } : null,
    { id: 'backup', label: 'Sauvegarde', icon: 'external', badge: null },
  ].filter(Boolean),
)

function selectTab(tab) {
  setAdminTab(tab)
}

// Devises affichées dans l'onglet : celles utilisées, plus la devise de référence.
const showAllRates = ref(false)
const rateFilter = ref('')

const visibleRateCodes = computed(() => {
  const codes = Object.keys(rateDraft.value).sort()
  const base = settings.default_currency
  const query = rateFilter.value.trim().toLowerCase()
  const kept = showAllRates.value
    ? codes
    : codes.filter((code) => code === base || usedCurrencies.value.includes(code))
  if (!query) return kept
  return kept.filter(
    (code) => code.toLowerCase().includes(query) || (currencyLabel(code) || '').toLowerCase().includes(query),
  )
})

async function loadUsage() {
  try {
    const stats = await api.getStats()
    usedCurrencies.value = (stats.by_currency || []).map((bucket) => bucket.key)
  } catch {
    /* sans conséquence : on retombe sur la devise de référence */
  }
}

// --------------------------------------------------------------------------- #
// Classes (arborescence)
// --------------------------------------------------------------------------- #
const newRootClass = ref('')
const classRows = computed(() => flattenedClasses())

async function addClass(parentId = null, presetName = null) {
  const parent = parentId ? classes.list.find((node) => node.id === parentId) : null
  // Un nom peut être fourni directement (champ « nouvelle classe racine »),
  // sinon on le demande par une invite.
  const name =
    presetName ??
    (await askPrompt({
      title: parent ? `Nouvelle sous-classe de « ${parent.name} »` : 'Nouvelle classe racine',
      label: 'Nom de la classe',
      placeholder: 'Aéronefs, Chasseur, Transport…',
      maxLength: 80,
      confirmLabel: 'Créer',
    }))
  if (name === null || !name.trim()) return
  try {
    await api.createClass({ name: name.trim(), parent_id: parentId })
    await loadClasses()
    toast.success(`Classe « ${name.trim()} » créée`)
  } catch (e) {
    error.value = e.message
  }
}

/** Ajoute la classe racine saisie dans le champ dédié. */
function submitRootClass() {
  const name = newRootClass.value.trim()
  if (!name) return
  newRootClass.value = ''
  addClass(null, name)
}

async function renameClass(node) {
  const name = await askPrompt({
    title: 'Renommer la classe',
    label: 'Nouveau nom',
    value: node.name,
    maxLength: 80,
    confirmLabel: 'Renommer',
  })
  if (name === null || name.trim() === node.name) return
  try {
    await api.updateClass(node.id, { name: name.trim() })
    await loadClasses()
  } catch (e) {
    error.value = e.message
  }
}

async function deleteClass(node) {
  const used = subtreeItemCount(node.id)
  const accepted = await askConfirm({
    title: `Supprimer « ${node.name} » ?`,
    message: used
      ? `${used} objet(s) sont rattachés à cette classe ou à ses sous-classes : ils resteront dans la collection, mais sans classe.`
      : 'La classe et ses éventuelles sous-classes seront supprimées.',
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return
  try {
    await api.deleteClass(node.id, used > 0)
    await Promise.all([loadClasses(), load()])
  } catch (e) {
    error.value = e.message
  }
}

// --------------------------------------------------------------------------- #
// Clés d'API
// --------------------------------------------------------------------------- #
const apiKeys = ref([])
const newKeyLabel = ref('')
const createdKey = ref(null)

async function loadApiKeys() {
  if (!isAdmin()) {
    apiKeys.value = []
    return
  }
  try {
    apiKeys.value = await api.listApiKeys()
  } catch (e) {
    error.value = e.message
  }
}

async function addApiKey() {
  const label = newKeyLabel.value.trim()
  if (!label) return
  try {
    const created = await api.createApiKey(label)
    createdKey.value = created
    newKeyLabel.value = ''
    await loadApiKeys()
  } catch (e) {
    error.value = e.message
  }
}

async function toggleApiKey(record) {
  try {
    await api.updateApiKey(record.id, { is_active: !record.is_active })
    await loadApiKeys()
  } catch (e) {
    error.value = e.message
  }
}

async function removeApiKey(record) {
  const accepted = await askConfirm({
    title: 'Révoquer cette clé ?',
    message: `« ${record.label} » ne pourra plus interroger l’API. Cette action est définitive.`,
    confirmLabel: 'Révoquer',
    danger: true,
  })
  if (!accepted) return
  try {
    await api.deleteApiKey(record.id)
    await loadApiKeys()
  } catch (e) {
    error.value = e.message
  }
}

async function copyKey() {
  try {
    await navigator.clipboard.writeText(createdKey.value.key)
    toast.success('Clé copiée dans le presse-papiers')
  } catch {
    error.value = 'Copie impossible : sélectionnez la clé à la main.'
  }
}

const publicStatsUrl = computed(
  () => `${window.location.origin}/api/public/stats`,
)
const curlExample = computed(
  () =>
    `curl -H "X-API-Key: ${createdKey.value?.key ?? 'VOTRE_CLE'}" \\\n  ${publicStatsUrl.value}`,
)

// Actions en masse
const bulkStatus = ref('STORED_BOX')
const bulkTags = ref('')

const allSelected = computed(
  () => items.value.length > 0 && selected.value.length === items.value.length,
)

async function loadFacets() {
  try {
    facets.value = await api.getFacets()
  } catch (e) {
    error.value = e.message
  }
}

async function loadTags() {
  try {
    tags.value = await api.getTags()
  } catch (e) {
    error.value = e.message
  }
}

async function load() {
  error.value = ''
  await Promise.all([list.load({ ...filters }), loadTags(), loadFacets()])
  if (!enums.value) {
    try {
      enums.value = await api.getEnums()
    } catch (e) {
      error.value = e.message
    }
  }
  selected.value = selected.value.filter((id) => items.value.some((item) => item.id === id))
}

onMounted(async () => {
  if (!auth.checked) await refreshSession()
  // Un compte lecteur ne doit pas rester sur un onglet réservé aux administrateurs
  // (onglet mémorisé d'une session précédente) : la page serait vide.
  if (!isAdmin() && ['users', 'api', 'journal'].includes(ui.adminTab)) setAdminTab('items')
  await load()
  await Promise.all([loadUsers(), loadUsage(), loadClasses(), loadApiKeys(), loadActivity()])
})

function specific(item) {
  if (item.item_type === 'DIECAST' && item.diecast) {
    return [item.diecast.scale, item.diecast.manufacturer].filter(Boolean).join(' · ')
  }
  if (item.item_type === 'PATCH' && item.patch) {
    return [item.patch.unit_squadron, item.patch.base].filter(Boolean).join(' · ')
  }
  return ''
}

function toggle(id) {
  const index = selected.value.indexOf(id)
  if (index === -1) selected.value.push(id)
  else selected.value.splice(index, 1)
}

function toggleAll() {
  selected.value = allSelected.value ? [] : items.value.map((item) => item.id)
}

function openCreate() {
  editing.value = null
  showForm.value = true
}

function openEdit(item) {
  editing.value = item
  showForm.value = true
}

// --- Mutations optimistes : la modale se ferme avant l'appel serveur ---
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
  selected.value = selected.value.filter((id) => id !== item.id)
  list.remove(item.id)
}

async function changeStatus(item, value) {
  await list.setStatus(item.id, value)
}

async function runBulk(payload) {
  error.value = ''
  const ids = [...selected.value]
  if (!ids.length) return
  selected.value = []
  const { ok, data } = await list.bulk(ids, payload.action, payload)
  if (ok) {
    notice.value = `${data?.affected ?? ids.length} objet(s) — action « ${payload.action} »`
  }
}

async function bulkDelete() {
  const accepted = await askConfirm({
    title: 'Supprimer la sélection ?',
    message: `${selected.value.length} objet(s) et leurs photos seront définitivement supprimés.`,
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return
  runBulk({ action: 'delete' })
}

function splitTags(value) {
  return value.split(',').map((s) => s.trim()).filter(Boolean)
}

async function exportJson() {
  try {
    const data = await api.exportItems()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `aviadb-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
    notice.value = `${data.total} objet(s) exporté(s)`
  } catch (e) {
    error.value = e.message
  }
}

async function importJson(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  error.value = ''
  try {
    const parsed = JSON.parse(await file.text())
    const entries = Array.isArray(parsed) ? parsed : parsed.items
    if (!Array.isArray(entries)) throw new Error('Format attendu : un tableau, ou {items: [...]}')
    const res = await api.importItems(entries)
    notice.value = `Import : ${res.created} objet(s) créé(s)`
    if (res.errors?.length) error.value = res.errors.join(' | ')
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function importCsvFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  error.value = ''
  try {
    const res = await api.importCsv(file)
    notice.value = `Import CSV : ${res.created} objet(s) créé(s)`
    if (res.errors?.length) error.value = res.errors.join(' | ')
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function restoreFile(event) {
  const file = event.target?.files?.[0]
  event.target.value = ''
  if (!file) return

  const choice = await askConfirm({
    title: 'Restaurer une sauvegarde',
    subtitle: file.name,
    message:
      'Remplacer toute la collection par le contenu de l’archive, ou fusionner avec l’existant ?',
    confirmLabel: 'Remplacer',
    alternateLabel: 'Fusionner',
    cancelLabel: 'Annuler',
    danger: true,
  })
  if (!choice) return

  error.value = ''
  try {
    const res = await api.restoreBackup(file, choice === 'confirm' ? 'replace' : 'merge')
    notice.value = `Restauration : ${res.created} objet(s), ${res.photos_restored} photo(s)${
      res.replaced ? ' (remplacement)' : ''
    }`
    if (res.errors?.length) error.value = res.errors.join(' | ')
    await Promise.all([load(), loadUsers()])
  } catch (e) {
    error.value = e.message
  }
}

// --- Comptes ---
const users = ref([])
const newUser = reactive({ username: '', password: '', role: 'VIEWER' })

async function loadUsers() {
  if (!isAdmin()) {
    users.value = []
    return
  }
  try {
    users.value = await api.listUsers()
  } catch (e) {
    error.value = e.message
  }
}

// --- Journal d'activité (audit) ---
const activity = ref([])

async function loadActivity() {
  if (!isAdmin()) {
    activity.value = []
    return
  }
  try {
    activity.value = await api.listActivity(200)
  } catch (e) {
    error.value = e.message
  }
}

async function addUser() {
  error.value = ''
  const username = newUser.username.trim()
  const payload = { username, password: newUser.password, role: newUser.role }
  const placeholder = {
    id: tempId('user'),
    username,
    role: payload.role,
    is_active: true,
    created_at: new Date().toISOString(),
    last_login_at: null,
    _optimistic: true,
  }
  users.value = [...users.value, placeholder].sort((a, b) => a.username.localeCompare(b.username))
  newUser.username = ''
  newUser.password = ''
  newUser.role = 'VIEWER'

  await optimistic({
    key: `user:${placeholder.id}`,
    label: 'Création du compte',
    apply: () => () => {
      users.value = users.value.filter((entry) => entry.id !== placeholder.id)
    },
    request: () => api.createUser(payload),
    onSuccess: (created) => {
      users.value = users.value
        .map((entry) => (entry.id === placeholder.id ? created : entry))
        .sort((a, b) => a.username.localeCompare(b.username))
    },
  })
}

async function changeRole(user, role) {
  const before = user.role
  user.role = role
  await optimistic({
    key: `user:${user.id}`,
    label: 'Changement de rôle',
    apply: () => () => {
      user.role = before
    },
    request: () => api.updateUser(user.id, { role }),
  })
}

async function toggleActive(user) {
  const before = user.is_active
  user.is_active = !before
  await optimistic({
    key: `user:${user.id}`,
    label: 'Activation du compte',
    apply: () => () => {
      user.is_active = before
    },
    request: () => api.updateUser(user.id, { is_active: !before }),
  })
}

async function resetPassword(user) {
  const password = await askPrompt({
    title: 'Nouveau mot de passe',
    label: `Compte « ${user.username} »`,
    subtitle: '6 caractères minimum.',
    type: 'password',
    minLength: 6,
    maxLength: 128,
    confirmLabel: 'Modifier',
  })
  if (!password) return
  await optimistic({
    key: `user:${user.id}`,
    label: 'Mot de passe',
    request: () => api.updateUser(user.id, { password }),
    onSuccess: () => toast.success(`Mot de passe de « ${user.username} » modifié`),
  })
}

async function removeUser(user) {
  const accepted = await askConfirm({
    title: 'Supprimer ce compte ?',
    message: `Le compte « ${user.username} » ne pourra plus se connecter.`,
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return

  const index = users.value.findIndex((entry) => entry.id === user.id)
  if (index === -1) return
  users.value = users.value.filter((entry) => entry.id !== user.id)

  await optimistic({
    key: `user:${user.id}`,
    label: 'Suppression du compte',
    apply: () => () => {
      users.value.splice(Math.min(index, users.value.length), 0, user)
    },
    request: () => api.deleteUser(user.id),
  })
}

// --- Devises et taux de change ---
const rateDraft = ref({})
const ratesBusy = ref(false)

function syncRateDraft() {
  const draft = {}
  for (const [code, value] of Object.entries(settings.rates || {})) draft[code] = String(value)
  rateDraft.value = draft
}

const rateCodes = computed(() => Object.keys(rateDraft.value).sort())

function rateInBase(code) {
  const rate = settings.rates?.[code]
  const base = settings.rates?.[settings.default_currency]
  if (!rate || !base) return null
  return base / rate
}

async function changeBaseCurrency(code) {
  error.value = ''
  try {
    await saveBaseCurrency(code)
    notice.value = `Devise de référence : ${code}`
    await Promise.all([load(), loadUsers()])
  } catch (e) {
    error.value = e.message
  }
}

async function saveRatesDraft() {
  ratesBusy.value = true
  error.value = ''
  try {
    const payload = {}
    for (const [code, value] of Object.entries(rateDraft.value)) {
      const number = Number(value)
      if (value !== '' && !Number.isNaN(number) && number > 0) payload[code] = number
    }
    await saveRates(payload)
    notice.value = 'Taux de change enregistrés'
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    ratesBusy.value = false
  }
}

async function refreshRatesFromProvider() {
  ratesBusy.value = true
  error.value = ''
  try {
    await refreshRates()
    notice.value = `Taux actualisés — ${settings.rates_source || 'source inconnue'}`
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    ratesBusy.value = false
  }
}

watch(
  () => settings.rates,
  () => syncRateDraft(),
  { deep: true, immediate: true },
)

// Toute modification d'un filtre relance la requête (comme dans la collection).
let filtersDebounce
watch(
  filters,
  () => {
    clearTimeout(filtersDebounce)
    filtersDebounce = setTimeout(() => load(), 250)
  },
  { deep: true },
)

async function renameTag(tag) {
  const name = await askPrompt({
    title: 'Renommer le tag',
    label: 'Nouveau nom',
    value: tag.name,
    maxLength: 64,
    confirmLabel: 'Renommer',
  })
  if (name === null || name.trim() === tag.name) return
  const before = tag.name
  const next = name.trim()

  // Renommage local, y compris dans les objets déjà affichés.
  tag.name = next
  const itemTags = items.value.map((item) => ({ item, tags: [...(item.tags || [])] }))
  items.value.forEach((item) => {
    item.tags = (item.tags || []).map((entry) => (entry.id === tag.id ? { ...entry, name: next } : entry))
  })

  await optimistic({
    key: `tag:${tag.id}`,
    label: 'Renommage du tag',
    apply: () => () => {
      tag.name = before
      itemTags.forEach(({ item, tags }) => {
        item.tags = tags
      })
    },
    request: () => api.renameTag(tag.id, next),
  })
}

async function deleteTag(tag) {
  const accepted = await askConfirm({
    title: 'Supprimer ce tag ?',
    message: `« ${tag.name} » sera retiré de tous les objets.`,
    confirmLabel: 'Supprimer',
    danger: true,
  })
  if (!accepted) return
  const index = tags.value.findIndex((entry) => entry.id === tag.id)
  const itemTags = items.value.map((item) => ({ item, tags: [...(item.tags || [])] }))

  tags.value = tags.value.filter((entry) => entry.id !== tag.id)
  items.value.forEach((item) => {
    item.tags = (item.tags || []).filter((entry) => entry.id !== tag.id)
  })

  await optimistic({
    key: `tag:${tag.id}`,
    label: 'Suppression du tag',
    apply: () => () => {
      tags.value.splice(Math.min(index, tags.value.length), 0, tag)
      itemTags.forEach(({ item, tags }) => {
        item.tags = tags
      })
    },
    request: () => api.deleteTag(tag.id),
  })
}

const btn =
  'rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
const btnPrimary = 'rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-700'
const cell = 'px-3 py-2 text-sm text-slate-700 dark:text-slate-300'
</script>

<template>
  <div class="flex flex-col gap-6">
    <!-- En-tête : l'accès est déjà protégé en amont -->
    <div>
      <h2 class="text-lg font-semibold text-slate-900 dark:text-slate-100">Administration</h2>
      <p class="text-sm text-slate-500 dark:text-slate-400">
        {{ total }} objet(s) · {{ tags.length }} tag(s) · {{ users.length }} compte(s)
        <span v-if="!auth.enabled" class="text-amber-600 dark:text-amber-400">
          · accès libre (ADMIN_PASSWORD non défini)</span>
      </p>
    </div>

    <!-- Catalogue d'onglets, collant sous la barre du haut -->
    <AppTabs
      :model-value="ui.adminTab"
      :tabs="tabs"
      class="sticky top-16 z-20 -mx-1 bg-slate-100/95 px-1 backdrop-blur dark:bg-slate-950/95"
      @update:model-value="selectTab"
    />

    <p
      v-if="notice"
      class="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
    >
      {{ notice }}
    </p>
    <p
      v-if="error || listError"
      class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
    >
      {{ error || listError }}
    </p>

    <!-- ================================ Onglet « Objets » ================================ -->
    <section v-if="ui.adminTab === 'items'" id="panel-items" role="tabpanel" aria-labelledby="tab-items" class="flex flex-col gap-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300">Objets de la collection</h3>
        <div class="flex flex-wrap gap-2">
          <button v-if="canWrite()" type="button" :class="btnPrimary" @click="openCreate">+ Nouvel objet</button>
          <button type="button" :class="btn" @click="exportJson">Exporter JSON</button>
          <a :href="excelUrl()" :class="btn" download>Exporter Excel</a>
          <a :href="exportCsvUrl()" :class="btn" download>Exporter CSV</a>
          <label v-if="canWrite()" :class="['cursor-pointer', btn]">
            Importer JSON
            <input type="file" accept="application/json,.json" class="hidden" @change="importJson" />
          </label>
          <label v-if="canWrite()" :class="['cursor-pointer', btn]">
            Importer CSV
            <input type="file" accept="text/csv,.csv" class="hidden" @change="importCsvFile" />
          </label>
          <button type="button" :class="btn" @click="load">Rafraîchir</button>
        </div>
      </div>

      <FilterBar :filters="filters" :facets="facets" :enums="enums" :total="total" />
      <!-- Barre d'actions en masse -->
      <div
        v-if="selected.length && canWrite()"
        class="flex flex-wrap items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 dark:border-sky-900 dark:bg-sky-950/40"
      >
        <span class="text-sm font-medium text-sky-900 dark:text-sky-200">
          {{ selected.length }} sélectionné(s)
        </span>

        <select v-model="bulkStatus" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700">
          <option v-for="s in enums?.statuses || []" :key="s" :value="s">{{ STATUS_LABEL[s] }}</option>
        </select>
        <button type="button" :class="btn" @click="runBulk({ action: 'set_status', status: bulkStatus })">
          Appliquer le statut
        </button>

        <input
          v-model="bulkTags"
          placeholder="tag1, tag2"
          class="w-40 rounded-lg border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700"
        />
        <button type="button" :class="btn" @click="runBulk({ action: 'add_tags', tags: splitTags(bulkTags) })">
          Ajouter les tags
        </button>
        <button type="button" :class="btn" @click="runBulk({ action: 'remove_tags', tags: splitTags(bulkTags) })">
          Retirer les tags
        </button>

        <button
          type="button"
          class="rounded-lg border border-rose-300 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-400 dark:hover:bg-rose-950/50"
          @click="bulkDelete"
        >
          Supprimer
        </button>
      </div>

      <!-- Tableau -->
      <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table class="min-w-full divide-y divide-slate-200 dark:divide-slate-800">
          <thead class="bg-slate-50 dark:bg-slate-800/60">
            <tr class="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              <th class="px-3 py-2">
                <input v-if="canWrite()" type="checkbox" :checked="allSelected" @change="toggleAll" />
              </th>
              <th class="px-3 py-2">Photo</th>
              <th class="px-3 py-2">Nom</th>
              <th class="px-3 py-2">Type</th>
              <th class="px-3 py-2">Pays</th>
              <th class="px-3 py-2">Détails</th>
              <th class="px-3 py-2">Statut</th>
              <th class="px-3 py-2">Valeur</th>
              <th class="px-3 py-2">Photos</th>
              <th class="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr
              v-for="item in items"
              :key="item.id"
              class="transition-opacity hover:bg-slate-50 dark:hover:bg-slate-800/50"
              :class="isPending(`item:${item.id}`) ? 'syncing' : ''"
            >
              <td :class="cell">
                <input
                  v-if="canWrite()"
                  type="checkbox"
                  :checked="selected.includes(item.id)"
                  @change="toggle(item.id)"
                />
              </td>
              <td :class="cell">
                <button type="button" @click="openEdit(item)">
                  <img
                    v-if="item.photos.length"
                    :src="photoUrl((item.photos.find((p) => p.is_primary) || item.photos[0]).file_path, 96)"
                    class="h-10 w-10 rounded object-cover"
                  />
                  <span
                    v-else
                    class="grid h-10 w-10 place-items-center rounded bg-slate-100 text-xs text-slate-400 dark:bg-slate-800 dark:text-slate-500"
                    >—</span
                  >
                </button>
              </td>
              <td :class="[cell, 'font-medium text-slate-900 dark:text-slate-100']">
                <span class="flex items-center gap-2">
                  <button type="button" class="text-left hover:text-sky-700 dark:hover:text-sky-400" @click="openEdit(item)">
                    {{ item.name }}
                  </button>
                  <span
                    v-if="item._optimistic"
                    class="rounded-full bg-slate-900/70 px-2 py-0.5 text-xs font-medium text-white"
                  >
                    envoi…
                  </span>
                  <span
                    v-else-if="isPending(`item:${item.id}`)"
                    class="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-sky-500 dark:border-slate-700 dark:border-t-sky-400"
                    title="Synchronisation en cours"
                  />
                </span>
                <span v-if="item.tags.length" class="mt-1 flex flex-wrap gap-1">
                  <span
                    v-for="tag in item.tags"
                    :key="tag.id"
                    class="rounded bg-slate-100 px-1.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                  >
                    {{ tag.name }}
                  </span>
                </span>
              </td>
              <td :class="cell">{{ TYPE_LABEL[item.item_type] }}</td>
              <td :class="cell">{{ item.country || '—' }}</td>
              <td :class="cell">{{ specific(item) || '—' }}</td>
              <td :class="cell">
                <select
                  v-if="canWrite()"
                  :value="item.status"
                  class="rounded-lg border border-slate-300 px-2 py-1 text-sm dark:border-slate-700"
                  @change="changeStatus(item, $event.target.value)"
                >
                  <option v-for="s in enums?.statuses || []" :key="s" :value="s">{{ STATUS_LABEL[s] }}</option>
                </select>
                <span v-else>{{ STATUS_LABEL[item.status] }}</span>
              </td>
              <td :class="cell">{{ formatMoney(item.estimated_value, item.currency) || '—' }}</td>
              <td :class="cell">{{ item.photos.length }}</td>
              <td :class="cell">
                <div v-if="canWrite()" class="flex gap-2">
                  <button type="button" class="text-sky-600 hover:underline dark:text-sky-400" @click="openEdit(item)">
                    Modifier
                  </button>
                  <button type="button" class="text-rose-600 hover:underline dark:text-rose-400" @click="onRemove(item)">
                    Suppr.
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <p v-if="loading" class="px-3 py-8 text-center text-sm text-slate-400 dark:text-slate-500">Chargement…</p>
        <p v-else-if="!items.length" class="px-3 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
          Aucun objet
        </p>
      </div>
    </section>

    <!-- ================================ Onglet « Tags » ================================ -->
    <section
      v-else-if="ui.adminTab === 'tags'"
      id="panel-tags"
      role="tabpanel"
      aria-labelledby="tab-tags"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Vocabulaire de tags</h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            {{ tags.length }} tag(s). Renommer un tag le met à jour sur tous les objets.
          </p>
        </div>
      </div>
      <ul class="mt-3 flex flex-wrap gap-2">
          <li
            v-for="tag in tags"
            :key="tag.id"
            class="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-sm dark:border-slate-800"
          >
            <span class="text-slate-700 dark:text-slate-300">{{ tag.name }}</span>
            <button
              v-if="canWrite()"
              type="button"
              class="text-xs text-slate-400 hover:text-sky-600 dark:hover:text-sky-400"
              @click="renameTag(tag)"
            >
              renommer
            </button>
            <button
              v-if="canWrite()"
              type="button"
              class="text-xs text-slate-400 hover:text-rose-600 dark:hover:text-rose-400"
              @click="deleteTag(tag)"
            >
              ✕
            </button>
          </li>
        </ul>
        <p v-if="!tags.length" class="mt-2 text-sm text-slate-400 dark:text-slate-500">Aucun tag.</p>
    </section>

    <!-- ============================ Onglet « Devises & taux » ============================ -->
    <section
      v-else-if="ui.adminTab === 'currencies'"
      id="panel-currencies"
      role="tabpanel"
      aria-labelledby="tab-currencies"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Devises &amp; taux de change</h3>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              Tous les totaux et graphiques sont exprimés dans la devise de référence.
              <span v-if="settings.rates_updated_at">
                Dernière mise à jour : {{ new Date(settings.rates_updated_at).toLocaleString('fr-FR') }}
                ({{ settings.rates_source }})
              </span>
              <span v-else> Aucun taux enregistré pour l’instant.</span>
            </p>
          </div>
          <div class="flex flex-wrap items-end gap-2">
            <label class="flex flex-col gap-1">
              <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Devise de référence</span>
              <select
                :value="settings.default_currency"
                class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
                :disabled="!canWrite()"
                @change="changeBaseCurrency($event.target.value)"
              >
                <option v-for="option in settings.currencies" :key="option.code" :value="option.code">
                  {{ option.code }} — {{ option.label }}
                </option>
              </select>
            </label>
            <button
              v-if="canWrite()"
              type="button"
              :class="btn"
              :disabled="ratesBusy"
              @click="refreshRatesFromProvider"
            >
              {{ ratesBusy ? 'Actualisation…' : 'Actualiser depuis la BCE' }}
            </button>
          </div>
        </div>

        <div class="mt-4 flex flex-wrap items-end gap-3">
          <label class="flex min-w-52 flex-1 flex-col gap-1">
            <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Filtrer les devises</span>
            <input
              v-model="rateFilter"
              type="search"
              placeholder="USD, livre, franc…"
              class="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-sky-500 dark:border-slate-700"
            />
          </label>
          <label class="flex cursor-pointer items-center gap-2 pb-2 text-sm text-slate-600 dark:text-slate-300">
            <input v-model="showAllRates" type="checkbox" class="h-4 w-4 rounded border-slate-300 dark:border-slate-700" />
            Toutes les devises ({{ rateCodes.length }})
          </label>
        </div>

        <p v-if="!visibleRateCodes.length" class="mt-3 text-sm text-slate-400 dark:text-slate-500">
          <template v-if="!rateCodes.length">
            Cliquez sur « Actualiser depuis la BCE » pour récupérer les taux du jour.
          </template>
          <template v-else>Aucune devise ne correspond.</template>
        </p>

        <div v-else class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <label
            v-for="code in visibleRateCodes"
            :key="code"
            class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800"
          >
            <span class="w-12 shrink-0 text-sm font-medium text-slate-700 dark:text-slate-300">{{ code }}</span>
            <span class="shrink-0 text-xs text-slate-400 dark:text-slate-500">1 EUR =</span>
            <input
              v-model="rateDraft[code]"
              type="number"
              step="0.0001"
              min="0"
              :disabled="!canWrite()"
              class="w-24 rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-700"
            />
            <span v-if="code !== settings.default_currency" class="ml-auto text-xs text-slate-400 dark:text-slate-500">
              = 1 {{ code }} → {{ rateInBase(code)?.toFixed(4) }} {{ settings.default_currency }}
            </span>
            <span v-else class="ml-auto text-xs text-slate-400 dark:text-slate-500">référence</span>
          </label>
        </div>

        <p
          v-if="!showAllRates && rateCodes.length && visibleRateCodes.length < rateCodes.length"
          class="mt-2 text-xs text-slate-400 dark:text-slate-500"
        >
          Seules les devises utilisées par la collection (et la devise de référence) sont affichées.
        </p>

        <div v-if="visibleRateCodes.length && canWrite()" class="mt-3 flex flex-wrap items-center gap-3">
          <button type="button" :class="btnPrimary" :disabled="ratesBusy" @click="saveRatesDraft">
            Enregistrer les taux
          </button>
          <p class="text-xs text-slate-400 dark:text-slate-500">
            Convention BCE : nombre d’unités de la devise pour 1 EUR. Corrigez une valeur si besoin.
          </p>
        </div>
    </section>

    <!-- =============================== Onglet « Classes » =============================== -->
    <section
      v-else-if="ui.adminTab === 'classes'"
      id="panel-classes"
      role="tabpanel"
      aria-labelledby="tab-classes"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Classes</h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            Arborescence de classement (classe → sous-classe). Chaque objet peut être rattaché
            à une classe ; filtrer sur une classe inclut sa descendance.
          </p>
        </div>
        <div v-if="canWrite()" class="flex flex-wrap items-end gap-2">
          <input
            v-model="newRootClass"
            placeholder="Nouvelle classe racine…"
            class="w-56 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
            @keyup.enter="submitRootClass"
          />
          <button
            type="button"
            :class="btnPrimary"
            :disabled="!newRootClass.trim()"
            @click="submitRootClass"
          >
            Ajouter
          </button>
        </div>
      </div>

      <ul v-if="classRows.length" class="mt-4 divide-y divide-slate-100 dark:divide-slate-800">
        <li
          v-for="node in classRows"
          :key="node.id"
          class="flex flex-wrap items-center gap-2 py-2"
          :style="{ paddingLeft: `${node.depth * 1.5}rem` }"
        >
          <AppIcon
            v-if="node.depth"
            name="collapseRight"
            size="h-3 w-3"
            class="shrink-0 text-slate-300 dark:text-slate-600"
          />
          <span class="text-sm font-medium text-slate-800 dark:text-slate-200">{{ node.name }}</span>
          <span
            v-if="subtreeItemCount(node.id)"
            class="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-300"
          >
            {{ subtreeItemCount(node.id) }} objet(s)
          </span>

          <div v-if="canWrite()" class="ml-auto flex flex-wrap gap-2 text-xs">
            <button type="button" class="text-sky-600 hover:underline dark:text-sky-400" @click="addClass(node.id)">
              + sous-classe
            </button>
            <button type="button" class="text-slate-500 hover:underline dark:text-slate-400" @click="renameClass(node)">
              renommer
            </button>
            <button type="button" class="text-rose-600 hover:underline dark:text-rose-400" @click="deleteClass(node)">
              supprimer
            </button>
          </div>
        </li>
      </ul>
      <p v-else class="mt-4 text-sm text-slate-400 dark:text-slate-500">
        Aucune classe pour l’instant. Créez par exemple « Aéronefs », puis « Chasseur » à
        l’intérieur, puis « Rafale ».
      </p>
    </section>

    <!-- ================================ Onglet « API » ================================ -->
    <section
      v-else-if="ui.adminTab === 'api' && isAdmin()"
      id="panel-api"
      role="tabpanel"
      aria-labelledby="tab-api"
      class="flex flex-col gap-4"
    >
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Clés d’API</h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Une clé donne accès aux <strong>métriques agrégées</strong> de la collection
          (<code>GET {{ '/api/public/stats' }}</code>) : compteurs, valeurs totales et répartitions.
          Aucun nom d’objet, aucun prix unitaire, aucun emplacement n’est exposé. Pratique pour
          afficher quelques chiffres sur un site externe.
        </p>

        <div v-if="canWrite()" class="mt-3 flex flex-wrap items-end gap-2">
          <label class="flex flex-col gap-1">
            <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Libellé</span>
            <input
              v-model="newKeyLabel"
              placeholder="Page d’accueil du site"
              class="w-64 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
              @keyup.enter="addApiKey"
            />
          </label>
          <button type="button" :class="btnPrimary" :disabled="!newKeyLabel.trim()" @click="addApiKey">
            Générer une clé
          </button>
        </div>

        <div v-if="apiKeys.length" class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 dark:divide-slate-800">
            <thead class="bg-slate-50 dark:bg-slate-800/60">
              <tr class="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <th :class="cell">Libellé</th>
                <th :class="cell">Clé</th>
                <th :class="cell">État</th>
                <th :class="cell">Créée le</th>
                <th :class="cell">Dernier appel</th>
                <th :class="cell">Appels</th>
                <th :class="cell">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="record in apiKeys" :key="record.id" class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <td :class="[cell, 'font-medium text-slate-900 dark:text-slate-100']">{{ record.label }}</td>
                <td :class="[cell, 'font-mono text-xs']">{{ record.prefix }}</td>
                <td :class="cell">
                  <span
                    class="rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset"
                    :class="record.is_active
                      ? 'bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-400/30'
                      : 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-400/30'"
                  >
                    {{ record.is_active ? 'Active' : 'Révoquée' }}
                  </span>
                </td>
                <td :class="cell">{{ new Date(record.created_at).toLocaleDateString('fr-FR') }}</td>
                <td :class="cell">
                  {{ record.last_used_at ? new Date(record.last_used_at).toLocaleString('fr-FR') : '—' }}
                </td>
                <td :class="cell">{{ record.request_count }}</td>
                <td :class="cell">
                  <div class="flex gap-2">
                    <button type="button" class="text-slate-500 hover:underline dark:text-slate-400" @click="toggleApiKey(record)">
                      {{ record.is_active ? 'Désactiver' : 'Réactiver' }}
                    </button>
                    <button type="button" class="text-rose-600 hover:underline dark:text-rose-400" @click="removeApiKey(record)">
                      Révoquer
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="mt-4 text-sm text-slate-400 dark:text-slate-500">Aucune clé pour l’instant.</p>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Utilisation</h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          En-tête <code>X-API-Key</code>, ou paramètre <code>?api_key=</code> pour un widget.
          La page de documentation complète est sur
          <a href="/api-docs/" target="_blank" rel="noopener" class="text-sky-600 hover:underline dark:text-sky-400">/api-docs/</a>.
        </p>
        <pre class="mt-2 overflow-x-auto rounded-lg bg-slate-900 px-3 py-2 text-xs text-slate-100"><code>curl -H "X-API-Key: aviadb_…" \
  {{ publicStatsUrl }}</code></pre>
      </div>
    </section>

    <!-- ============================== Onglet « Comptes » ============================== -->
    <section
      v-else-if="ui.adminTab === 'users' && isAdmin()"
      id="panel-users"
      role="tabpanel"
      aria-labelledby="tab-users"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Comptes ({{ users.length }})
        </h3>

        <div class="mt-3 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 dark:divide-slate-800">
            <thead class="bg-slate-50 dark:bg-slate-800/60">
              <tr class="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <th class="px-3 py-2">Identifiant</th>
                <th class="px-3 py-2">Rôle</th>
                <th class="px-3 py-2">Actif</th>
                <th class="px-3 py-2">Dernière connexion</th>
                <th class="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="user in users" :key="user.id" class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <td :class="[cell, 'font-medium text-slate-900 dark:text-slate-100']">
                  {{ user.username }}
                  <span v-if="user.username === auth.username" class="text-xs text-slate-400 dark:text-slate-500">
                    (vous)
                  </span>
                </td>
                <td :class="cell">
                  <select
                    :value="user.role"
                    class="rounded-lg border border-slate-300 px-2 py-1 text-sm dark:border-slate-700"
                    @change="changeRole(user, $event.target.value)"
                  >
                    <option value="ADMIN">Administrateur</option>
                    <option value="VIEWER">Lecteur</option>
                  </select>
                </td>
                <td :class="cell">
                  <button
                    type="button"
                    class="rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset"
                    :class="user.is_active
                      ? 'bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-400/30'
                      : 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-400/30'"
                    @click="toggleActive(user)"
                  >
                    {{ user.is_active ? 'Actif' : 'Désactivé' }}
                  </button>
                </td>
                <td :class="cell">
                  {{ user.last_login_at ? new Date(user.last_login_at).toLocaleString('fr-FR') : '—' }}
                </td>
                <td :class="cell">
                  <div class="flex gap-2">
                    <button
                      type="button"
                      class="text-slate-500 hover:underline dark:text-slate-400"
                      @click="resetPassword(user)"
                    >
                      Mot de passe
                    </button>
                    <button
                      type="button"
                      class="text-rose-600 hover:underline dark:text-rose-400"
                      @click="removeUser(user)"
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <form class="mt-4 flex flex-wrap items-end gap-2" @submit.prevent="addUser">
          <label class="flex flex-col gap-1">
            <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Identifiant</span>
            <input
              v-model="newUser.username"
              required
              class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
            />
          </label>
          <label class="flex flex-col gap-1">
            <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Mot de passe</span>
            <input
              v-model="newUser.password"
              type="password"
              required
              minlength="6"
              class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
            />
          </label>
          <label class="flex flex-col gap-1">
            <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Rôle</span>
            <select
              v-model="newUser.role"
              class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
            >
              <option value="VIEWER">Lecteur (lecture seule)</option>
              <option value="ADMIN">Administrateur</option>
            </select>
          </label>
          <button type="submit" :class="btnPrimary">Créer le compte</button>
        </form>
    </section>

    <!-- ============================= Onglet « Journal » ============================= -->
    <section
      v-else-if="ui.adminTab === 'journal' && isAdmin()"
      id="panel-journal"
      role="tabpanel"
      aria-labelledby="tab-journal"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Journal d’activité
        </h3>
        <button type="button" :class="btn" @click="loadActivity">Rafraîchir</button>
      </div>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Les {{ activity.length }} dernières modifications : qui a modifié quoi, et quand.
      </p>

      <div v-if="activity.length" class="mt-3 overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 dark:divide-slate-800">
          <thead class="bg-slate-50 dark:bg-slate-800/60">
            <tr class="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              <th :class="cell">Date</th>
              <th :class="cell">Compte</th>
              <th :class="cell">Méthode</th>
              <th :class="cell">Requête</th>
              <th :class="cell">Code</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr
              v-for="entry in activity"
              :key="entry.id"
              class="hover:bg-slate-50 dark:hover:bg-slate-800/50"
            >
              <td :class="cell">{{ new Date(entry.at).toLocaleString('fr-FR') }}</td>
              <td :class="[cell, 'font-medium text-slate-900 dark:text-slate-100']">
                {{ entry.username || '—' }}
              </td>
              <td :class="cell">{{ entry.method }}</td>
              <td :class="[cell, 'font-mono text-xs']">{{ entry.path }}</td>
              <td :class="cell">
                <span
                  :class="
                    entry.status_code < 400
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-rose-600 dark:text-rose-400'
                  "
                >
                  {{ entry.status_code }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="mt-3 text-sm text-slate-400 dark:text-slate-500">
        Aucune activité enregistrée.
      </p>
    </section>

    <!-- ============================= Onglet « Sauvegarde » ============================= -->
    <section
      v-else-if="ui.adminTab === 'backup'"
      id="panel-backup"
      role="tabpanel"
      aria-labelledby="tab-backup"
      class="flex flex-col gap-4"
    >
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Sauvegarde complète (ZIP)</h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          L’archive contient les objets, leurs photos, les réglages (devise de référence et taux)
          et les comptes. Un seul fichier à conserver — c’est aussi le moyen de transférer la
          collection vers une autre base.
        </p>
        <div class="mt-3 flex flex-wrap gap-2">
          <a :href="backupUrl()" :class="btnPrimary" download>Sauvegarder maintenant</a>
          <label v-if="canWrite()" :class="['cursor-pointer', btn]">
            Restaurer une archive…
            <input type="file" accept="application/zip,.zip" class="hidden" @change="restoreFile" />
          </label>
        </div>
        <p class="mt-2 text-xs text-slate-400 dark:text-slate-500">
          À la restauration, vous choisissez entre <strong>remplacer</strong> la collection ou
          <strong>fusionner</strong> avec l’existant. Les comptes déjà présents ne sont jamais écrasés.
        </p>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Sauvegarde PostgreSQL</h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Pour une sauvegarde au niveau du moteur (restauration par <code>psql</code>) :
        </p>
        <pre class="mt-2 overflow-x-auto rounded-lg bg-slate-900 px-3 py-2 text-xs text-slate-100"><code>docker exec aviadb-db pg_dump -U aviadb aviadb | gzip &gt; aviadb-pg.sql.gz</code></pre>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Inventaire et étiquettes
        </h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Le rapport d’inventaire récapitule les totaux et la liste des objets — utile pour une
          déclaration d’assurance. Les étiquettes portent un QR code qui rouvre la fiche de
          l’objet.
        </p>
        <div class="mt-3 flex flex-wrap gap-2">
          <a :href="reportUrl()" :class="btnPrimary" download>Rapport PDF</a>
          <a href="/etiquettes" :class="btn">Étiquettes à imprimer</a>
        </div>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Documentation de l’API</h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Page dédiée, hors de l’application : schéma à jour et essais de requêtes.
        </p>
        <a href="/api-docs/" target="_blank" rel="noopener" :class="['mt-3 inline-block', btn]">
          Ouvrir la documentation ↗
        </a>
      </div>
    </section>

    <!-- Clé fraîchement créée : affichée une seule fois -->
    <AppModal
      :open="createdKey !== null"
      title="Clé d’API créée"
      subtitle="Copiez-la maintenant : elle ne sera plus jamais affichée."
      size="md"
      level="top"
      @close="createdKey = null"
    >
      <div v-if="createdKey" class="space-y-4">
        <div class="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
          <p class="text-xs text-slate-500 dark:text-slate-400">{{ createdKey.api_key.label }}</p>
          <code class="mt-1 block break-all font-mono text-sm text-slate-800 dark:text-slate-100">
            {{ createdKey.key }}
          </code>
        </div>
        <div>
          <p class="text-xs font-medium text-slate-500 dark:text-slate-400">Exemple d’appel</p>
          <pre class="mt-1 overflow-x-auto rounded-lg bg-slate-900 px-3 py-2 text-xs text-slate-100"><code>{{ curlExample }}</code></pre>
        </div>
      </div>

      <template #footer>
        <AppButton variant="secondary" @click="createdKey = null">Fermer</AppButton>
        <AppButton variant="primary" @click="copyKey">Copier la clé</AppButton>
      </template>
    </AppModal>

    <ItemFormModal
      :open="showForm && canWrite()"
      :item="editing"
      :enums="enums"
      @close="showForm = false"
      @create="onCreate"
      @update="onUpdate"
      @remove="onRemove"
    />
  </div>
</template>
