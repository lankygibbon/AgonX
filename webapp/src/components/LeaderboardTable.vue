<script setup>
import { ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  deriveComponentColumns,
  formatWorkoutTotal,
  formatMemberWorkout,
} from '../lib/ranking.js'

const props = defineProps({
  ranked:         { type: Array,  default: () => [] },
  loading:        { type: Boolean, default: false },
  competitorType: { type: String,  default: 'individual' }, // 'individual' | 'team'
  workoutSchema:  { type: Object,  default: null },
  activeWorkout:  { type: String,  default: '' },
})

// Sorted workout entries — preserves schema insertion order
const workoutEntries = computed(() =>
  props.workoutSchema ? Object.entries(props.workoutSchema) : []
)

// When a workout filter is active, show per-component columns
const componentCols = computed(() =>
  props.activeWorkout && props.workoutSchema
    ? deriveComponentColumns(props.ranked, props.activeWorkout, props.workoutSchema[props.activeWorkout])
    : []
)

// Number of score columns (used for accordion colspan)
const scoreColCount = computed(() =>
  props.activeWorkout && componentCols.value.length
    ? componentCols.value.length
    : workoutEntries.value.length
)

// Total table column count: rank + name + event + scores + pts + expand
const totalCols = computed(() => 3 + scoreColCount.value + 2)

// When a workout filter is active, re-sort by that workout's rank so the
// table order reflects the selected exercise, not overall points
const displayRanked = computed(() => {
  if (!props.activeWorkout) return props.ranked
  return [...props.ranked].sort((a, b) => {
    const ra = a.workoutRanks?.[props.activeWorkout] ?? Infinity
    const rb = b.workoutRanks?.[props.activeWorkout] ?? Infinity
    return ra - rb
  })
})

// Expand/collapse state
const expanded = ref(new Set())
function toggleExpand(key) {
  const next = new Set(expanded.value)
  next.has(key) ? next.delete(key) : next.add(key)
  expanded.value = next
}

function rowKey(c) {
  return c._key || c.user_id || c.name
}

function rankBadge(rank) {
  if (rank === 1) return 'bg-yellow-500 text-yellow-900'
  if (rank === 2) return 'bg-slate-400 text-slate-900'
  if (rank === 3) return 'bg-amber-700 text-amber-100'
  return 'bg-slate-700 text-slate-300'
}

// Whether a competitor has any component-level detail worth showing
function hasDetail(c) {
  if (!props.workoutSchema) return false
  return workoutEntries.value.some(([wkey, wdef]) => {
    if (wdef.unit === 'time') return !!c.scores?.[wkey]?.time
    return Object.keys(c.scores?.[wkey]?.components || {}).length > 0
  })
}

// Format a component value for display
function formatComponent(value, unit) {
  if (value == null) return '—'
  if (unit === 'kg') return `${value} kg`
  if (unit === 'km') return `${Number(value).toFixed(3)} km`
  return String(value)
}
</script>

