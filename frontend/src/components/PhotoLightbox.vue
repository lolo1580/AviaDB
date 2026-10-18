<script setup>
import { computed, ref, watch } from 'vue'
import { photoUrl } from '../api'
import AppModal from './ui/AppModal.vue'

const props = defineProps({
  photos: { type: Array, required: true },
  open: { type: Boolean, default: false },
  startIndex: { type: Number, default: 0 },
})
defineEmits(['close'])

const index = ref(props.startIndex)

watch(
  () => [props.open, props.startIndex],
  ([open]) => {
    if (open) index.value = Math.min(Math.max(0, props.startIndex), Math.max(0, props.photos.length - 1))
  },
  { immediate: true },
)

const current = computed(() => props.photos[index.value] || null)

function previous() {
  index.value = (index.value - 1 + props.photos.length) % props.photos.length
}
function next() {
  index.value = (index.value + 1) % props.photos.length
}

function onKeydown(event) {
  if (event.key === 'ArrowLeft') previous()
  else if (event.key === 'ArrowRight') next()
}

watch(
  () => props.open,
  (open) => {
    if (open) window.addEventListener('keydown', onKeydown)
    else window.removeEventListener('keydown', onKeydown)
  },
  { immediate: true },
)
</script>

<template>
  <AppModal
    :open="open"
    size="full"
    bare
    backdrop="dark"
    :title="current?.caption || 'Photo'"
    :subtitle="photos.length > 1 ? `${index + 1} / ${photos.length}` : ''"
    @update:open="$emit('close')"
  >
    <div class="relative flex items-center justify-center">
      <button
        v-if="photos.length > 1"
        type="button"
        class="absolute left-2 z-10 grid h-10 w-10 place-items-center rounded-full bg-white/10 text-xl text-white transition hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-white"
        aria-label="Photo précédente"
        @click="previous"
      >
        ‹
      </button>

      <img
        :src="photoUrl(current?.file_path)"
        :alt="current?.caption || ''"
        class="max-h-[75vh] w-auto rounded-lg object-contain shadow-2xl"
      />

      <button
        v-if="photos.length > 1"
        type="button"
        class="absolute right-2 z-10 grid h-10 w-10 place-items-center rounded-full bg-white/10 text-xl text-white transition hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-white"
        aria-label="Photo suivante"
        @click="next"
      >
        ›
      </button>
    </div>
  </AppModal>
</template>
