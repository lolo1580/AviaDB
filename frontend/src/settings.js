import { reactive } from 'vue'
import { api } from './api'

// Réglages monétaires partagés : devise de référence, devises disponibles et
// taux courants (convention BCE : 1 EUR = X).
export const settings = reactive({
  loaded: false,
  default_currency: 'EUR',
  currencies: [],
  rates: {},
  rates_updated_at: null,
  rates_source: null,
})

export async function loadSettings() {
  try {
    Object.assign(settings, await api.getSettings(), { loaded: true })
  } catch {
    /* On conserve les valeurs par défaut (EUR) si l'appel échoue. */
  }
}

export async function saveBaseCurrency(code) {
  Object.assign(settings, await api.updateSettings(code))
}

export async function saveRates(rates) {
  Object.assign(settings, await api.updateRates(rates))
}

export async function refreshRates() {
  Object.assign(settings, await api.refreshRates())
}

export function currencyLabel(code) {
  return settings.currencies.find((option) => option.code === code)?.label || code || ''
}

/** Convertit un montant de `currency` vers la devise de référence. */
export function toBase(value, currency) {
  if (value === null || value === undefined) return null
  const source = (currency || settings.default_currency).toUpperCase()
  const rateSource = settings.rates?.[source]
  const rateBase = settings.rates?.[settings.default_currency]
  if (!rateSource || !rateBase) return value
  return (value / rateSource) * rateBase
}

/** Taux affiché « 1 <code> = X <devise de référence> ». */
export function rateInBase(code) {
  const rate = settings.rates?.[code]
  const base = settings.rates?.[settings.default_currency]
  if (!rate || !base) return null
  return base / rate
}
