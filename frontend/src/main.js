import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { initTheme } from './theme'
import { initUi } from './ui'
import './style.css'

initTheme()
initUi()

createApp(App).use(router).mount('#app')
