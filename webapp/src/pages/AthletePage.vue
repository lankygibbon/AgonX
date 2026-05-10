<script setup>
import { computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useData } from '../lib/useData.js'
import { formatWorkoutTotal, formatMemberWorkout } from '../lib/ranking.js'

const route = useRoute()
const userId = computed(() => route.params.userId)

const { competitors, teams, workoutSchema, loading } = useData()

const workoutEntries = computed(() =>
  workoutSchema.value ? Object.entries(workoutSchema.value) : []
)

const individual = computed(() =>
  competitors.value.find(c => c.user_id === userId.value)
)

const athleteTeams = computed(() =>
  teams.value.filter(t =>
    t.members?.some(m => m.user_id === userId.value)
  )
)

const name = computed(() =>
  individual.value?.name
  || athleteTeams.value[0]?.members?.find(m => m.user_id === userId.value)?.name
  || 'Unknown Athlete'
)

const country = computed(() => individual.value?.country || '')

function findMember(team) {
  return team.members?.find(m => m.user_id === userId.value)
}
</script>

<template>
  <div>
    <RouterLink to="/leaderboard" class="text-sm text-slate-400 hover:text-slate-200 mb-6 inline-flex items-center gap-1">
      ← Back to leaderboard
    </RouterLink>

    <div v-if="loading" class="text-center py-20 text-slate-400">Loading…</div>

    <div v-else>
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-white">{{ name }}</h1>
        <p class="text-slate-400 mt-1">{{ country }}</p>
      </div>

      <!-- Individual results -->
      <section v-if="individual" class="mb-8">
        <h2 class="text-lg font-semibold text-slate-200 mb-3">Individual Results</h2>
        <div class="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-slate-800/80 text-slate-400 text-xs uppercase tracking-wider text-left">
                <th class="px-4 py-3">Event</th>
                <th class="px-4 py-3">Division / Age</th>
                <th
                  v-for="[wkey, wdef] in workoutEntries"
                  :key="wkey"
                  class="px-4 py-3 text-right"
                >{{ wdef.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr class="border-t border-slate-700">
                <td class="px-4 py-3 text-slate-200">{{ individual.event }}</td>
                <td class="px-4 py-3 text-slate-400">{{ individual.division }} · {{ individual.age_group }}</td>
                <td
                  v-for="[wkey, wdef] in workoutEntries"
                  :key="wkey"
                  class="px-4 py-3 text-right text-slate-100"
                >
                  {{ formatWorkoutTotal(individual, wkey, wdef) }}
                  <div v-if="wdef.components?.length && individual.scores?.[wkey]?.components" class="text-xs text-slate-500 mt-0.5 space-x-2">
                    <span v-for="comp in wdef.components" :key="comp.id">
                      <template v-if="individual.scores[wkey].components[comp.id] != null">
                        {{ comp.label }}: {{ individual.scores[wkey].components[comp.id] }}{{ wdef.unit !== 'time' ? wdef.unit : '' }}
                      </template>
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Teams this athlete was part of -->
      <section v-if="athleteTeams.length" class="mb-8">
        <h2 class="text-lg font-semibold text-slate-200 mb-3">Team Results</h2>
        <div
          v-for="team in athleteTeams"
          :key="team.team + team.event"
          class="bg-slate-800 border border-slate-700 rounded-xl p-4 mb-3"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="font-medium text-slate-100">{{ team.team }}</div>
              <div class="text-sm text-slate-400 mt-0.5">{{ team.event }} · {{ team.division }} · {{ team.age_group }}</div>
            </div>
            <div class="text-right text-sm text-slate-400 space-y-0.5">
              <div v-for="[wkey, wdef] in workoutEntries" :key="wkey">
                {{ wdef.name }}: <span class="text-slate-200">{{ formatWorkoutTotal(team, wkey, wdef) }}</span>
              </div>
            </div>
          </div>

          <!-- This athlete's contribution -->
          <div v-if="findMember(team) && workoutEntries.some(([wkey, wdef]) => formatMemberWorkout(findMember(team), wkey, wdef))" class="mb-2 text-xs text-slate-400">
            Your scores:
            <span v-for="[wkey, wdef] in workoutEntries" :key="wkey" class="ml-3">
              <template v-if="formatMemberWorkout(findMember(team), wkey, wdef)">
                {{ wdef.name }}: <span class="text-slate-300">{{ formatMemberWorkout(findMember(team), wkey, wdef) }}</span>
              </template>
            </span>
          </div>

          <!-- Team member list -->
          <div class="flex gap-3 flex-wrap">
            <span class="text-xs text-slate-500">Team:</span>
            <span v-for="m in team.members" :key="m.user_id || m.name">
              <RouterLink
                v-if="m.user_id && m.user_id !== userId"
                :to="`/athlete/${m.user_id}`"
                class="text-xs text-orange-400 hover:text-orange-300"
              >{{ m.name }}</RouterLink>
              <span v-else-if="m.user_id === userId" class="text-xs text-slate-300 font-medium">{{ m.name }} (you)</span>
              <span v-else class="text-xs text-slate-400">{{ m.name }}</span>
            </span>
          </div>
        </div>
      </section>

      <!-- No data at all -->
      <div
        v-if="!individual && !athleteTeams.length"
        class="text-center py-20 text-slate-400"
      >
        No data found for this athlete.
      </div>
    </div>
  </div>
</template>
