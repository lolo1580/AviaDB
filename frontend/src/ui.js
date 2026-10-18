import { reactive } from 'vue'

// Préférences d'interface persistées : repli de la barre latérale, tiroir mobile
// et mode d'affichage des listes.
const STORAGE_KEY = 'aviadb-ui'

export const ui = reactive({
  sidebarCollapsed: false,
  mobileOpen: false,
  viewMode: 'grid', // 'grid' | 'list'
})

function persist() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ sidebarCollapsed: ui.sidebarCollapsed, viewMode: ui.viewMode }),
    )
  } catch {
    /* stockage indisponible : on garde les valeurs en mémoire */
  }
}

export function initUi() {
  let stored = null
  try {
    stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    stored = null
  }
  if (stored && typeof stored === 'object') {
    ui.sidebarCollapsed = Boolean(stored.sidebarCollapsed)
    ui.viewMode = stored.viewMode === 'list' ? 'list' : 'grid'
  }
  // Sur petit écran, la barre latérale est un tiroir : jamais ouverte au départ.
  ui.mobileOpen = false
}

export function toggleSidebar() {
  ui.sidebarCollapsed = !ui.sidebarCollapsed
  persist()
}

export function openMobileSidebar() {
  ui.mobileOpen = true
}

export function closeMobileSidebar() {
  ui.mobileOpen = false
}

export function setViewMode(mode) {
  ui.viewMode = mode === 'list' ? 'list' : 'grid'
  persist()
}
