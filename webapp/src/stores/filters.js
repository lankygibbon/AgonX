import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useFiltersStore = defineStore('filters', () => {
  // Dataset scope
  const family = ref('athx')
  const year   = ref('2026')

  // Competitor type
  const competitorType = ref('individual') // 'individual' | 'team'

  // Per-competitor filters — derived from loaded data
  const division  = ref('')
  const age_group = ref('')
  const category  = ref('')
  const event     = ref('')
  const workout   = ref('') // '' | workout key e.g. 'strength' | 'endurance' | 'metcon_x'

  watch([family, year, competitorType], resetCompetitorFilters)

  function resetCompetitorFilters() {
    division.value  = ''
    age_group.value = ''
    category.value  = ''
    event.value     = ''
    workout.value   = ''
  }

  function reset() {
    resetCompetitorFilters()
  }

  return { family, year, competitorType, division, age_group, category, event, workout, reset }
})
