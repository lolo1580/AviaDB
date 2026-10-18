<script setup>
import { ref } from 'vue'
import { login } from '../auth'
import ThemeToggle from './ThemeToggle.vue'

defineProps({
  subtitle: {
    type: String,
    default: 'Connectez-vous pour accéder à la collection.',
  },
})

const username = ref('admin')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await login(username.value.trim(), password.value)
    password.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

const inputClass =
  'rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-200 dark:border-slate-700 dark:focus:ring-sky-900'
</script>

<template>
  <div class="relative grid min-h-full place-items-center px-4 py-10">
    <div class="absolute right-4 top-4">
      <ThemeToggle />
    </div>

    <div class="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex items-center gap-3">
        <span class="grid h-10 w-10 place-items-center rounded-xl bg-sky-600 text-lg font-bold text-white">A</span>
        <div>
          <h1 class="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">AviaDB</h1>
          <p class="text-sm text-slate-500 dark:text-slate-400">Collection aviation</p>
        </div>
      </div>

      <p class="mt-5 text-sm text-slate-600 dark:text-slate-300">{{ subtitle }}</p>

      <form class="mt-4 space-y-3" @submit.prevent="submit">
        <label class="flex flex-col gap-1">
          <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Identifiant</span>
          <input v-model="username" required autocomplete="username" :class="inputClass" />
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs font-medium text-slate-500 dark:text-slate-400">Mot de passe</span>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            :class="inputClass"
          />
        </label>
        <button
          type="submit"
          :disabled="busy"
          class="w-full rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-sky-700 disabled:opacity-50"
        >
          {{ busy ? 'Connexion…' : 'Se connecter' }}
        </button>
      </form>

      <p v-if="error" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
        {{ error }}
      </p>
    </div>
  </div>
</template>
