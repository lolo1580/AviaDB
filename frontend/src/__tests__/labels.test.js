import { describe, it, expect } from 'vitest'
import { formatMoney, TYPE_LABEL, STATUS_LABEL } from '../labels'

describe('labels', () => {
  it('expose les libellés métier', () => {
    expect(TYPE_LABEL.DIECAST).toBe('Maquette')
    expect(STATUS_LABEL.WANTED).toBe('Recherché')
  })

  it('formate un montant en devise', () => {
    // Espace insécable utilisé par Intl en fr-FR.
    expect(formatMoney(1234.5, 'EUR')).toMatch(/1[\s\u202f]234,50/)
  })

  it('renvoie null pour une valeur absente', () => {
    expect(formatMoney(null)).toBeNull()
    expect(formatMoney(undefined)).toBeNull()
    expect(formatMoney('')).toBeNull()
  })

  it('retombe sur un format simple si la devise est inconnue', () => {
    expect(formatMoney(10, 'ZZZ')).toContain('ZZZ')
  })
})
