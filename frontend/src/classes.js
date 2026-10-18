import { reactive } from 'vue'
import { api } from './api'

/**
 * Arborescence des classes, partagée par les filtres, le formulaire et les
 * affichages. L'API renvoie une liste plate : on la reconstruit ici.
 */
export const classes = reactive({ list: [], loaded: false })

export async function loadClasses() {
  try {
    classes.list = await api.getClasses()
    classes.loaded = true
  } catch {
    /* silencieux : l'interface reste utilisable sans classes */
  }
}

export function childrenOf(parentId = null) {
  return classes.list
    .filter((node) => node.parent_id === parentId)
    .sort((a, b) => a.position - b.position || a.name.localeCompare(b.name))
}

/** Liste aplatie avec profondeur, pour un `<select>` indenté ou un arbre. */
export function flattenedClasses(excluded = new Set()) {
  const rows = []
  const walk = (parentId, depth) => {
    for (const node of childrenOf(parentId)) {
      if (excluded.has(node.id)) continue
      rows.push({ ...node, depth })
      walk(node.id, depth + 1)
    }
  }
  walk(null, 0)
  return rows
}

/** Chemin lisible d'une classe : « Aéronefs › Chasseur › Rafale ». */
export function classPath(classId, separator = ' › ') {
  if (!classId) return ''
  const byId = new Map(classes.list.map((node) => [node.id, node]))
  const names = []
  const seen = new Set()
  let current = classId
  while (current && byId.has(current) && !seen.has(current)) {
    seen.add(current)
    names.unshift(byId.get(current).name)
    current = byId.get(current).parent_id
  }
  return names.join(separator)
}

/** Identifiants de la classe et de toute sa descendance (pour l'admin). */
export function descendantsOf(classId) {
  const found = new Set([classId])
  let added = true
  while (added) {
    added = false
    for (const node of classes.list) {
      if (node.parent_id && found.has(node.parent_id) && !found.has(node.id)) {
        found.add(node.id)
        added = true
      }
    }
  }
  return found
}

/** Nombre d'objets rattachés à la classe et à sa descendance. */
export function subtreeItemCount(classId) {
  const ids = descendantsOf(classId)
  return classes.list
    .filter((node) => ids.has(node.id))
    .reduce((total, node) => total + (node.item_count || 0), 0)
}
