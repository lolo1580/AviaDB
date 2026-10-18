import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Ferme un panneau flottant (menu, notifications) au clic extérieur ou sur Échap.
 * `elementRef` est une ref vers l'élément racine du panneau.
 */
export function useClickOutside(elementRef, onOutside) {
  function onPointerDown(event) {
    const element = elementRef.value
    if (!element) return
    if (!element.contains(event.target)) onOutside(event)
  }

  function onKeydown(event) {
    if (event.key === 'Escape') onOutside(event)
  }

  onMounted(() => {
    document.addEventListener('pointerdown', onPointerDown, true)
    document.addEventListener('keydown', onKeydown)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onPointerDown, true)
    document.removeEventListener('keydown', onKeydown)
  })
}
