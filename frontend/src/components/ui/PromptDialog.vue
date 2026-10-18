<script setup>
/**
 * Boîte de saisie — montée une seule fois (voir `App.vue`).
 * S'appuie sur `AppModal` : mêmes animations, même piège de focus, même
 * fermeture par Échap ou clic extérieur (qui annulent la saisie).
 */
import { computed, nextTick, ref, watch } from 'vue'
import { promptState, settlePrompt } from '../../composables/usePrompt'
import AppModal from './AppModal.vue'
import AppButton from './AppButton.vue'

const options = computed(() => promptState.options)
const value = ref('')
const error = ref('')
const field = ref(null)
const formId = `prompt-form-${Math.random().toString(36).slice(2, 7)}`

const required = computed(() => options.value.required ?? true)
const minLength = computed(() => options.value.minLength ?? 0)
const inputClass =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-200 dark:border-slate-700 dark:focus:ring-sky-900'

watch(
  () => promptState.open,
  async (open) => {
    if (!open) return
    value.value = options.value.value ?? ''
    error.value = ''
    await nextTick()
    // Le bouton de fermeture est le premier élément focalisable : on vise
    // explicitement le champ pour éviter une frappe dans le vide.
    field.value?.focus()
    field.value?.select?.()
  },
)

function validate(input) {
  if (required.value && !String(input).trim()) return 'Ce champ est obligatoire'
  if (minLength.value && String(input).length < minLength.value) {
    return `${minLength.value} caractères minimum`
  }
  if (options.value.validate) return options.value.validate(input) || ''
  return ''
}

function submit() {
  const message = validate(value.value)
  if (message) {
    error.value = message
    field.value?.focus()
    return
  }
  error.value = ''
  settlePrompt(value.value)
}
</script>

<template>
  <AppModal
    :open="promptState.open"
    :title="options.title || 'Saisie'"
    :subtitle="options.subtitle || ''"
    size="sm"
    level="top"
    @close="settlePrompt(null)"
  >
    <form :id="formId" class="space-y-3" @submit.prevent="submit">
      <label class="flex flex-col gap-1">
        <span class="text-xs font-medium text-slate-500 dark:text-slate-400">
          {{ options.label || 'Valeur' }}
        </span>

        <textarea
          v-if="options.multiline"
          ref="field"
          v-model="value"
          rows="3"
          data-autofocus
          :placeholder="options.placeholder || ''"
          :aria-invalid="error ? 'true' : undefined"
          :aria-describedby="error ? `${formId}-error` : undefined"
          :class="inputClass"
        />
        <input
          v-else
          ref="field"
          v-model="value"
          data-autofocus
          :type="options.type || 'text'"
          :placeholder="options.placeholder || ''"
          :autocomplete="options.type === 'password' ? 'new-password' : 'off'"
          :maxlength="options.maxLength"
          :aria-invalid="error ? 'true' : undefined"
          :aria-describedby="error ? `${formId}-error` : undefined"
          :class="inputClass"
        />
      </label>

      <p
        v-if="error"
        :id="`${formId}-error`"
        role="alert"
        class="text-xs font-medium text-rose-600 dark:text-rose-400"
      >
        {{ error }}
      </p>
    </form>

    <template #footer>
      <AppButton variant="secondary" @click="settlePrompt(null)">
        {{ options.cancelLabel || 'Annuler' }}
      </AppButton>
      <AppButton type="submit" :form="formId" variant="primary">
        {{ options.confirmLabel || 'Valider' }}
      </AppButton>
    </template>
  </AppModal>
</template>
