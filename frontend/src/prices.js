import { formatMoney } from './labels'
import { settings, toBase } from './settings'

/**
 * Relevés de prix d'un objet.
 *
 * Ils sont toujours triés par date croissante côté API. Les calculs passent par
 * l'équivalent EUR figé au moment du relevé (ou l'équivalent courant si absent),
 * puis sont exprimés dans la devise de référence — la courbe reste donc cohérente
 * même si les relevés ont été faits dans plusieurs devises.
 */

export function pricePoints(item) {
  return item?.price_points || []
}

/** Valeur d'un relevé ramenée dans la devise de référence. */
export function valueInBase(point) {
  if (!point) return null
  if (point.eur_value != null) return toBase(point.eur_value, 'EUR')
  return toBase(point.price, point.currency)
}

export function latestPrice(item) {
  const points = pricePoints(item)
  return points.length ? points[points.length - 1] : null
}

export function previousPrice(item) {
  const points = pricePoints(item)
  return points.length > 1 ? points[points.length - 2] : null
}

/** Variation en pourcentage entre les deux derniers relevés, ou null. */
export function priceVariation(item) {
  const last = latestPrice(item)
  const before = previousPrice(item)
  if (!last || !before) return null
  const from = valueInBase(before)
  const to = valueInBase(last)
  if (!from || !to) return null
  return ((to - from) / from) * 100
}

/** Résumé prêt à afficher : « 45,00 € · ▼ 8 % ». */
export function priceSummary(item) {
  const last = latestPrice(item)
  if (!last) return null
  const variation = priceVariation(item)
  return {
    label: formatMoney(last.price, last.currency),
    date: last.recorded_on,
    variation,
    trend: variation === null ? null : variation < 0 ? 'down' : variation > 0 ? 'up' : 'flat',
  }
}

/** Série pour le graphique : { label, value } dans la devise de référence. */
export function chartSeries(item) {
  const base = settings.default_currency
  return pricePoints(item)
    .map((point) => ({ label: point.recorded_on, value: valueInBase(point) }))
    .filter((entry) => entry.value !== null && entry.value !== undefined)
    .map((entry) => ({ ...entry, currency: base }))
}

/**
 * Alerte de budget d'une pièce recherchée : le dernier relevé est-il au niveau
 * ou en dessous du budget visé (`estimated_value`) ? Renvoie null sinon.
 *
 * Les deux montants sont ramenés dans la devise de référence avant comparaison.
 */
export function budgetAlert(item) {
  const target = toBase(item?.estimated_value, item?.currency)
  const last = latestPrice(item)
  if (target == null || target <= 0 || !last) return null

  const price = valueInBase(last)
  if (price == null || price > target) return null

  return {
    target,
    price,
    saving: target - price,
    percent: ((target - price) / target) * 100,
    date: last.recorded_on,
  }
}
