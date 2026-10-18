import { auth } from '../auth'

/**
 * Source unique de vérité pour la navigation latérale.
 * `adminOnly` masque l'entrée aux comptes en lecture seule.
 */
export const navItems = [
  { name: 'collection', to: '/', icon: 'collection', label: 'Collection', title: 'Collection' },
  { name: 'wishlist', to: '/souhaits', icon: 'wishlist', label: 'Souhaits', title: 'Liste de souhaits' },
  { name: 'charts', to: '/statistiques', icon: 'charts', label: 'Statistiques', title: 'Statistiques' },
  { name: 'admin', to: '/admin', icon: 'admin', label: 'Administration', title: 'Administration' },
]

/** Entrées visibles pour la session courante. */
export function visibleNavItems() {
  return navItems.filter((item) => !item.adminOnly || auth.role === 'ADMIN')
}

export function isActiveRoute(item, currentPath) {
  if (item.to === '/') return currentPath === '/'
  return currentPath === item.to || currentPath.startsWith(`${item.to}/`)
}
