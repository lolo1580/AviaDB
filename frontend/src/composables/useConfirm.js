import { reactive } from 'vue'

/**
 * Confirmations asynchrones, sur le même socle que les modales.
 *
 * Usage :
 *   const ok = await confirm({ title: 'Supprimer ?', message: '…', danger: true })
 *   if (ok) …
 *
 * Une troisième issue est possible via `alternateLabel` (ex. « Fusionner » à côté
 * de « Remplacer ») : la promesse résout alors 'confirm', 'alternate' ou false.
 */
export const confirmState = reactive({
  open: false,
  options: {},
  resolve: null,
})

export function confirm(options) {
  const normalized = typeof options === 'string' ? { message: options } : { ...options }
  return new Promise((resolve) => {
    confirmState.options = normalized
    confirmState.resolve = resolve
    confirmState.open = true
  })
}

export function settleConfirm(result) {
  const { resolve } = confirmState
  confirmState.open = false
  confirmState.resolve = null
  const options = confirmState.options
  confirmState.options = {}
  if (resolve) resolve(result)
  return options
}
