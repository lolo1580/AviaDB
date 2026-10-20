import { test, expect } from '@playwright/test'

// Parcours de fumée : l'application se charge et affiche la collection.
// Toutes les réponses API sont simulées, l'application est en mode « non
// protégé » (aucun compte) pour éviter l'écran de connexion.

const EMPTY_STATS = {
  total_items: 1,
  total_photos: 0,
  base_currency: 'EUR',
  rates_updated_at: null,
  total_estimated_value: 120,
  total_purchase_value: 100,
  items_with_estimated_value: 1,
  by_type: [{ key: 'DIECAST', count: 1 }],
  by_status: [{ key: 'EXHIBITED', count: 1 }],
  by_country: [{ key: 'France', count: 1 }],
  by_currency: [{ key: 'EUR', count: 1 }],
  by_scale: [{ key: '1/72', count: 1 }],
  by_manufacturer: [{ key: 'Hobby Master', count: 1 }],
  by_material: [],
  by_class: [],
  by_year: [{ key: '2024', count: 1 }],
  value_by_country: [{ key: 'France', value: 120 }],
  value_by_class: [],
  value_by_location: [],
  value_by_year: [{ key: '2024', value: 100 }],
  top_gains: [{ id: 1, name: 'Rafale', estimated_value: 120, purchase_value: 100, gain: 20 }],
  top_losses: [],
}

const ITEM = {
  id: 1,
  name: 'Rafale',
  item_type: 'DIECAST',
  status: 'EXHIBITED',
  country: 'France',
  aircraft_model: 'Rafale',
  storage_location: 'Vitrine',
  estimated_value: 120,
  currency: 'EUR',
  diecast: { scale: '1/72', manufacturer: 'Hobby Master' },
  patch: null,
  tags: [],
  photos: [],
  links: [],
  price_points: [],
}

async function stubApi(page) {
  await page.route('**/api/admin/session', (route) =>
    route.fulfill({ json: { enabled: false, authenticated: false, username: null, role: null } }),
  )
  await page.route('**/api/meta/settings', (route) =>
    route.fulfill({
      json: {
        default_currency: 'EUR',
        currencies: [{ code: 'EUR', label: 'Euro' }],
        rates: { EUR: 1 },
        rates_updated_at: null,
        rates_source: null,
      },
    }),
  )
  await page.route('**/api/classes', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/stats', (route) => route.fulfill({ json: EMPTY_STATS }))
  await page.route('**/api/meta/facets', (route) =>
    route.fulfill({
      json: {
        countries: ['France'],
        aircraft_models: [],
        storage_locations: ['Vitrine'],
        scales: ['1/72'],
        manufacturers: ['Hobby Master'],
        tags: [],
      },
    }),
  )
  await page.route('**/api/meta/enums', (route) =>
    route.fulfill({
      json: {
        item_types: ['DIECAST', 'PATCH', 'OTHER'],
        statuses: ['EXHIBITED', 'STORED_BOX', 'WANTED', 'TRANSIT'],
        materials: [],
        attachment_types: [],
        shapes: [],
      },
    }),
  )
  await page.route('**/api/items**', (route) =>
    route.fulfill({ json: { total: 1, items: [ITEM] } }),
  )
}

test('la collection s’affiche', async ({ page }) => {
  await stubApi(page)
  await page.goto('/')

  const main = page.locator('main')
  await expect(main.getByRole('heading', { name: /Collection/ })).toBeVisible()
  await expect(page.getByText('Rafale').first()).toBeVisible()
})

test('la navigation mène aux statistiques', async ({ page }) => {
  await stubApi(page)
  await page.goto('/')
  await page.goto('/statistiques')

  await expect(page.locator('main').getByRole('heading', { name: /Statistiques/ })).toBeVisible()
})
