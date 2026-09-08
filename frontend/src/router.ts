import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import NewReviewView from './views/NewReviewView.vue'
import HistoryView from './views/HistoryView.vue'
import WorkflowView from './views/WorkflowView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/reviews', component: HistoryView },
    { path: '/reviews/new', component: NewReviewView },
    { path: '/reviews/:id', component: () => import('./views/ReviewDetailView.vue') },
    { path: '/reviews/:id/report', component: () => import('./views/ReviewDetailView.vue') },
    { path: '/workflow', component: WorkflowView },
    { path: '/evals', component: () => import('./views/EvalsView.vue') },
  ],
})
