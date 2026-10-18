import { computed, reactive } from 'vue'

// Centre de notifications alimenté par les messages de l'application.
// Les succès y figurent pour l'historique mais ne comptent pas comme non lus :
// seuls les échecs et les informations méritent l'attention.
export const notifications = reactive([])

const MAX_ENTRIES = 30
let sequence = 0

export function pushNotification({ type = 'info', message }) {
  sequence += 1
  notifications.unshift({
    id: sequence,
    type,
    message,
    at: Date.now(),
    read: type === 'success',
  })
  if (notifications.length > MAX_ENTRIES) notifications.splice(MAX_ENTRIES)
}

export const unreadCount = computed(() => notifications.filter((entry) => !entry.read).length)

export function markAllRead() {
  notifications.forEach((entry) => {
    entry.read = true
  })
}

export function clearNotifications() {
  notifications.splice(0)
}

/** « il y a 3 min » — sans librairie de dates. */
export function relativeTime(timestamp) {
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000))
  if (seconds < 60) return "à l'instant"
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `il y a ${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `il y a ${hours} h`
  const days = Math.round(hours / 24)
  return `il y a ${days} j`
}
