/**
 * Verrouillage du défilement de la page tant qu'une modale est ouverte.
 *
 * Compté par référence : plusieurs modales empilées ne relâchent le verrou
 * qu'à la fermeture de la dernière. La largeur de la barre de défilement est
 * compensée pour éviter un décalage horizontal de la page.
 */
let locks = 0
let previousOverflow = ''
let previousPaddingRight = ''

export function lockScroll() {
  if (locks === 0) {
    const gap = window.innerWidth - document.documentElement.clientWidth
    previousOverflow = document.body.style.overflow
    previousPaddingRight = document.body.style.paddingRight
    document.body.style.overflow = 'hidden'
    if (gap > 0) document.body.style.paddingRight = `${gap}px`
  }
  locks += 1
}

export function unlockScroll() {
  locks = Math.max(0, locks - 1)
  if (locks === 0) {
    document.body.style.overflow = previousOverflow
    document.body.style.paddingRight = previousPaddingRight
  }
}
