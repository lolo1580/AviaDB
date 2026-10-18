import { describe, it, expect, beforeEach } from 'vitest'
import {
  classes,
  childrenOf,
  flattenedClasses,
  classPath,
  descendantsOf,
  subtreeItemCount,
} from '../classes'

// Arborescence de test :
//   Aéronefs (id 1)
//   ├── Chasseur (2)
//   │   └── Rafale (4)
//   └── Transport (3)
beforeEach(() => {
  classes.list = [
    { id: 1, name: 'Aéronefs', parent_id: null, position: 0, item_count: 1 },
    { id: 2, name: 'Chasseur', parent_id: 1, position: 0, item_count: 2 },
    { id: 4, name: 'Rafale', parent_id: 2, position: 0, item_count: 3 },
    { id: 3, name: 'Transport', parent_id: 1, position: 1, item_count: 0 },
  ]
  classes.loaded = true
})

describe('classes', () => {
  it('liste les enfants triés par position', () => {
    expect(childrenOf(1).map((n) => n.name)).toEqual(['Chasseur', 'Transport'])
    expect(childrenOf(null).map((n) => n.name)).toEqual(['Aéronefs'])
  })

  it('aplatit l’arbre avec la profondeur', () => {
    const flat = flattenedClasses()
    expect(flat.map((n) => [n.name, n.depth])).toEqual([
      ['Aéronefs', 0],
      ['Chasseur', 1],
      ['Rafale', 2],
      ['Transport', 1],
    ])
  })

  it('exclut un sous-arbre entier', () => {
    const flat = flattenedClasses(descendantsOf(2))
    expect(flat.map((n) => n.name)).toEqual(['Aéronefs', 'Transport'])
  })

  it('reconstruit le chemin complet', () => {
    expect(classPath(4)).toBe('Aéronefs › Chasseur › Rafale')
    expect(classPath(null)).toBe('')
  })

  it('renvoie la classe et toute sa descendance', () => {
    expect([...descendantsOf(1)].sort()).toEqual([1, 2, 3, 4])
    expect([...descendantsOf(2)].sort()).toEqual([2, 4])
  })

  it('cumule le nombre d’objets du sous-arbre', () => {
    expect(subtreeItemCount(1)).toBe(6)
    expect(subtreeItemCount(2)).toBe(5)
  })
})
