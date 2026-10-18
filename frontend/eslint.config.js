import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import prettier from 'eslint-config-prettier'

// Configuration ESLint (flat config) : règles JS recommandées + Vue,
// puis `eslint-config-prettier` qui désactive les règles de mise en forme
// (celles-ci sont du ressort de Prettier).
export default [
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**', 'docs/**', 'playwright-report/**', 'test-results/**'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  prettier,
  {
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
        __BUILD_STAMP__: 'readonly',
      },
    },
    rules: {
      // Les vues sont nommées par usage (CollectionView, AdminView…).
      'vue/multi-word-component-names': 'off',
      // `FilterBar` reçoit un objet `filters` réactif et le modifie en place
      // (son parent s'appuie sur cette réactivité). On interdit la réaffectation
      // de la prop elle-même, pas la mutation de ses champs.
      'vue/no-mutating-props': ['error', { shallowOnly: true }],
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
    },
  },
]
