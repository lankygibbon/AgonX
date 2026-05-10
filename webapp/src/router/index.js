import { createRouter, createWebHashHistory } from 'vue-router'
import LeaderboardPage from '../pages/LeaderboardPage.vue'
import PredictPage from '../pages/PredictPage.vue'
import AthletePage from '../pages/AthletePage.vue'

const routes = [
  { path: '/', redirect: '/leaderboard' },
  { path: '/leaderboard', component: LeaderboardPage },
  { path: '/predict', component: PredictPage },
  { path: '/athlete/:userId', component: AthletePage },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
