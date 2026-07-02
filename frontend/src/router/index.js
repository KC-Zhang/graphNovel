import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import ReaderView from '../views/ReaderView.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/read/:projectId',
    name: 'Reader',
    component: ReaderView,
    props: true
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
