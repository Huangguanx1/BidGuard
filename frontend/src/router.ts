import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import NewReviewView from './views/NewReviewView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/reviews/new', component: NewReviewView },
  ],
})

