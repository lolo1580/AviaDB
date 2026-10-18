import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ItemCard from '../components/ItemCard.vue'
import { classes } from '../classes'

function makeItem(overrides = {}) {
  return {
    id: 1,
    name: 'Rafale',
    item_type: 'DIECAST',
    status: 'EXHIBITED',
    country: 'France',
    aircraft_model: 'Rafale',
    storage_location: 'Vitrine',
    class_id: null,
    estimated_value: 120,
    currency: 'EUR',
    diecast: { scale: '1/72', manufacturer: 'Hobby Master' },
    patch: null,
    tags: [],
    photos: [],
    links: [],
    price_points: [],
    ...overrides,
  }
}

beforeEach(() => {
  classes.list = []
})

describe('ItemCard', () => {
  it('affiche le nom, le type, le statut et la valeur', () => {
    const wrapper = mount(ItemCard, { props: { item: makeItem() } })
    const text = wrapper.text()
    expect(text).toContain('Rafale')
    expect(text).toContain('Maquette')
    expect(text).toContain('Exposé')
    expect(text).toMatch(/120,00/)
    expect(text).toContain('France')
    expect(text).toContain('1/72')
  })

  it('émet « edit » au clic sur la vignette', async () => {
    const item = makeItem()
    const wrapper = mount(ItemCard, { props: { item } })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('edit')[0][0]).toStrictEqual(item)
  })

  it('affiche le chemin de classe', () => {
    classes.list = [
      { id: 1, name: 'Aéronefs', parent_id: null, position: 0, item_count: 1 },
      { id: 2, name: 'Chasseur', parent_id: 1, position: 0, item_count: 1 },
    ]
    const wrapper = mount(ItemCard, { props: { item: makeItem({ class_id: 2 }) } })
    expect(wrapper.text()).toContain('Aéronefs › Chasseur')
  })
})
