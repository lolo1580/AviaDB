import { createRouter, createWebHistory } from 'vue-router'
import CollectionView from './views/CollectionView.vue'

// Les vues lourdes (Chart.js, qrcode, administration) sont chargées à la
// demande : seule la collection reste dans le paquet initial.
const WishlistView = () => import('./views/WishlistView.vue')
const ChartsView = () => import('./views/ChartsView.vue')
const LabelsView = () => import('./views/LabelsView.vue')
const AdminView = () => import('./views/AdminView.vue')

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
      path: '/etiquettes',
      name: 'labels',
      component: LabelsView,
      meta: { title: 'Étiquettes', subtitle: 'QR codes de rangement à imprimer' },
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
