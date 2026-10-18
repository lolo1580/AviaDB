import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Configuration des tests unitaires (Vitest) — indépendante du build Vite :
// Tailwind n'est pas nécessaire pour tester les composables et les composants.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.js'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      // Périmètre mesuré : la logique couverte par les tests unitaires. Les vues
      // et les composants de présentation seront ajoutés au fur et à mesure.
      include: [
        'src/labels.js',
        'src/settings.js',
        'src/classes.js',
        'src/prices.js',
        'src/optimistic.js',
        'src/composables/useItemList.js',
        'src/components/ItemCard.vue',
        'src/components/FilterBar.vue',
      ],
      thresholds: {
        statements: 70,
        lines: 72,
        functions: 55,
        branches: 60,
      },
    },
  },
})
