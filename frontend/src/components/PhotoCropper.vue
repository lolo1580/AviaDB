<script setup>
/**
 * Recadrage manuel d'une photo.
 *
 * Affiche l'image et une zone de recadrage déplaçable (glisser le cadre) et
 * redimensionnable par ses quatre coins. Émet `apply` avec des fractions
 * (0 à 1) relatives à l'image : `{ crop: { x, y, width, height } }`.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AppModal from './ui/AppModal.vue'
import AppButton from './ui/AppButton.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  src: { type: String, default: '' },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['apply', 'close'])

const MIN_SIZE = 0.05

const frame = ref(null)
const crop = ref({ x: 0.1, y: 0.1, width: 0.8, height: 0.8 })
const drag = ref(null)

const boxStyle = computed(() => ({
  left: `${crop.value.x * 100}%`,
  top: `${crop.value.y * 100}%`,
  width: `${crop.value.width * 100}%`,
  height: `${crop.value.height * 100}%`,
}))

const handles = ['nw', 'ne', 'sw', 'se']
const handleClass = {
  nw: '-left-1.5 -top-1.5 cursor-nwse-resize',
  ne: '-right-1.5 -top-1.5 cursor-nesw-resize',
  sw: '-left-1.5 -bottom-1.5 cursor-nesw-resize',
  se: '-right-1.5 -bottom-1.5 cursor-nwse-resize',
}

watch(
  () => props.open,
  (open) => {
    if (open) crop.value = { x: 0.1, y: 0.1, width: 0.8, height: 0.8 }
  },
)

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function startDrag(event, mode, handle = null) {
  if (!frame.value || event.button !== 0) return
  drag.value = {
    mode,
    handle,
    startX: event.clientX,
    startY: event.clientY,
    rect: frame.value.getBoundingClientRect(),
    crop: { ...crop.value },
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', stopDrag)
}

function onMove(event) {
  const state = drag.value
  if (!state) return
  const dx = (event.clientX - state.startX) / state.rect.width
  const dy = (event.clientY - state.startY) / state.rect.height

  if (state.mode === 'move') {
    crop.value = {
      ...state.crop,
      x: clamp(state.crop.x + dx, 0, 1 - state.crop.width),
      y: clamp(state.crop.y + dy, 0, 1 - state.crop.height),
    }
    return
  }

  let { x, y, width, height } = state.crop
  if (state.handle.includes('e')) {
    width = clamp(state.crop.width + dx, MIN_SIZE, 1 - state.crop.x)
  }
  if (state.handle.includes('s')) {
    height = clamp(state.crop.height + dy, MIN_SIZE, 1 - state.crop.y)
  }
  if (state.handle.includes('w')) {
    const nextX = clamp(state.crop.x + dx, 0, state.crop.x + state.crop.width - MIN_SIZE)
    width = state.crop.width + (state.crop.x - nextX)
    x = nextX
  }
  if (state.handle.includes('n')) {
    const nextY = clamp(state.crop.y + dy, 0, state.crop.y + state.crop.height - MIN_SIZE)
    height = state.crop.height + (state.crop.y - nextY)
    y = nextY
  }
  crop.value = { x, y, width, height }
}

function stopDrag() {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', stopDrag)
  drag.value = null
}

onBeforeUnmount(stopDrag)
</script>

<template>
  <AppModal
    :open="open"
    title="Recadrer la photo"
    subtitle="Faites glisser le cadre, ou ses coins, pour choisir la zone à conserver."
    size="xl"
    @close="emit('close')"
  >
    <div class="flex justify-center">
      <div
        ref="frame"
        class="relative inline-block touch-none overflow-hidden rounded-lg select-none"
        @pointerdown="startDrag($event, 'move')"
      >
        <img :src="src" class="max-h-[60vh] max-w-full" alt="" draggable="false" />

        <!-- Voile sombre hors de la zone (l'ombre déborde, le cadre la masque) -->
        <div class="pointer-events-none absolute inset-0 bg-slate-900/20" />

        <div
          class="absolute cursor-move border-2 border-white shadow-[0_0_0_9999px_rgba(15,23,42,0.55)]"
          :style="boxStyle"
        >
          <span
            v-for="handle in handles"
            :key="handle"
            class="absolute h-3 w-3 rounded-full border border-slate-400 bg-white shadow"
            :class="handleClass[handle]"
            @pointerdown.stop="startDrag($event, 'resize', handle)"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <AppButton variant="secondary" @click="emit('close')">Annuler</AppButton>
      <AppButton variant="primary" :loading="busy" @click="emit('apply', { ...crop })">
        Recadrer
      </AppButton>
    </template>
  </AppModal>
</template>
