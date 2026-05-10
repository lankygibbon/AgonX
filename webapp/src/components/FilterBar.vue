<script setup>
import { computed, watch } from 'vue'
import { useFiltersStore } from '../stores/filters.js'
import { useWorkoutsIndex } from '../lib/useData.js'
import { deriveFilterOptions } from '../lib/ranking.js'

const props = defineProps({
  competitors:   { type: Array,  default: () => [] },
  workoutSchema: { type: Object, default: null },
})

const filters = useFiltersStore()
const { families, yearsForFamily } = useWorkoutsIndex()

const availableYears = computed(() => yearsForFamily(filters.family))

watch(() => filters.family, (newFamily) => {
  const years = yearsForFamily(newFamily)
  if (years.length && !years.includes(filters.year)) filters.year = years[0]
})

const options = computed(() => deriveFilterOptions(props.competitors))

const workoutOptions = computed(() => {
  if (!props.workoutSchema) return []
  return Object.entries(props.workoutSchema).map(([id, def]) => ({
    value: id,
    label: def.name,
  }))
})

const hasCompetitorFilters = computed(() =>
  filters.division || filters.age_group || filters.category || filters.event || filters.workout
)

const TYPES = [
  { value: 'individual', label: 'Individual' },
  { value: 'team',       label: 'Team'       },
]

const sel = 'bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500 min-w-[130px]'
const accentSel = 'bg-slate-600 border border-orange-600/50 text-slate-100 text-sm font-medium rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500 min-w-[100px] uppercase tracking-wide'
</script>

<template>
  <div class="mb-6 space-y-3">
    <!-- Row 1: Dataset scope + competitor type -->
    <div class="flex flex-wrap gap-3 items-center pb-3 border-b border-slate-700">
      <select :class="accentSel" v-model="filters.family">
        <option v-for="f in families" :key="f" :value="f">{{ f }}</option>
      </select>
      <select :class="accentSel" v-model="filters.year">
        <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
      </select>

      <div class="w-px h-6 bg-slate-600 mx-1" />

      <div class="flex rounded-lg border border-slate-600 overflow-hidden">
        <button
          v-for="type in TYPES"
          :key="type.value"
          @click="filters.competitorType = type.value"
          :class="[
            'px-4 py-2 text-sm font-medium transition-colors whitespace-nowrap',
            filters.competitorType === type.value
              ? 'bg-orange-600 text-white'
              : 'bg-slate-700 text-slate-300 hover:text-white hover:bg-slate-600',
          ]"
        >{{ type.label }}</button>
      </div>
    </div>

    <!-- Row 2: Per-competitor filters + workout selector -->
    <div class="flex flex-wrap gap-3 items-center">
      <select :class="sel" v-model="filters.division">
        <option value="">All Divisions</option>
        <option v-for="d in options.divisions" :key="d" :value="d">{{ d }}</option>
      </select>
      <select :class="sel" v-model="filters.age_group">
        <option value="">All Ages</option>
        <option v-for="a in options.age_groups" :key="a" :value="a">{{ a }}</option>
      </select>
      <select :class="sel" v-model="filters.category">
        <option value="">All Categories</option>
        <option v-for="c in options.categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <select :class="sel" v-model="filters.event">
        <option value="">All Events</option>
        <option v-for="e in options.events" :key="e" :value="e">{{ e }}</option>
      </select>

      <select v-if="workoutOptions.length" :class="sel" v-model="filters.workout">
        <option value="">All Workouts</option>
        <option v-for="w in workoutOptions" :key="w.value" :value="w.value">{{ w.label }}</option>
      </select>

      <button
        v-if="hasCompetitorFilters"
        @click="filters.reset()"
        class="text-sm text-slate-400 hover:text-slate-200 underline"
      >Clear</button>
    </div>
  </div>
</template>
