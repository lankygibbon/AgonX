<script setup>
import { computed, watch } from 'vue'
import { useFiltersStore } from '../stores/filters.js'
import { usePredictionStore } from '../stores/prediction.js'
import { useData } from '../lib/useData.js'
import { rankCompetitors } from '../lib/ranking.js'
import FilterBar from '../components/FilterBar.vue'
import LeaderboardTable from '../components/LeaderboardTable.vue'
import RankAnalysis from '../components/RankAnalysis.vue'

const { competitors, teams, workoutSchema, loading } = useData()
const filters = useFiltersStore()
const prediction = usePredictionStore()

const isTeam = computed(() => filters.competitorType === 'team')

// Normalise teams the same way LeaderboardPage does
const normalisedTeams = computed(() => teams.value.map(t => ({ ...t, name: t.team })))

// Mirror active filters into the virtual competitor
watch(() => filters.division,  v => { prediction.division  = v })
watch(() => filters.age_group, v => { prediction.age_group = v })
watch(() => filters.category,  v => { prediction.category  = v })
watch(() => filters.event,     v => { prediction.event     = v })

const workoutList = computed(() => {
  if (!workoutSchema.value) return []
  return Object.entries(workoutSchema.value).map(([id, def]) => ({ id, ...def }))
})

const activeFilters = computed(() => ({
  division:  filters.division,
  age_group: filters.age_group,
  category:  filters.category,
  event:     filters.event,
}))

const ranked = computed(() => {
  if (!workoutSchema.value) return []
  const schema = workoutSchema.value

  if (isTeam.value) {
    if (!normalisedTeams.value.length) return []
    const virtual = prediction.hasScores
      ? prediction.buildVirtualTeam(schema)
      : null
    return rankCompetitors(normalisedTeams.value, schema, activeFilters.value, virtual)
  } else {
    if (!competitors.value.length) return []
    const virtual = prediction.hasScores
      ? prediction.buildVirtualCompetitor(schema)
      : null
    return rankCompetitors(competitors.value, schema, activeFilters.value, virtual)
  }
})

const predictedResult = computed(() => ranked.value.find(c => c._isPredicted))

const inputClass = 'bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 w-full focus:outline-none focus:ring-2 focus:ring-orange-500'
const labelClass = 'block text-xs text-slate-400 mb-1'
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-white mb-1">Predict My Rank</h1>
      <p class="text-slate-400 text-sm">Enter your scores to see where you'd place. Use the filters to narrow the pool.</p>
    </div>

    <FilterBar :competitors="isTeam ? normalisedTeams : competitors" :workout-schema="workoutSchema" />

    <!-- Score inputs — driven entirely by the schema -->
    <div class="grid gap-6 mb-8" :class="workoutList.length > 1 ? 'md:grid-cols-3' : 'md:grid-cols-1 max-w-sm'">
      <div
        v-for="workout in workoutList"
        :key="workout.id"
        class="bg-slate-800 border border-slate-700 rounded-xl p-5"
      >
        <h3 class="font-semibold text-white mb-1">{{ workout.name }}</h3>
        <p class="text-xs text-slate-500 mb-4">{{ workout.scoring === 'asc' ? 'Lower is better' : 'Higher is better' }}</p>

        <!-- Component-based workout (kg / km) -->
        <template v-if="workout.components?.length">

          <!-- Individual: single set of inputs -->
          <template v-if="!isTeam">
            <div v-for="comp in workout.components" :key="comp.id" class="mb-3">
              <label :class="labelClass">{{ comp.label }} <span class="text-slate-600">({{ comp.unit }})</span></label>
              <input
                type="number" step="0.001" min="0" :class="inputClass"
                :placeholder="comp.unit === 'kg' ? 'e.g. 100' : 'e.g. 2.500'"
                :value="prediction.componentScores[`${workout.id}::${comp.id}`]"
                @input="prediction.componentScores[`${workout.id}::${comp.id}`] = $event.target.value"
              />
            </div>
          </template>

          <!-- Team: per-component layout driven by per_person flag -->
          <template v-else>
            <div v-for="comp in workout.components" :key="comp.id" class="mb-4">
              <div class="flex items-center gap-2 mb-1.5">
                <span :class="labelClass" class="mb-0">{{ comp.label }} <span class="text-slate-600">({{ comp.unit }})</span></span>
                <span
                  class="text-xs px-1.5 py-0.5 rounded"
                  :class="comp.per_person === false ? 'bg-blue-900/50 text-blue-400' : 'bg-slate-700 text-slate-500'"
                >{{ comp.per_person === false ? 'combined' : 'per athlete' }}</span>
              </div>

              <!-- Combined: one shared input -->
              <template v-if="comp.per_person === false">
                <input
                  type="number" step="0.001" min="0" :class="inputClass"
                  :placeholder="comp.unit === 'kg' ? 'e.g. 100' : 'e.g. 2.500'"
                  :value="prediction.componentScores[`shared::${workout.id}::${comp.id}`]"
                  @input="prediction.componentScores[`shared::${workout.id}::${comp.id}`] = $event.target.value"
                />
              </template>

              <!-- Per athlete: two inputs side by side -->
              <template v-else>
                <div class="grid grid-cols-2 gap-2">
                  <div v-for="(athlete, idx) in ['t1', 't2']" :key="athlete">
                    <label class="text-xs text-slate-600 mb-1 block">Athlete {{ idx + 1 }}</label>
                    <input
                      type="number" step="0.001" min="0" :class="inputClass"
                      :placeholder="comp.unit === 'kg' ? 'e.g. 100' : 'e.g. 2.500'"
                      :value="prediction.componentScores[`${athlete}::${workout.id}::${comp.id}`]"
                      @input="prediction.componentScores[`${athlete}::${workout.id}::${comp.id}`] = $event.target.value"
                    />
                  </div>
                </div>
              </template>
            </div>
          </template>
        </template>

        <!-- Time / single-value workout — always one shared input -->
        <template v-else>
          <div class="mb-3">
            <label :class="labelClass">{{ workout.unit === 'time' ? 'Time (mm:ss)' : `Score (${workout.unit})` }}</label>
            <input
              :type="workout.unit === 'time' ? 'text' : 'number'"
              step="0.001" min="0" :class="inputClass"
              :placeholder="workout.unit === 'time' ? 'e.g. 09:30' : 'e.g. 100'"
              :value="prediction.componentScores[`${workout.id}::_time`]"
              @input="prediction.componentScores[`${workout.id}::_time`] = $event.target.value"
            />
          </div>
        </template>
      </div>
    </div>

    <RankAnalysis
      v-if="predictedResult"
      :ranked="ranked"
      :predicted-result="predictedResult"
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
