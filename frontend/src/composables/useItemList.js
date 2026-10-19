import { ref } from 'vue'
import { api } from '../api'
import { optimistic, tempId } from '../optimistic'
import { toast } from '../toast'

/**
 * État local d'une liste d'objets + mutations optimistes.
 *
 * Principe : on modifie la liste **immédiatement**, on envoie la requête, et on
 * restaure l'état précédent si le serveur refuse. `refreshStats` est appelé
 * après coup, sans bloquer l'interface, pour recaler les agrégats.
 */
export function useItemList({ limit = 200, refreshStats } = {}) {
  const items = ref([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref('')

  const key = (id) => `item:${id}`
  const indexOf = (id) => items.value.findIndex((item) => item.id === id)

  async function load(params = {}) {
    loading.value = true
    error.value = ''
    try {
      const data = await api.listItems({ ...params, limit: params.limit ?? limit })
      items.value = data.items
      total.value = data.total
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  /** Représentation locale d'un objet pas encore confirmé par le serveur. */
  function localFrom(payload) {
    return {
      ...payload,
      id: tempId('item'),
      diecast: payload.diecast ?? null,
      patch: payload.patch ?? null,
      tags: (payload.tags || []).map((name) => ({ id: tempId('tag'), name })),
      photos: [],
      links: [],
      price_points: [],
      _optimistic: true,
    }
  }

  /** Ajoute les liens d'un objet créé, en tâche de fond. */
  async function attachLinks(itemId, links = []) {
    for (const link of links) {
      await optimistic({
        key: key(itemId),
        label: 'Ajout du lien',
        request: () => api.addLink(itemId, link),
        onSuccess: (created) => {
          const item = items.value.find((entry) => entry.id === itemId)
          if (item) item.links = [...(item.links || []), created]
        },
      })
    }
    if (links.length) refreshStats?.()
  }

  /** Téléverse les photos d'un objet, en tâche de fond. */
  async function uploadFiles(itemId, files = []) {
    for (const file of files) {
      await optimistic({
        key: key(itemId),
        label: 'Envoi de la photo',
        request: () => api.uploadPhoto(itemId, file),
        onSuccess: (photo) => {
          const item = items.value.find((entry) => entry.id === itemId)
          if (!item) return
          const existing = (item.photos || []).some((entry) => entry.id === photo.id)
          item.photos = existing
            ? item.photos.map((entry) => (entry.id === photo.id ? photo : entry))
            : [...(item.photos || []), photo]
        },
      })
    }
    if (files.length) refreshStats?.()
  }

  // ------------------------------------------------------------------------- #
  // Mutations
  // ------------------------------------------------------------------------- #
  async function create(payload, files = [], links = []) {
    const local = localFrom(payload)
    items.value.unshift(local)
    total.value += 1

    const result = await optimistic({
      key: key(local.id),
      label: 'Création',
      apply: () => () => {
        const index = indexOf(local.id)
        if (index !== -1) items.value.splice(index, 1)
        total.value = Math.max(0, total.value - 1)
      },
      request: () => api.createItem(payload),
      onSuccess: (created) => {
        // Réconciliation : l'ID temporaire cède la place à l'ID serveur.
        const index = indexOf(local.id)
        if (index !== -1) items.value.splice(index, 1, created)
        uploadFiles(created.id, files)
        attachLinks(created.id, links)
      },
      retry: () => create(payload, files, links),
    })

    if (result.ok) {
      refreshStats?.()
      toast.success(`« ${payload.name} » ajouté`)
    }
    return result
  }

  async function update(id, payload) {
    const index = indexOf(id)
    if (index === -1) return { ok: false }

    const previous = { ...items.value[index] }
    const local = { ...items.value[index], ...payload }
    if (payload.tags) {
      local.tags = payload.tags.map((name) => ({ id: tempId('tag'), name }))
    }
    if ('diecast' in payload) {
      local.diecast = payload.diecast
        ? { ...payload.diecast, id: local.diecast?.id ?? tempId('diecast') }
        : null
    }
    if ('patch' in payload) {
      local.patch = payload.patch
        ? { ...payload.patch, id: local.patch?.id ?? tempId('patch') }
        : null
    }
    items.value.splice(index, 1, local)

    const result = await optimistic({
      key: key(id),
      label: 'Modification',
      apply: () => () => {
        const current = indexOf(id)
        if (current !== -1) items.value.splice(current, 1, previous)
      },
      request: () => api.updateItem(id, payload),
      onSuccess: (updated) => {
        const current = indexOf(id)
        if (current !== -1) items.value.splice(current, 1, updated)
      },
      retry: () => update(id, payload),
    })

    if (result.ok) refreshStats?.()
    return result
  }

  async function remove(id) {
    const index = indexOf(id)
    if (index === -1) return { ok: true }
    const [removed] = items.value.splice(index, 1)
    total.value = Math.max(0, total.value - 1)

    const result = await optimistic({
      key: key(id),
      label: 'Suppression',
      apply: () => () => {
        items.value.splice(Math.min(index, items.value.length), 0, removed)
        total.value += 1
      },
      request: () => api.deleteItem(id),
      retry: () => remove(id),
    })

    if (result.ok) refreshStats?.()
    return result
  }

  /** Changement de statut isolé (tableau d'administration). */
  async function setStatus(id, status) {
    const item = items.value.find((entry) => entry.id === id)
    if (!item || item.status === status) return { ok: true }

    const previous = item.status
    item.status = status

    const result = await optimistic({
      key: key(id),
      label: 'Changement de statut',
      apply: () => () => {
        const current = items.value.find((entry) => entry.id === id)
        if (current) current.status = previous
      },
      request: () => api.updateItem(id, { status }),
      onSuccess: () => refreshStats?.(),
      retry: () => setStatus(id, status),
    })
    return result
  }

  /** Action groupée : suppression, statut, ajout / retrait de tags. */
  async function bulk(ids, action, payload = {}) {
    const affected = ids
      .map((id) => ({ id, index: indexOf(id), item: items.value.find((entry) => entry.id === id) }))
      .filter((entry) => entry.item)
    if (!affected.length) return { ok: true }

    const before = affected.map(({ item }) => ({
      id: item.id,
      status: item.status,
      tags: [...(item.tags || [])],
    }))

    if (action === 'delete') {
      affected
        .map((entry) => entry.index)
        .sort((a, b) => b - a)
        .forEach((index) => items.value.splice(index, 1))
      total.value = Math.max(0, total.value - affected.length)
    } else if (action === 'set_status') {
      affected.forEach(({ item }) => {
        item.status = payload.status
      })
    } else if (action === 'add_tags') {
      const names = (payload.tags || []).filter(Boolean)
      affected.forEach(({ item }) => {
        const existing = new Set((item.tags || []).map((tag) => tag.name))
        item.tags = [
          ...(item.tags || []),
          ...names.filter((name) => !existing.has(name)).map((name) => ({ id: tempId('tag'), name })),
        ]
      })
    } else if (action === 'remove_tags') {
      const wanted = new Set((payload.tags || []).map((name) => name.trim().toLowerCase()))
      affected.forEach(({ item }) => {
        item.tags = (item.tags || []).filter((tag) => !wanted.has(tag.name.toLowerCase()))
      })
    }

    const result = await optimistic({
      key: 'bulk',
      label: 'Action groupée',
      apply: () => () => {
        if (action === 'delete') {
          affected
            .slice()
            .sort((a, b) => a.index - b.index)
            .forEach(({ item, index }) => {
              items.value.splice(Math.min(index, items.value.length), 0, item)
              total.value += 1
            })
        } else {
          before.forEach((snapshot) => {
            const item = items.value.find((entry) => entry.id === snapshot.id)
            if (!item) return
            item.status = snapshot.status
            item.tags = snapshot.tags
          })
        }
      },
      request: () => api.bulk({ ids, action, ...payload }),
      retry: () => bulk(ids, action, payload),
    })

    if (result.ok) refreshStats?.()
    return result
  }

  return { items, total, loading, error, load, create, update, remove, setStatus, bulk, indexOf }
}
