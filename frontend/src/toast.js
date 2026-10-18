import { reactive } from 'vue'
import { pushNotification } from './notifications'

// File de notifications. Sert notamment à expliquer un rollback optimiste
// (« Modification annulée — ... ») et à proposer l'annulation d'une action
// réversible (statut, tags).
// Chaque message alimente aussi le centre de notifications de la barre du haut.
export const toasts = reactive([])

let sequence = 0

export function pushToast({ type = 'info', message, timeout = 5000, action = null }) {
  const id = ++sequence
  toasts.push({ id, type, message, action })
  pushNotification({ type, message })
  if (timeout) {
    setTimeout(() => dismissToast(id), timeout)
  }
  return id
}

export function dismissToast(id) {
  const index = toasts.findIndex((entry) => entry.id === id)
  if (index !== -1) toasts.splice(index, 1)
}

function runAction(toast) {
  dismissToast(toast.id)
  try {
    toast.action?.run?.()
  } catch {
    /* l'annulation ne doit jamais casser l'interface */
  }
}

export const toast = {
  success: (message, options) => pushToast({ type: 'success', message, ...options }),
  info: (message, options) => pushToast({ type: 'info', message, ...options }),
  error: (message, options) => pushToast({ type: 'error', message, timeout: 8000, ...options }),
  runAction,
}
