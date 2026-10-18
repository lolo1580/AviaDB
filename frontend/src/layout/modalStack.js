import { computed, reactive } from 'vue'

/**
 * Pile des modales ouvertes.
 *
 * Sert à trois choses :
 * - `Échap` ne ferme que la modale du dessus (utile pour les modales imbriquées :
 *   formulaire → visionneuse photo → confirmation) ;
 * - le verrouillage du défilement n'est levé qu'à la fermeture de la dernière ;
 * - savoir si une modale est ouverte, par exemple pour désactiver un raccourci.
 */
const stack = reactive([])

export function registerModal(id) {
  if (!stack.includes(id)) stack.push(id)
}

export function unregisterModal(id) {
  const index = stack.indexOf(id)
  if (index !== -1) stack.splice(index, 1)
}

export function isTopModal(id) {
  return stack.length > 0 && stack[stack.length - 1] === id
}

export const openModalCount = computed(() => stack.length)
export const hasOpenModal = computed(() => stack.length > 0)
