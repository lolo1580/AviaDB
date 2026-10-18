<script setup>
/**
 * Panneau latéral (drawer) réutilisable — Tailwind uniquement.
 *
 * Même socle que `AppModal` : téléportation dans `body`, transitions, fermeture
 * par `Échap` ou clic à l'extérieur, `role="dialog"` + `aria-modal`, piège de
 * focus, verrouillage du défilement, et pile de fenêtres (Échap ne ferme que
 * celle du dessus).
 *
 * Emplacements : `header`, `default` (corps défilant), `footer` (fixe en bas).
 *
 * @example
 * <AppDrawer v-model:open="open" title="Rafale M" size="lg">
 *   <p>…</p>
 *   <template #footer><AppButton @click="open = false">Fermer</AppButton></template>
 * </AppDrawer>
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { focusFirst, useFocusTrap } from '../../composables/useFocusTrap'
import { lockScroll, unlockScroll } from '../../composables/useScrollLock'
import { isTopModal, registerModal, unregisterModal } from '../../layout/modalStack'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  /** sm | md | lg | xl */
  size: { type: String, default: 'md' },
  /** Côté d'ancrage du panneau. */
  side: { type: String, default: 'right' },
  closeOnEscape: { type: Boolean, default: true },
  closeOnOutside: { type: Boolean, default: true },
  hideClose: { type: Boolean, default: false },
  /** Ouvre au-dessus des autres fenêtres (confirmations). */
  level: { type: String, default: 'base' },
  labelledBy: { type: String, default: null },
})

const emit = defineEmits(['update:open', 'close', 'opened', 'closed'])

const panel = ref(null)
const uid = `drawer-${Math.random().toString(36).slice(2, 9)}`
const titleId = computed(() => props.labelledBy || `${uid}-title`)
const descriptionId = computed(() => (props.subtitle ? `${uid}-description` : undefined))

const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-2xl',
}
const sizeClass = computed(() => SIZES[props.size] || SIZES.md)
const levelClass = computed(() => (props.level === 'top' ? 'z-[60]' : 'z-50'))
const sideClass = computed(() =>
  props.side === 'left' ? 'left-0 border-r' : 'right-0 border-l',
)

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
  if (!props.closeOnOutside) return
  const element = panel.value
  if (element && element.contains(event.target)) return
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
    <Transition name="drawer">
      <div v-if="open" class="fixed inset-0" :class="levelClass" @pointerdown="onBackdropPointerDown">
        <div class="drawer-backdrop absolute inset-0 bg-slate-900/50" aria-hidden="true" />

        <div
          ref="panel"
          class="drawer-panel absolute inset-y-0 flex w-full flex-col border-slate-200 bg-white shadow-2xl outline-none dark:border-slate-800 dark:bg-slate-900"
          :class="[sizeClass, sideClass]"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="title || $slots.header ? titleId : undefined"
          :aria-describedby="descriptionId"
        >
          <header
            v-if="title || subtitle || $slots.header || !hideClose"
            class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 dark:border-slate-800"
          >
            <slot name="header" :title-id="titleId" :description-id="descriptionId">
              <div class="min-w-0">
                <h2 :id="titleId" class="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {{ title }}
                </h2>
                <p v-if="subtitle" :id="descriptionId" class="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
                  {{ subtitle }}
                </p>
              </div>
            </slot>

            <button
              v-if="!hideClose"
              type="button"
              class="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              aria-label="Fermer le panneau"
              @click="close('button')"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </header>

          <div class="thin-scroll flex-1 overflow-y-auto px-5 py-5">
            <slot />
          </div>

          <footer
            v-if="$slots.footer"
            class="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 px-5 py-4 dark:border-slate-800"
          >
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
