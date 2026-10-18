import { reactive } from 'vue'

/**
 * Saisie asynchrone, sur le même socle que les modales.
 *
 * Usage :
 *   const nom = await prompt({ title: 'Renommer', label: 'Nouveau nom', value: ancien })
 *   if (nom === null) return            // annulé
 *
 * Options : title, subtitle, label, value, placeholder, type, required,
 * minLength, maxLength, multiline, confirmLabel, cancelLabel, validate(v).
 * La promesse résout la chaîne saisie, ou `null` si l'utilisateur annule.
 */
export const promptState = reactive({
  open: false,
  options: {},
  resolve: null,
})

export function prompt(options) {
  const normalized = typeof options === 'string' ? { title: options } : { ...options }
  return new Promise((resolve) => {
    promptState.options = normalized
    promptState.resolve = resolve
    promptState.open = true
  })
}

export function settlePrompt(value) {
  const { resolve } = promptState
  promptState.open = false
  promptState.resolve = null
  const options = promptState.options
  promptState.options = {}
  if (resolve) resolve(value)
  return options
}
