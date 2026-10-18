<script setup>
/**
 * Boîte de confirmation — montée une seule fois (voir `App.vue`).
 * S'appuie sur `AppModal` et se place au-dessus des autres modales.
 */
import { computed } from 'vue'
import { confirmState, settleConfirm } from '../../composables/useConfirm'
import AppModal from './AppModal.vue'
import AppButton from './AppButton.vue'

const options = computed(() => confirmState.options)

const confirmLabel = computed(() => options.value.confirmLabel || 'Confirmer')
const cancelLabel = computed(() => options.value.cancelLabel || 'Annuler')
</script>

<template>
  <AppModal
    :open="confirmState.open"
    :title="options.title || 'Confirmation'"
    :subtitle="options.subtitle || ''"
    size="sm"
    level="top"
    @close="settleConfirm(false)"
  >
    <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
      {{ options.message }}
    </p>

    <template #footer>
      <AppButton variant="secondary" data-autofocus @click="settleConfirm(false)">
        {{ cancelLabel }}
      </AppButton>
      <AppButton
        v-if="options.alternateLabel"
        variant="secondary"
        @click="settleConfirm('alternate')"
      >
        {{ options.alternateLabel }}
      </AppButton>
      <AppButton
        :variant="options.danger ? 'danger' : 'primary'"
        @click="settleConfirm('confirm')"
      >
        {{ confirmLabel }}
      </AppButton>
    </template>
  </AppModal>
</template>
