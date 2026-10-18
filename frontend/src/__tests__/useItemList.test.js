import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useItemList } from '../composables/useItemList'
import { api } from '../api'

vi.mock('../api', () => ({
  api: {
    listItems: vi.fn(),
    createItem: vi.fn(),
    updateItem: vi.fn(),
    deleteItem: vi.fn(),
    bulk: vi.fn(),
    addLink: vi.fn(),
    uploadPhoto: vi.fn(),
  },
}))

function makeItem(overrides = {}) {
  return {
    id: 1,
    name: 'Rafale',
    item_type: 'DIECAST',
    status: 'STORED_BOX',
    tags: [],
    photos: [],
    links: [],
    price_points: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useItemList — chargement', () => {
  it('remplit la liste et le total', async () => {
    api.listItems.mockResolvedValue({ items: [makeItem()], total: 1 })
    const list = useItemList()
    await list.load()

    expect(list.items.value).toHaveLength(1)
    expect(list.total.value).toBe(1)
    expect(list.error.value).toBe('')
  })

  it('expose l’erreur sans jeter', async () => {
    api.listItems.mockRejectedValue(new Error('réseau indisponible'))
    const list = useItemList()
    await list.load()
    expect(list.error.value).toBe('réseau indisponible')
  })
})

describe('useItemList — création optimiste', () => {
  it('affiche l’objet aussitôt, puis le remplace par la réponse serveur', async () => {
    const refreshStats = vi.fn()
    api.createItem.mockResolvedValue(makeItem({ id: 42, name: 'Mirage' }))
    const list = useItemList({ refreshStats })

    const promise = list.create({ name: 'Mirage', item_type: 'DIECAST' })
    // Mutation locale visible avant la réponse du serveur.
    expect(list.items.value[0].name).toBe('Mirage')
    expect(list.items.value[0]._optimistic).toBe(true)
    expect(list.total.value).toBe(1)

    await promise
    expect(list.items.value[0].id).toBe(42)
    expect(list.items.value[0]._optimistic).toBeUndefined()
    expect(refreshStats).toHaveBeenCalled()
  })

  it('annule la création si le serveur refuse', async () => {
    api.createItem.mockRejectedValue(new Error('nom déjà pris'))
    const list = useItemList({ refreshStats: vi.fn() })

    const result = await list.create({ name: 'Doublon', item_type: 'DIECAST' })

    expect(result.ok).toBe(false)
    expect(list.items.value).toHaveLength(0)
    expect(list.total.value).toBe(0)
  })
})

describe('useItemList — modification et suppression', () => {
  beforeEach(async () => {
    api.listItems.mockResolvedValue({ items: [makeItem({ id: 1 }), makeItem({ id: 2 })], total: 2 })
  })

  it('applique une modification puis la réconcilie', async () => {
    api.updateItem.mockResolvedValue(makeItem({ id: 1, name: 'Rafale M' }))
    const list = useItemList()
    await list.load()

    await list.update(1, { name: 'Rafale M' })
    expect(list.items.value.find((i) => i.id === 1).name).toBe('Rafale M')
  })

  it('restaure l’état précédent si la modification échoue', async () => {
    api.updateItem.mockRejectedValue(new Error('refus'))
    const list = useItemList()
    await list.load()
    const before = list.items.value.find((i) => i.id === 1).name

    await list.update(1, { name: 'Nouveau' })
    expect(list.items.value.find((i) => i.id === 1).name).toBe(before)
  })

  it('supprime immédiatement et réinsère en cas d’échec', async () => {
    api.deleteItem.mockRejectedValue(new Error('refus'))
    const list = useItemList()
    await list.load()

    const promise = list.remove(1)
    expect(list.items.value.find((i) => i.id === 1)).toBeUndefined()
    expect(list.total.value).toBe(1)

    await promise
    expect(list.items.value.find((i) => i.id === 1)).toBeDefined()
    expect(list.total.value).toBe(2)
  })

  it('change un statut de façon optimiste', async () => {
    api.updateItem.mockResolvedValue(makeItem({ id: 2, status: 'EXHIBITED' }))
    const list = useItemList()
    await list.load()

    await list.setStatus(2, 'EXHIBITED')
    expect(list.items.value.find((i) => i.id === 2).status).toBe('EXHIBITED')
    expect(api.updateItem).toHaveBeenCalledWith(2, { status: 'EXHIBITED' })
  })
})

describe('useItemList — actions groupées', () => {
  it('supprime plusieurs objets et rafraîchit les agrégats', async () => {
    api.listItems.mockResolvedValue({ items: [makeItem({ id: 1 }), makeItem({ id: 2 })], total: 2 })
    api.bulk.mockResolvedValue({ action: 'delete', affected: 2 })
    const refreshStats = vi.fn()
    const list = useItemList({ refreshStats })
    await list.load()

    await list.bulk([1, 2], 'delete')
    expect(list.items.value).toHaveLength(0)
    expect(list.total.value).toBe(0)
    expect(refreshStats).toHaveBeenCalled()
  })
})
