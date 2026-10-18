import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import FilterBar from '../components/FilterBar.vue'
import { classes } from '../classes'

function setup() {
  classes.list = []
  const filters = reactive({
    q: '',
    item_type: [],
    status: [],
    country: [],
    scale: [],
    manufacturer: [],
    tag: [],
    class_id: '',
    sort: 'name',
    order: 'asc',
  })
  const facets = {
    countries: ['France', 'États-Unis'],
    aircraft_models: [],
    storage_locations: [],
    scales: ['1/72'],
    manufacturers: ['Hobby Master'],
    tags: ['dassault'],
  }
  const enums = {
    item_types: ['DIECAST', 'PATCH'],
    statuses: ['EXHIBITED', 'WANTED'],
    materials: [],
    attachment_types: [],
    shapes: [],
  }
  const wrapper = mount(FilterBar, { props: { filters, facets, enums, total: 3 } })
  return { wrapper, filters }
}

describe('FilterBar', () => {
  it('met à jour le filtre pays (tableau, un seul choix)', async () => {
    const { wrapper, filters } = setup()
    // Le premier <select> est la liste des pays.
    await wrapper.find('select').setValue('France')
    expect(filters.country).toEqual(['France'])
    await wrapper.find('select').setValue('')
    expect(filters.country).toEqual([])
  })

  it('bascule l’ordre de tri', async () => {
    const { wrapper, filters } = setup()
    const orderButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Croissant'))
    await orderButton.trigger('click')
    expect(filters.order).toBe('desc')
  })

  it('réinitialise tous les filtres', async () => {
    const { wrapper, filters } = setup()
    filters.country = ['France']
    filters.q = 'rafale'
    const reset = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Réinitialiser'))
    await reset.trigger('click')
    expect(filters.country).toEqual([])
    expect(filters.q).toBe('')
    expect(filters.order).toBe('asc')
  })
})
