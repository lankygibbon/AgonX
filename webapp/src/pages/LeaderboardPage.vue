<script setup>
import { computed } from 'vue'
import { useFiltersStore } from '../stores/filters.js'
import { useData } from '../lib/useData.js'
import { rankCompetitors } from '../lib/ranking.js'
import FilterBar from '../components/FilterBar.vue'
import LeaderboardTable from '../components/LeaderboardTable.vue'

const { competitors, teams, workoutSchema, loading, error } = useData()
const filters = useFiltersStore()

const activeFilters = computed(() => ({
  division:  filters.division,
  age_group: filters.age_group,
  category:  filters.category,
  event:     filters.event,
}))

// Teams expose `team` not `name` — normalise so rankCompetitors can use a consistent key
const normalisedTeams = computed(() =>
  teams.value.map(t => ({ ...t, name: t.team }))
)

const filterSource = computed(() =>
  filters.competitorType === 'team' ? normalisedTeams.value : competitors.value
)

const ranked = computed(() => {
  if (!workoutSchema.value) return []
  const pool = filterSource.value
  if (!pool.length) return []
  return rankCompetitors(pool, workoutSchema.value, activeFilters.value)
})

const totalCount = computed(() => ranked.value.length)
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-white mb-1">Leaderboard</h1>
      <p class="text-slate-400 text-sm">
        {{ totalCount }} result{{ totalCount === 1 ? '' : 's' }}
        <span v-if="filters.division || filters.age_group || filters.category || filters.event"> (filtered)</span>
      </p>
    </div>

    <div v-if="error" class="bg-red-900/40 border border-red-700 rounded-lg p-4 mb-6 text-red-300 text-sm">
      Failed to load data: {{ error }}
    </div>

    <FilterBar
      :competitors="filterSource"
      :workout-schema="workoutSchema"
    />

    <LeaderboardTable
      :ranked="ranked"
      :loading="loading"
      :competitor-type="filters.competitorType"
      :workout-schema="workoutSchema"
      :active-workout="filters.workout"
    />
  </div>
</template>
