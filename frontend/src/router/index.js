import { createRouter, createWebHistory } from 'vue-router'

// ReaderView pulls in graph and PDF rendering code. Route-level chunks keep
// those libraries off the landing-page critical path.
const Home = () => import('../views/Home.vue')
const ReaderView = () => import('../views/ReaderView.vue')

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
