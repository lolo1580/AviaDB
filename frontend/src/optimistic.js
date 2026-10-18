import { computed, reactive } from 'vue'
import { toast } from './toast'

/**
 * Registre des opérations serveur en cours.
 *
 * Chaque opération s'enregistre sous une clé stable (ex. `item:12`), ce qui
 * permet aux composants d'afficher un indicateur au bon endroit :
 *
 *     isPending(`item:${item.id}`)
 *
 * Le nombre d'opérations est compté par clé : deux requêtes simultanées sur le
 * même objet ne se masquent pas mutuellement.
 */
export const pending = reactive({})

export function isPending(key) {
  return Boolean(pending[key])
}

export const pendingCount = computed(() =>
  Object.values(pending).reduce((total, count) => total + count, 0),
)

export const anyPending = computed(() => pendingCount.value > 0)

function acquire(key) {
  pending[key] = (pending[key] || 0) + 1
}

function release(key) {
  if (!pending[key]) return
  pending[key] -= 1
  if (pending[key] <= 0) delete pending[key]
}

// --------------------------------------------------------------------------- #
// Identifiants temporaires
// --------------------------------------------------------------------------- #
let sequence = 0

/** Identifiant local, en attendant celui du serveur. */
export function tempId(prefix = 'temp') {
  sequence += 1
  return `${prefix}-${Date.now().toString(36)}-${sequence}`
}

export function isTempId(id) {
  return typeof id === 'string' && id.startsWith('temp-')
}

// --------------------------------------------------------------------------- #
// Action optimiste
// --------------------------------------------------------------------------- #
/**
 * Applique une mutation locale, lance la requête, et **annule la mutation** si
 * le serveur refuse.
 *
 * @param {string}   key       clé du registre (indicateur de chargement)
 * @param {string}   label     libellé utilisé dans le message d'erreur
 * @param {Function} apply     mutation immédiate ; renvoie la fonction d'annulation
 * @param {Function} request   appel serveur
 * @param {Function} onSuccess réconciliation avec la réponse serveur
 * @param {Function} retry     relance la même opération (bouton « Réessayer »)
 * @param {boolean}  silence   ne rien notifier en cas d'échec
 */
export async function optimistic({
  key,
  label = 'Action',
  apply,
  request,
  onSuccess,
  retry,
  silence = false,
}) {
  const rollback = typeof apply === 'function' ? apply() : undefined
  acquire(key)

  try {
    const data = await request()
    if (onSuccess) await onSuccess(data)
    return { ok: true, data }
  } catch (error) {
    try {
      rollback?.()
    } catch {
      /* une annulation défaillante ne doit pas masquer l'erreur d'origine */
    }
    if (!silence) {
      toast.error(`${label} annulée — ${error.message}`, {
        action: retry ? { label: 'Réessayer', run: retry } : null,
      })
    }
    return { ok: false, error }
  } finally {
    release(key)
  }
}
