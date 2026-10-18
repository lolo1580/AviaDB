import { onBeforeUnmount, watch } from 'vue'

// Éléments susceptibles de recevoir le focus au clavier.
const FOCUSABLE = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  'audio[controls]',
  'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function isVisible(element) {
  if (element.hasAttribute('disabled')) return false
  if (element.getAttribute('aria-hidden') === 'true') return false
  return element.getClientRects().length > 0
}

/** Liste des éléments focalisables et visibles d'un conteneur. */
export function focusableWithin(container) {
  if (!container) return []
  return Array.from(container.querySelectorAll(FOCUSABLE)).filter(isVisible)
}

/** Donne le focus au premier élément utile, sinon au conteneur lui-même. */
export function focusFirst(container) {
  if (!container) return
  // Le contenu peut désigner explicitement l'élément à focaliser.
  const explicit = container.querySelector('[data-autofocus]')
  if (explicit && typeof explicit.focus === 'function') {
    explicit.focus({ preventScroll: true })
    if (typeof explicit.select === 'function' && explicit.tagName === 'INPUT') explicit.select()
    return
  }
  const [first] = focusableWithin(container)
  if (first) {
    first.focus({ preventScroll: true })
    return
  }
  container.setAttribute('tabindex', '-1')
  container.focus({ preventScroll: true })
}

/**
 * Piège le focus dans `containerRef` tant que `isActive` est vrai :
 * Tab et Maj+Tab bouclent à l'intérieur, et le focus est rendu à l'élément
 * précédemment actif à la fermeture.
 */
export function useFocusTrap(containerRef, isActive) {
  let previouslyFocused = null
  let trapped = false

  function onKeydown(event) {
    if (event.key !== 'Tab') return
    const container = containerRef.value
    if (!container) return

    const elements = focusableWithin(container)
    if (!elements.length) {
      event.preventDefault()
      container.focus({ preventScroll: true })
      return
    }

    const first = elements[0]
    const last = elements[elements.length - 1]
    const active = document.activeElement
    const inside = container.contains(active)

    if (event.shiftKey && (active === first || !inside)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && (active === last || !inside)) {
      event.preventDefault()
      first.focus()
    }
  }

  function activate() {
    if (trapped) return
    trapped = true
    previouslyFocused = document.activeElement
    document.addEventListener('keydown', onKeydown, true)
  }

  function deactivate() {
    if (!trapped) return
    trapped = false
    document.removeEventListener('keydown', onKeydown, true)
    const target = previouslyFocused
    previouslyFocused = null
    if (target && document.contains(target) && typeof target.focus === 'function') {
      target.focus({ preventScroll: true })
    }
  }

  watch(isActive, (value) => (value ? activate() : deactivate()), { immediate: true })
  onBeforeUnmount(deactivate)
}
