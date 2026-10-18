import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// Horodatage du build, affiché en pied de page : permet de vérifier d'un coup
// d'œil que le navigateur tourne bien sur la dernière version déployée.
const buildStamp = new Date().toISOString().replace('T', ' ').slice(0, 16)

// En dev, l'API et les images sont proxifiées vers le backend FastAPI.
export default defineConfig({
  define: {
    __BUILD_STAMP__: JSON.stringify(buildStamp),
  },
  plugins: [vue(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/uploads': 'http://localhost:8000',
    },
  },
})
