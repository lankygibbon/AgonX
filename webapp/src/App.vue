<script setup>
import { RouterView, RouterLink } from 'vue-router'
</script>

<template>
  <div class="min-h-screen bg-slate-900 text-slate-100">
    <nav class="bg-slate-800 border-b border-slate-700 px-4 md:px-8">
      <div class="max-w-7xl mx-auto flex items-center h-14 gap-8">
        <span class="font-bold text-xl tracking-tight text-white">AgonX</span>
        <RouterLink
          to="/leaderboard"
          class="text-sm font-medium text-slate-300 hover:text-white transition-colors"
          active-class="text-white border-b-2 border-orange-500 pb-1"
        >
          Leaderboard
        </RouterLink>
        <RouterLink
          to="/predict"
          class="text-sm font-medium text-slate-300 hover:text-white transition-colors"
          active-class="text-white border-b-2 border-orange-500 pb-1"
        >
          Predict My Rank
        </RouterLink>
      </div>
    </nav>
    <main class="max-w-7xl mx-auto px-4 md:px-8 py-6">
      <RouterView />
    </main>
  </div>
</template>
