import { reactive } from 'vue'

// Préférences d'interface persistées : repli de la barre latérale, tiroir mobile,
// mode d'affichage des listes et onglet d'administration courant.
const STORAGE_KEY = 'aviadb-ui'

export const ADMIN_TABS = ['items', 'tags', 'classes', 'currencies', 'users', 'api', 'journal', 'backup']

export const ui = reactive({
  sidebarCollapsed: false,
  mobileOpen: false,
  viewMode: 'grid', // 'grid' | 'list'
  adminTab: 'items',
})

function persist() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        sidebarCollapsed: ui.sidebarCollapsed,
        viewMode: ui.viewMode,
        adminTab: ui.adminTab,
      }),
    )
  } catch {
    /* stockage indisponible : on garde les valeurs en mémoire */
  }
}

export function initUi() {
  let stored
  try {
    stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    stored = null
  }
  if (stored && typeof stored === 'object') {
    ui.sidebarCollapsed = Boolean(stored.sidebarCollapsed)
    ui.viewMode = stored.viewMode === 'list' ? 'list' : 'grid'
    if (ADMIN_TABS.includes(stored.adminTab)) ui.adminTab = stored.adminTab
  }
  // Sur petit écran, la barre latérale est un tiroir : jamais ouverte au départ.
  ui.mobileOpen = false
}

export function setAdminTab(tab) {
  if (!ADMIN_TABS.includes(tab)) return
  ui.adminTab = tab
  persist()
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
