import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
  { path: '/model-settings', name: 'model-settings', component: () => import('./views/ModelSettingsView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