<template>
  <div>
    <div v-if="loading" class="text-center py-20 text-slate-400">Loading…</div>
    <div v-else-if="!ranked.length" class="text-center py-20 text-slate-400">
      No results match the current filters.
    </div>

    <div v-else class="overflow-x-auto rounded-xl border border-slate-700">
      <table class="w-full text-sm">
        <thead>
          <tr class="bg-slate-800 text-slate-400 text-left text-xs uppercase tracking-wider">
            <th class="px-4 py-3 w-12">#</th>
            <th class="px-4 py-3">{{ competitorType === 'team' ? 'Team' : 'Athlete' }}</th>
            <th class="px-4 py-3 hidden sm:table-cell">Event</th>

            <!-- Workout-filtered: per-component columns -->
            <template v-if="activeWorkout && componentCols.length">
              <th
                v-for="col in componentCols"
                :key="col.id"
                class="px-4 py-3 text-right"
              >
                {{ col.label }}
                <span class="normal-case font-normal ml-1 text-slate-500">({{ col.unit }})</span>
              </th>
            </template>

            <!-- Overview: one column per workout in schema -->
            <template v-else>
              <th
                v-for="[wkey, wdef] in workoutEntries"
                :key="wkey"
                class="px-4 py-3 text-right"
                :class="workoutEntries.length > 2 ? 'hidden md:table-cell first-of-type:table-cell' : ''"
              >{{ wdef.name }}</th>
            </template>

            <th class="px-4 py-3 text-right">Pts</th>
            <th class="px-4 py-3 w-8" />
          </tr>
        </thead>

        <tbody>
          <template v-for="c in displayRanked" :key="rowKey(c)">
            <tr
              :class="[
                'border-t border-slate-700 transition-colors cursor-pointer',
                c._isPredicted ? 'bg-orange-950/40 border-l-2 border-l-orange-500' : 'hover:bg-slate-800/50',
              ]"
              @click="toggleExpand(rowKey(c))"
            >
              <!-- Rank (workout rank when filtered, overall otherwise) -->
              <td class="px-4 py-3">
                <span :class="['inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold', rankBadge(activeWorkout ? (c.workoutRanks?.[activeWorkout] ?? c.overallRank) : c.overallRank)]">
                  {{ activeWorkout ? (c.workoutRanks?.[activeWorkout] ?? '—') : c.overallRank }}
                </span>
              </td>

              <!-- Name -->
              <td class="px-4 py-3">
                <div class="font-medium text-slate-100">
                  <span v-if="c._isPredicted">★ </span>
                  <RouterLink
                    v-if="competitorType === 'individual' && c.user_id && !c._isPredicted"
                    :to="`/athlete/${c.user_id}`"
                    class="hover:text-orange-400 transition-colors"
                    @click.stop
                  >{{ c.name }}</RouterLink>
                  <span v-else>{{ c.name }}</span>
                </div>
                <div class="text-xs text-slate-400 mt-0.5">{{ c.country }} · {{ c.age_group }}</div>
              </td>

              <!-- Event -->
              <td class="px-4 py-3 hidden sm:table-cell text-slate-400">{{ c.event }}</td>

              <!-- Workout-filtered: component values -->
              <template v-if="activeWorkout && componentCols.length">
                <td
                  v-for="col in componentCols"
                  :key="col.id"
                  class="px-4 py-3 text-right text-slate-100"
                >{{ formatComponent(col.getValue(c), col.unit) }}</td>
              </template>

              <!-- Overview: workout totals -->
              <template v-else>
                <td
                  v-for="[wkey, wdef] in workoutEntries"
                  :key="wkey"
                  class="px-4 py-3 text-right"
                  :class="workoutEntries.length > 2 ? 'hidden md:table-cell first-of-type:table-cell' : ''"
                >
                  <span class="text-slate-100">{{ formatWorkoutTotal(c, wkey, wdef) }}</span>
                  <span
                    v-if="c.workoutRanks?.[wkey]"
                    class="text-xs text-slate-500 ml-1"
                  >#{{ c.workoutRanks[wkey] }}</span>
                </td>
              </template>

              <!-- Points -->
              <td class="px-4 py-3 text-right font-semibold text-slate-100">{{ c.points ?? '—' }}</td>

              <!-- Expand toggle -->
              <td class="px-3 py-3 text-slate-500 text-center select-none" @click.stop="toggleExpand(rowKey(c))">
                <span
                  class="transition-transform inline-block"
                  :class="expanded.has(rowKey(c)) ? 'rotate-180' : ''"
                >▾</span>
              </td>
            </tr>

            <!-- ─── Accordion ─── -->
            <template v-if="expanded.has(rowKey(c))">

              <!-- Component detail (overview mode only — redundant when components already shown as columns) -->
              <tr
                v-if="!activeWorkout && hasDetail(c)"
                class="border-t border-slate-700/30 bg-slate-900/40"
              >
                <td :colspan="totalCols" class="px-4 py-3">
                  <div class="flex flex-wrap gap-6 pl-7">
                    <div v-for="[wkey, wdef] in workoutEntries" :key="wkey">
                      <!-- Time workout: just show time -->
                      <template v-if="wdef.unit === 'time' && c.scores?.[wkey]?.time">
                        <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">{{ wdef.name }}</div>
                        <span class="text-slate-300 text-xs font-medium">{{ c.scores[wkey].time }}</span>
                      </template>
                      <!-- Component workout: show each component -->
                      <template v-else-if="Object.keys(c.scores?.[wkey]?.components || {}).length">
                        <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">{{ wdef.name }}</div>
                        <div class="flex flex-wrap gap-x-4 gap-y-1">
                          <div
                            v-for="comp in wdef.components"
                            :key="comp.id"
                            class="text-xs"
                          >
                            <span class="text-slate-500">{{ comp.label }}:</span>
                            <span class="text-slate-300 ml-1 font-medium">
                              {{ formatComponent(c.scores[wkey].components[comp.id], comp.unit) }}
                            </span>
                          </div>
                        </div>
                      </template>
                    </div>
                  </div>
                </td>
              </tr>

              <!-- Team member rows -->
              <template v-if="competitorType === 'team'">
                <tr
                  v-for="member in (c.members || [])"
                  :key="member.user_id || member.name"
                  class="border-t border-slate-700/50 bg-slate-800/60"
                >
                  <td class="px-4 py-2" />
                  <td class="px-4 py-2 pl-10">
                    <div class="flex items-center gap-2">
                      <span class="w-1.5 h-1.5 rounded-full bg-orange-500 flex-shrink-0" />
                      <RouterLink
                        v-if="member.user_id"
                        :to="`/athlete/${member.user_id}`"
                        class="text-sm text-slate-300 hover:text-orange-400 transition-colors"
                        @click.stop
                      >{{ member.name }}</RouterLink>
                      <span v-else class="text-sm text-slate-400">{{ member.name }}</span>
                      <span
                        v-if="member.match_confidence > 0 && member.match_confidence < 0.95"
                        class="text-xs text-slate-600"
                        :title="`Match confidence: ${Math.round(member.match_confidence * 100)}%`"
                      >~{{ Math.round(member.match_confidence * 100) }}%</span>
                    </div>
                  </td>
                  <td class="hidden sm:table-cell px-4 py-2 text-xs text-slate-500">{{ c.event }}</td>
                  <!-- Per-workout score summary for each member -->
                  <td
                    class="px-4 py-2 text-right text-xs text-slate-400"
                    :colspan="scoreColCount + 2"
                  >
                    <template v-if="Object.keys(member.scores || {}).length">
                      <span
                        v-for="[wkey, wdef] in workoutEntries"
                        :key="wkey"
                        class="ml-4"
                      >
                        <template v-if="formatMemberWorkout(member, wkey, wdef)">
                          <span class="text-slate-600">{{ wdef.name }}:</span>
                          <span class="text-slate-300 ml-1">{{ formatMemberWorkout(member, wkey, wdef) }}</span>
                        </template>
                      </span>
                    </template>
                    <span v-else class="text-slate-600 italic">scores not linked</span>
                  </td>
                </tr>

                <tr v-if="!c.members?.length" class="border-t border-slate-700/50 bg-slate-800/60">
                  <td :colspan="totalCols" class="px-4 py-2 pl-10 text-xs text-slate-600 italic">No member data</td>
                </tr>
              </template>
            </template>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>
