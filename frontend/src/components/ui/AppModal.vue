<script setup>
/**
 * Modale réutilisable — Tailwind uniquement, aucune librairie UI.
 *
 * Fonctions clés :
 * - transitions d'entrée / sortie (fondu + léger glissement) ;
 * - fermeture par `Échap` ou clic sur le fond, désactivable ;
 * - `role="dialog"` + `aria-modal` + `aria-labelledby` / `aria-describedby` ;
 * - piège de focus (Tab boucle), focus rendu à l'élément déclencheur ;
 * - verrouillage du défilement de la page, compatible avec les modales empilées ;
 * - `Échap` ne ferme que la modale du dessus.
 *
 * Emplacements : `header`, `default` (corps), `footer`.
 *
 * @example
 * <AppModal v-model:open="open" title="Nouvel objet" size="lg">
 *   <p>…</p>
 *   <template #footer>
 *     <AppButton @click="open = false">Annuler</AppButton>
 *     <AppButton variant="primary" @click="save">Enregistrer</AppButton>
 *   </template>
 * </AppModal>
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { focusFirst, useFocusTrap } from '../../composables/useFocusTrap'
import { lockScroll, unlockScroll } from '../../composables/useScrollLock'
import { isTopModal, registerModal, unregisterModal } from '../../layout/modalStack'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  /** sm | md | lg | xl | full */
  size: { type: String, default: 'md' },
  /** dim (gris) | dark (visionneuse) | none */
  backdrop: { type: String, default: 'dim' },
  /** Retire le cadre blanc du panneau (contenu plein écran). */
  bare: { type: Boolean, default: false },
  closeOnEscape: { type: Boolean, default: true },
  closeOnOutside: { type: Boolean, default: true },
  hideClose: { type: Boolean, default: false },
  /** Ouvre au-dessus des autres modales (confirmations). */
  level: { type: String, default: 'base' },
  /** Identifiant du titre, si un `aria-labelledby` externe est fourni. */
  labelledBy: { type: String, default: null },
})

const emit = defineEmits(['update:open', 'close', 'opened', 'closed'])

const panel = ref(null)
const uid = `modal-${Math.random().toString(36).slice(2, 9)}`
const titleId = computed(() => props.labelledBy || `${uid}-title`)
const descriptionId = computed(() => (props.subtitle ? `${uid}-description` : undefined))

const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
  full: 'max-w-[min(100rem,96vw)]',
}
const sizeClass = computed(() => SIZES[props.size] || SIZES.md)
const levelClass = computed(() => (props.level === 'top' ? 'z-[60]' : 'z-50'))
const backdropClass = computed(() => {
  if (props.backdrop === 'none') return 'bg-transparent'
  if (props.backdrop === 'dark') return 'bg-slate-950/95'
  return 'bg-slate-900/50'
})

let registered = false

function activate() {
  if (registered) return
  registered = true
  registerModal(uid)
  lockScroll()
  nextTick(() => {
    focusFirst(panel.value)
    emit('opened')
  })
}

function deactivate() {
  if (!registered) return
  registered = false
  unregisterModal(uid)
  unlockScroll()
  emit('closed')
}

function close(reason = 'close') {
  emit('update:open', false)
  emit('close', reason)
}

function onDocumentKeydown(event) {
  if (event.key !== 'Escape' || !props.closeOnEscape) return
  if (!isTopModal(uid)) return
  event.stopPropagation()
  close('escape')
}

function onBackdropPointerDown(event) {
  // Ferme dès que l'appui n'a pas commencé *dans le panneau* : un simple test
  // d'égalité avec la cible échouerait sur le voile et le conteneur de centrage.
  if (!props.closeOnOutside) return
  const panelElement = panel.value
  if (panelElement && panelElement.contains(event.target)) return
  close('outside')
}

watch(
  () => props.open,
  (value) => {
    if (value) {
      activate()
      document.addEventListener('keydown', onDocumentKeydown, true)
    } else {
      document.removeEventListener('keydown', onDocumentKeydown, true)
      deactivate()
    }
  },
  { immediate: true },
)

useFocusTrap(panel, () => props.open && isTopModal(uid))

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onDocumentKeydown, true)
  deactivate()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="fixed inset-0 overflow-y-auto"
        :class="levelClass"
        @pointerdown="onBackdropPointerDown"
      >
        <div class="modal-backdrop fixed inset-0" :class="backdropClass" aria-hidden="true" />

        <div class="relative flex min-h-full items-start justify-center p-4 sm:p-6">
          <div
            ref="panel"
            class="modal-panel relative w-full outline-none"
            :class="[
              sizeClass,
              bare
                ? ''
                : 'my-auto rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900',
            ]"
            role="dialog"
            aria-modal="true"
            :aria-labelledby="title || $slots.header ? titleId : undefined"
            :aria-describedby="descriptionId"
          >
            <!-- En-tête -->
            <header
              v-if="title || subtitle || $slots.header || !hideClose"
              class="flex items-start justify-between gap-4 px-6 py-4"
              :class="bare ? 'border-b border-white/10' : 'border-b border-slate-200 dark:border-slate-800'"
            >
              <slot name="header" :title-id="titleId" :description-id="descriptionId">
                <div class="min-w-0">
                  <h2
                    :id="titleId"
                    class="truncate text-lg font-semibold"
                    :class="bare ? 'text-white' : 'text-slate-900 dark:text-slate-100'"
                  >
                    {{ title }}
                  </h2>
                  <p
                    v-if="subtitle"
                    :id="descriptionId"
                    class="mt-0.5 text-sm"
                    :class="bare ? 'text-slate-300' : 'text-slate-500 dark:text-slate-400'"
                  >
                    {{ subtitle }}
                  </p>
                </div>
              </slot>

              <button
                v-if="!hideClose"
                type="button"
                class="shrink-0 rounded-lg p-1.5 transition"
                :class="
                  bare
                    ? 'text-slate-300 hover:bg-white/10 hover:text-white'
                    : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200'
                "
                aria-label="Fermer la fenêtre"
                @click="close('button')"
              >
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </header>

            <!-- Corps -->
            <div :class="bare ? '' : 'px-6 py-5'">
              <slot />
            </div>

            <!-- Pied -->
            <footer
              v-if="$slots.footer"
              class="flex flex-wrap items-center justify-end gap-2 px-6 py-4"
              :class="bare ? '' : 'border-t border-slate-200 dark:border-slate-800'"
            >
              <slot name="footer" />
            </footer>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
