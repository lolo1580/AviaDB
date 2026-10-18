import { ref } from 'vue'

const STORAGE_KEY = 'aviadb-theme'

export const isDark = ref(false)

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

function apply(dark) {
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

/** Initialise le thème : choix mémorisé, sinon préférence système. */
export function initTheme() {
  let stored = null
  try {
    stored = localStorage.getItem(STORAGE_KEY)
  } catch {
    /* localStorage indisponible : on retombe sur la préférence système */
  }
  isDark.value = stored ? stored === 'dark' : systemPrefersDark()
  apply(isDark.value)
}

export function toggleTheme() {
  isDark.value = !isDark.value
  try {
    localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
  } catch {
    /* ignore */
  }
  apply(isDark.value)
}
