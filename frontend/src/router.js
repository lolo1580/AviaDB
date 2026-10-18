import { createRouter, createWebHistory } from 'vue-router'
import CollectionView from './views/CollectionView.vue'
import AdminView from './views/AdminView.vue'
import ChartsView from './views/ChartsView.vue'
import WishlistView from './views/WishlistView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'collection',
      component: CollectionView,
      meta: { title: 'Collection', subtitle: 'Maquettes et patchs de la collection' },
    },
    {
      path: '/souhaits',
      name: 'wishlist',
      component: WishlistView,
      meta: { title: 'Liste de souhaits', subtitle: 'Pièces recherchées et budget estimé' },
    },
    {
      path: '/statistiques',
      name: 'charts',
      component: ChartsView,
      meta: { title: 'Statistiques', subtitle: 'Répartition de la collection' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: AdminView,
      meta: { title: 'Administration', subtitle: 'Gestion des objets, des comptes et des devises' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
