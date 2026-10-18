import { reactive } from 'vue'
import { api } from './api'

// État d'authentification partagé par toute l'application.
// `enabled` : l'accès est-il protégé (au moins un compte existe) ?
// `authenticated` : la session courante est-elle valide ?
// `role` : 'ADMIN' (écriture) ou 'VIEWER' (lecture seule).
export const auth = reactive({
  enabled: false,
  authenticated: false,
  username: null,
  role: null,
  checked: false,
})

export async function refreshSession() {
  try {
    const session = await api.session()
    auth.enabled = session.enabled
    auth.authenticated = session.authenticated
    auth.username = session.username
    auth.role = session.role
  } catch {
    auth.enabled = false
    auth.authenticated = false
    auth.username = null
    auth.role = null
  } finally {
    auth.checked = true
  }
}

export async function login(username, password) {
  await api.login(username, password)
  await refreshSession()
}

export async function logout() {
  await api.logout()
  await refreshSession()
}

/** L'écriture est-elle autorisée dans la session courante ? */
export function canWrite() {
  return !auth.enabled || auth.role === 'ADMIN'
}

/** Le compte courant est-il administrateur ? */
export function isAdmin() {
  return !auth.enabled || auth.role === 'ADMIN'
}
