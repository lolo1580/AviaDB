// Client API — encapsule les appels REST et l'accesseur d'URL des images.
const API_BASE = import.meta.env.VITE_API_BASE || ''

function buildQuery(params = {}) {
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) {
      value.forEach((v) => usp.append(key, v))
    } else {
      usp.append(key, value)
    }
  }
  const qs = usp.toString()
  return qs ? `?${qs}` : ''
}

async function request(path, { method = 'GET', body, isForm = false } = {}) {
  const opts = { method, headers: {}, credentials: 'same-origin' }
  if (body !== undefined) {
    if (isForm) {
      opts.body = body
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }

  const res = await fetch(`${API_BASE}${path}`, opts)
  if (res.status === 204) return null

  const text = await res.text()
  const data = text ? JSON.parse(text) : null

  if (!res.ok) {
    const detail = data?.detail
    const message = Array.isArray(detail)
      ? detail.map((d) => `${(d.loc || []).join('.')}: ${d.msg}`).join(' ; ')
      : detail || res.statusText
    throw new Error(message)
  }
  return data
}

export const api = {
  listItems: (params) => request(`/api/items${buildQuery(params)}`),
  getItem: (id) => request(`/api/items/${id}`),
  createItem: (data) => request('/api/items', { method: 'POST', body: data }),
  updateItem: (id, data) => request(`/api/items/${id}`, { method: 'PATCH', body: data }),
  deleteItem: (id) => request(`/api/items/${id}`, { method: 'DELETE' }),

  getStats: () => request('/api/stats'),
  getFacets: () => request('/api/meta/facets'),
  getEnums: () => request('/api/meta/enums'),
  getTags: () => request('/api/tags'),

  // Devises et taux
  getSettings: () => request('/api/meta/settings'),
  updateSettings: (defaultCurrency) =>
    request('/api/admin/settings', { method: 'PUT', body: { default_currency: defaultCurrency } }),
  updateRates: (rates) => request('/api/admin/rates', { method: 'PUT', body: { rates } }),
  refreshRates: () => request('/api/admin/rates/refresh', { method: 'POST' }),

  // Liens externes
  addLink: (itemId, data) => request(`/api/items/${itemId}/links`, { method: 'POST', body: data }),
  updateLink: (id, data) => request(`/api/links/${id}`, { method: 'PATCH', body: data }),
  deleteLink: (id) => request(`/api/links/${id}`, { method: 'DELETE' }),

  // Relevés de prix
  addPrice: (itemId, data) => request(`/api/items/${itemId}/prices`, { method: 'POST', body: data }),
  deletePrice: (id) => request(`/api/prices/${id}`, { method: 'DELETE' }),
  fetchPrice: (url) => request('/api/admin/fetch-price', { method: 'POST', body: { url } }),

  // Classes (arborescence)
  getClasses: () => request('/api/classes'),  createClass: (data) => request('/api/admin/classes', { method: 'POST', body: data }),
  updateClass: (id, data) => request(`/api/admin/classes/${id}`, { method: 'PATCH', body: data }),
  deleteClass: (id, force = false) =>
    request(`/api/admin/classes/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  // Clés d'API
  listApiKeys: () => request('/api/admin/api-keys'),
  createApiKey: (label) => request('/api/admin/api-keys', { method: 'POST', body: { label } }),
  updateApiKey: (id, data) => request(`/api/admin/api-keys/${id}`, { method: 'PATCH', body: data }),
  deleteApiKey: (id) => request(`/api/admin/api-keys/${id}`, { method: 'DELETE' }),

  listPhotos: (itemId) => request(`/api/items/${itemId}/photos`),
  uploadPhoto: (itemId, file, { caption = '', isPrimary = false } = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    if (caption) fd.append('caption', caption)
    fd.append('is_primary', String(isPrimary))
    return request(`/api/items/${itemId}/photos`, { method: 'POST', body: fd, isForm: true })
  },
  updatePhoto: (id, data) => request(`/api/photos/${id}`, { method: 'PATCH', body: data }),
  setPrimaryPhoto: (id) => request(`/api/photos/${id}/primary`, { method: 'POST' }),
  deletePhoto: (id) => request(`/api/photos/${id}`, { method: 'DELETE' }),

  // Session admin
  session: () => request('/api/admin/session'),
  login: (username, password) =>
    request('/api/admin/login', { method: 'POST', body: { username, password } }),
  logout: () => request('/api/admin/logout', { method: 'POST' }),

  // Administration
  bulk: (payload) => request('/api/admin/bulk', { method: 'POST', body: payload }),
  listActivity: (limit = 100) => request(`/api/admin/activity?limit=${limit}`),
  exportItems: () => request('/api/admin/export'),
  importItems: (items) => request('/api/admin/import', { method: 'POST', body: items }),
  importCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/admin/import.csv', { method: 'POST', body: fd, isForm: true })
  },
  restoreBackup: (file, mode = 'merge') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('mode', mode)
    return request('/api/admin/restore', { method: 'POST', body: fd, isForm: true })
  },
  renameTag: (id, name) => request(`/api/admin/tags/${id}`, { method: 'PATCH', body: { name } }),
  deleteTag: (id) => request(`/api/admin/tags/${id}`, { method: 'DELETE' }),

  // Comptes
  listUsers: () => request('/api/admin/users'),
  createUser: (data) => request('/api/admin/users', { method: 'POST', body: data }),
  updateUser: (id, data) => request(`/api/admin/users/${id}`, { method: 'PATCH', body: data }),
  deleteUser: (id) => request(`/api/admin/users/${id}`, { method: 'DELETE' }),

  // Photos
  reorderPhotos: (itemId, ids) =>
    request(`/api/items/${itemId}/photos/reorder`, { method: 'POST', body: { ids } }),
}

/** URL de l'export CSV (téléchargement direct, cookie envoyé automatiquement). */
export const exportCsvUrl = () => `${API_BASE}/api/admin/export.csv`

/** URL de la sauvegarde ZIP (base + images). */
export const backupUrl = () => `${API_BASE}/api/admin/backup`

/** URL du rapport d'inventaire PDF (totaux + liste des objets). */
export const reportUrl = () => `${API_BASE}/api/admin/report.pdf`

/** URL de la fiche détaillée PDF d'un objet. */
export const itemReportUrl = (id) => `${API_BASE}/api/items/${id}/report.pdf`

export const photoUrl = (path) => (path ? `${API_BASE}/uploads/${path}` : '')

/** Photo de couverture : la principale, sinon la première. */
export function coverPhoto(item) {
  if (!item?.photos?.length) return null
  return item.photos.find((p) => p.is_primary) || item.photos[0]
}
