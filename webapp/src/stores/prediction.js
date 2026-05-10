import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const usePredictionStore = defineStore('prediction', () => {
  const name = ref('You (predicted)')
  const division = ref('')
  const age_group = ref('')
  const category = ref('')
  const event = ref('')

  // Individual keys:  `${wkey}::${compId}`  or  `${wkey}::_time`
  // Team keys:        `t1::${wkey}::${compId}` / `t2::${wkey}::${compId}`
  //                   `${wkey}::_time` (shared — teams have one time)
  const componentScores = ref({})

  // ── Individual ────────────────────────────────────────────────────────────

  function buildVirtualCompetitor(workoutSchema) {
    if (!workoutSchema) return null
    const scores = {}

    for (const [wkey, wdef] of Object.entries(workoutSchema)) {
      if (wdef.components?.length) {
        const components = {}
        let total = 0
        let hasAny = false
        for (const comp of wdef.components) {
          const v = parseFloat(componentScores.value[`${wkey}::${comp.id}`])
          if (!isNaN(v) && v > 0) {
            components[comp.id] = v
            total += v
            hasAny = true
          }
        }
        if (hasAny) scores[wkey] = { total, components }
      } else {
        const raw = componentScores.value[`${wkey}::_time`]
        const secs = parseTime(raw)
        if (secs !== null) scores[wkey] = { total: secs, time: raw }
      }
    }

    return {
      name: name.value,
      user_id: null,
      event: event.value,
      division: division.value,
      age_group: age_group.value,
      category: category.value,
      scores,
    }
  }

  // ── Team ──────────────────────────────────────────────────────────────────

  function buildVirtualTeam(workoutSchema) {
    if (!workoutSchema) return null
    const scores = {}
    const m1scores = {}
    const m2scores = {}

    for (const [wkey, wdef] of Object.entries(workoutSchema)) {
      if (wdef.components?.length) {
        const combined = {}
        const a1comps = {}
        const a2comps = {}
        let total = 0
        let hasAny = false

        for (const comp of wdef.components) {
          // per_person defaults to true when not set (transform may not have run yet)
          if (comp.per_person !== false) {
            // Each athlete contributes independently — two inputs, sum for team total
            const v1 = parseFloat(componentScores.value[`t1::${wkey}::${comp.id}`])
            const v2 = parseFloat(componentScores.value[`t2::${wkey}::${comp.id}`])
            const n1 = !isNaN(v1) && v1 > 0 ? v1 : 0
            const n2 = !isNaN(v2) && v2 > 0 ? v2 : 0
            if (n1 || n2) {
              combined[comp.id] = n1 + n2
              total += n1 + n2
              hasAny = true
            }
            if (n1) a1comps[comp.id] = n1
            if (n2) a2comps[comp.id] = n2
          } else {
            // Team does this component together — one shared input
            const v = parseFloat(componentScores.value[`shared::${wkey}::${comp.id}`])
            const n = !isNaN(v) && v > 0 ? v : 0
            if (n) {
              combined[comp.id] = n
              total += n
              hasAny = true
            }
          }
        }

        if (hasAny) {
          scores[wkey] = { total, components: combined }
          if (Object.keys(a1comps).length) m1scores[wkey] = { components: a1comps }
          if (Object.keys(a2comps).length) m2scores[wkey] = { components: a2comps }
        }
      } else {
        // Shared single time for the team
        const raw = componentScores.value[`${wkey}::_time`]
        const secs = parseTime(raw)
        if (secs !== null) scores[wkey] = { total: secs, time: raw }
      }
    }

    return {
      name: 'Your Team',
      team: 'Your Team',
      event: event.value,
      division: division.value,
      age_group: age_group.value,
      category: category.value,
      scores,
      members: [
        { name: 'Athlete 1', user_id: null, match_confidence: 1, scores: m1scores },
        { name: 'Athlete 2', user_id: null, match_confidence: 1, scores: m2scores },
      ],
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function parseTime(raw) {
    if (!raw) return null
    const parts = raw.split(':').map(Number)
    if (parts.some(isNaN)) return null
    if (parts.length === 2) return parts[0] * 60 + parts[1]
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return null
  }

  const hasScores = computed(() =>
    Object.values(componentScores.value).some(v => v !== '' && v != null)
  )

  function reset() {
    componentScores.value = {}
    name.value = 'You (predicted)'
    division.value = ''
    age_group.value = ''
    category.value = ''
    event.value = ''
  }

  return {
    name, division, age_group, category, event, componentScores,
    buildVirtualCompetitor, buildVirtualTeam, hasScores, reset,
  }
})
