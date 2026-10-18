import { describe, it, expect, beforeEach } from 'vitest'
import { settings, toBase, rateInBase, currencyLabel } from '../settings'

beforeEach(() => {
  settings.default_currency = 'EUR'
  settings.currencies = [
    { code: 'EUR', label: 'Euro' },
    { code: 'USD', label: 'Dollar américain' },
  ]
  settings.rates = { EUR: 1, USD: 1.25 }
})

describe('settings', () => {
  it('convertit un montant vers la devise de référence', () => {
    expect(toBase(125, 'USD')).toBeCloseTo(100, 6)
    expect(toBase(50, 'EUR')).toBeCloseTo(50, 6)
  })

  it('renvoie la valeur telle quelle sans taux connu', () => {
    expect(toBase(42, 'GBP')).toBe(42)
  })

  it('conserve null pour une valeur absente', () => {
    expect(toBase(null, 'USD')).toBeNull()
    expect(toBase(undefined, 'USD')).toBeNull()
  })

  it('calcule le taux affiché en devise de référence', () => {
    expect(rateInBase('USD')).toBeCloseTo(0.8, 6)
  })

  it('libelle une devise, avec repli sur le code', () => {
    expect(currencyLabel('USD')).toBe('Dollar américain')
    expect(currencyLabel('JPY')).toBe('JPY')
  })
})
