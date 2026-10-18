import { describe, it, expect, beforeEach } from 'vitest'
import { settings } from '../settings'
import {
  pricePoints,
  valueInBase,
  latestPrice,
  previousPrice,
  priceVariation,
  priceSummary,
  chartSeries,
  budgetAlert,
} from '../prices'

const item = {
  price_points: [
    { price: 100, currency: 'USD', eur_value: 80, recorded_on: '2024-01-01' },
    { price: 110, currency: 'USD', eur_value: 90, recorded_on: '2024-02-01' },
  ],
}

beforeEach(() => {
  settings.default_currency = 'EUR'
  settings.rates = { EUR: 1, USD: 1.25 }
})

describe('prices', () => {
  it('liste les relevés, avec repli sur un tableau vide', () => {
    expect(pricePoints(item)).toHaveLength(2)
    expect(pricePoints({})).toEqual([])
    expect(pricePoints(null)).toEqual([])
  })

  it('exprime un relevé dans la devise de référence', () => {
    // eur_value figé prioritaire.
    expect(valueInBase(item.price_points[0])).toBeCloseTo(80, 6)
    // sans équivalent EUR : conversion via le taux courant.
    expect(valueInBase({ price: 125, currency: 'USD' })).toBeCloseTo(100, 6)
    expect(valueInBase(null)).toBeNull()
  })

  it('distingue le dernier et l’avant-dernier relevé', () => {
    expect(latestPrice(item).recorded_on).toBe('2024-02-01')
    expect(previousPrice(item).recorded_on).toBe('2024-01-01')
    expect(previousPrice({ price_points: [item.price_points[0]] })).toBeNull()
  })

  it('calcule la variation en pourcentage', () => {
    expect(priceVariation(item)).toBeCloseTo(12.5, 6)
    expect(priceVariation({ price_points: [] })).toBeNull()
  })

  it('produit un résumé avec tendance', () => {
    const summary = priceSummary(item)
    expect(summary.date).toBe('2024-02-01')
    expect(summary.trend).toBe('up')
    expect(summary.label).toContain('110')
    expect(priceSummary({ price_points: [] })).toBeNull()
  })

  it('prépare la série du graphique dans la devise de référence', () => {
    const series = chartSeries(item)
    expect(series.map((p) => p.value)).toEqual([80, 90])
    expect(series.every((p) => p.currency === 'EUR')).toBe(true)
  })
})

describe('prices — alerte de budget', () => {
  const wanted = (estimated, points) => ({
    estimated_value: estimated,
    currency: 'EUR',
    price_points: points,
  })
  const point = (eur, date = '2024-03-01') => ({
    price: eur,
    currency: 'EUR',
    eur_value: eur,
    recorded_on: date,
  })

  it('déclenche quand le dernier relevé est sous le budget', () => {
    const alert = budgetAlert(wanted(100, [point(80)]))
    expect(alert.price).toBeCloseTo(80, 6)
    expect(alert.saving).toBeCloseTo(20, 6)
    expect(alert.percent).toBeCloseTo(20, 6)
    expect(alert.date).toBe('2024-03-01')
  })

  it('se déclenche aussi à égalité', () => {
    expect(budgetAlert(wanted(100, [point(100)]))).not.toBeNull()
  })

  it('ne déclenche pas au-dessus du budget', () => {
    expect(budgetAlert(wanted(100, [point(120)]))).toBeNull()
  })

  it('ne déclenche pas sans budget ni sans relevé', () => {
    expect(budgetAlert(wanted(null, [point(10)]))).toBeNull()
    expect(budgetAlert(wanted(100, []))).toBeNull()
    expect(budgetAlert(null)).toBeNull()
  })

  it('compare dans la devise de référence', () => {
    // Budget saisi en USD (100 USD = 80 EUR), relevé à 75 EUR.
    const alert = budgetAlert({
      estimated_value: 100,
      currency: 'USD',
      price_points: [point(75)],
    })
    expect(alert.target).toBeCloseTo(80, 6)
    expect(alert.saving).toBeCloseTo(5, 6)
  })
})
