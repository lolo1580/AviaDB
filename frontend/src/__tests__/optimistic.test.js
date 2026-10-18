import { describe, it, expect, vi, beforeEach } from 'vitest'
import { optimistic, pending, isPending, pendingCount, anyPending, tempId, isTempId } from '../optimistic'
import { toast } from '../toast'

beforeEach(() => {
  for (const key of Object.keys(pending)) delete pending[key]
})

describe('optimistic — identifiants temporaires', () => {
  it('génère des identifiants uniques préfixés', () => {
    const a = tempId('item')
    const b = tempId('item')
    expect(a).not.toBe(b)
    expect(a.startsWith('item-')).toBe(true)
  })

  it('reconnaît un identifiant temporaire', () => {
    expect(isTempId(tempId('tag'))).toBe(true)
    expect(isTempId(12)).toBe(false)
    expect(isTempId('item-real')).toBe(false)
  })
})

describe('optimistic — exécution', () => {
  it('applique la mutation et réconcilie en cas de succès', async () => {
    const apply = vi.fn(() => vi.fn())
    const request = vi.fn().mockResolvedValue({ id: 1 })
    const onSuccess = vi.fn()

    const result = await optimistic({ key: 'item:1', apply, request, onSuccess })

    expect(result).toEqual({ ok: true, data: { id: 1 } })
    expect(apply).toHaveBeenCalledOnce()
    expect(onSuccess).toHaveBeenCalledWith({ id: 1 })
    expect(pendingCount.value).toBe(0)
  })

  it('annule la mutation et notifie en cas d’échec', async () => {
    const rollback = vi.fn()
    const error = new Error('boom')
    const spy = vi.spyOn(toast, 'error')

    const result = await optimistic({
      key: 'item:1',
      label: 'Modification',
      apply: () => rollback,
      request: () => Promise.reject(error),
    })

    expect(result.ok).toBe(false)
    expect(result.error).toBe(error)
    expect(rollback).toHaveBeenCalledOnce()
    expect(spy).toHaveBeenCalledOnce()
    expect(spy.mock.calls[0][0]).toContain('Modification annulée')
  })

  it('propose de réessayer et reste silencieux si demandé', async () => {
    const retry = vi.fn()
    const spy = vi.spyOn(toast, 'error')

    await optimistic({
      key: 'bulk',
      label: 'Action groupée',
      request: () => Promise.reject(new Error('nope')),
      retry,
      silence: true,
    })

    expect(spy).not.toHaveBeenCalled()
  })

  it('ne masque pas une annulation défaillante', async () => {
    const result = await optimistic({
      key: 'item:1',
      apply: () => () => {
        throw new Error('rollback cassé')
      },
      request: () => Promise.reject(new Error('origine')),
      silence: true,
    })
    expect(result.ok).toBe(false)
    expect(result.error.message).toBe('origine')
  })
})

describe('optimistic — registre des opérations en cours', () => {
  it('compte les opérations par clé, puis les libère', async () => {
    let resolve
    const promise = new Promise((r) => (resolve = r))
    const running = optimistic({ key: 'item:9', request: () => promise })

    expect(isPending('item:9')).toBe(true)
    expect(isPending('item:8')).toBe(false)
    expect(pendingCount.value).toBe(1)
    expect(anyPending.value).toBe(true)

    resolve('ok')
    await running

    expect(isPending('item:9')).toBe(false)
    expect(pendingCount.value).toBe(0)
    expect(anyPending.value).toBe(false)
  })

  it('ne confond pas deux requêtes simultanées sur la même clé', async () => {
    let resolveA
    let resolveB
    const runningA = optimistic({ key: 'item:1', request: () => new Promise((r) => (resolveA = r)) })
    const runningB = optimistic({ key: 'item:1', request: () => new Promise((r) => (resolveB = r)) })

    expect(pending['item:1']).toBe(2)
    resolveA('a')
    await runningA
    expect(pending['item:1']).toBe(1)
    resolveB('b')
    await runningB
    expect(isPending('item:1')).toBe(false)
  })
})
