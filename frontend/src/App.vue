<script setup>
import { onMounted, watch } from 'vue'
import { RouterView } from 'vue-router'
import { auth, refreshSession } from './auth'
import { initUi } from './ui'
import { loadSettings } from './settings'
import { loadClasses } from './classes'
import AppShell from './components/layout/AppShell.vue'
import LoginPanel from './components/LoginPanel.vue'
import ToastStack from './components/ToastStack.vue'
import ConfirmDialog from './components/ui/ConfirmDialog.vue'
import PromptDialog from './components/ui/PromptDialog.vue'

onMounted(async () => {
  initUi()
  await refreshSession()
  if (auth.authenticated) await Promise.all([loadSettings(), loadClasses()])
})

// Les réglages monétaires et les classes ne sont lisibles qu'une fois connecté.
watch(
  () => auth.authenticated,
  (value) => {
    if (value) Promise.all([loadSettings(), loadClasses()])
  },
)
</script>

<template>
  <!-- Chargement de l'état de session -->
  <div
    v-if="!auth.checked"
    class="grid min-h-screen place-items-center text-sm text-slate-400 dark:text-slate-500"
  >
    Chargement…
  </div>

  <!-- Accès protégé : connexion avant toute chose -->
  <LoginPanel v-else-if="auth.enabled && !auth.authenticated" />

  <!-- Application -->
  <AppShell v-else>
    <RouterView />
  </AppShell>

  <!-- Hôtes globaux : notifications, confirmations et saisies -->
  <ConfirmDialog />
  <PromptDialog />
  <ToastStack />
</template>
