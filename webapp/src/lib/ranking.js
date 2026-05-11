// @ts-check

/**
 * @typedef {{ division?: string, age_group?: string, category?: string, event?: string }} Filters
 * @typedef {{ total?: number, time?: string, components?: Object }} WorkoutScore
 * @typedef {{ [workoutKey: string]: WorkoutScore }} Scores
 * @typedef {{ name: string, user_id?: string, event: string, division: string, age_group: string, category: string, scores: Scores, _isPredicted?: boolean }} Competitor
 * @typedef {{ name: string, scoring: 'asc'|'desc', unit: string, result_field: string, components: Array }} WorkoutDef
 * @typedef {{ [workoutKey: string]: WorkoutDef }} WorkoutSchema
 */

/**
 * Get the sortable total for a competitor on a given workout.
 * All workouts now store their sortable value as `.total` (seconds for time-based).
 * @param {Competitor} competitor
 * @param {string} workoutKey
 * @returns {number|null}
 */
function getWorkoutTotal(competitor, workoutKey) {
  const entry = competitor.scores?.[workoutKey]
  if (!entry) return null
  if (entry.total != null) return entry.total
  const vals = Object.values(entry.components || {})
  if (!vals.length) return null
  return vals.reduce((a, b) => a + b, 0)
}

/**
 * Filter competitors by the active filter values.
 * @param {Competitor[]} competitors
 * @param {Filters} filters
 * @returns {Competitor[]}
 */
function applyFilters(competitors, filters) {
  return competitors.filter(c => {
    if (filters.division  && c.division  !== filters.division)  return false
    if (filters.age_group && c.age_group !== filters.age_group) return false
    if (filters.category  && c.category  !== filters.category)  return false
    if (filters.event     && c.event     !== filters.event)     return false
    return true
  })
}

/**
 * Assign ranks to an already-sorted array.
 * Ties share a rank; next rank skips (1, 1, 3 not 1, 1, 2).
 * @param {any[]} sorted
 * @param {(item: any) => number|null} scoreFn
 * @returns {number[]}
 */
function assignRanks(sorted, scoreFn) {
  const ranks = []
  let rank = 1
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && scoreFn(sorted[i]) !== scoreFn(sorted[i - 1])) rank = i + 1
    ranks.push(rank)
  }
  return ranks
}

/**
 * Rank a pool of competitors using the workout schema.
 * Workout keys and scoring direction come entirely from the schema —
 * no workout names are hardcoded here.
 *
 * @param {Competitor[]} competitors
 * @param {WorkoutSchema} workoutSchema
 * @param {Filters} filters
 * @param {Competitor|null} predicted   optional virtual competitor to inject
 * @returns {Array} ranked competitors with overallRank, workoutRanks, points added
 */
export function rankCompetitors(competitors, workoutSchema, filters = {}, predicted = null) {
  let pool = applyFilters(competitors, filters)

  if (predicted) {
    pool = [...pool, { ...predicted, _isPredicted: true }]
  }

  pool = pool.map(c => ({ ...c, _key: c.user_id || `${c.name}||${c.event}` }))

  /** @type {Record<string, Record<string, number>>} */
  const workoutRanks = {}
  // How many real competitors scored each workout (used to penalise missing predicted scores)
  const scoredCounts = {}

  for (const [workoutKey, def] of Object.entries(workoutSchema)) {
    const scored = pool
      .map(c => ({ c, score: getWorkoutTotal(c, workoutKey) }))
      .filter(({ score }) => score !== null)

    scoredCounts[workoutKey] = scored.filter(({ c }) => !c._isPredicted).length

    scored.sort((a, b) =>
      def.scoring === 'asc' ? a.score - b.score : b.score - a.score
    )

    const ranks = assignRanks(scored, ({ score }) => score)
    scored.forEach(({ c }, i) => {
      if (!workoutRanks[c._key]) workoutRanks[c._key] = {}
      workoutRanks[c._key][workoutKey] = ranks[i]
    })
  }

  let result = pool.map(c => {
    const wRanks = workoutRanks[c._key] || {}
    let points = 0
    for (const workoutKey of Object.keys(workoutSchema)) {
      if (wRanks[workoutKey] != null) {
        points += wRanks[workoutKey]
      } else if (c._isPredicted) {
        // No score entered for this workout — penalise as dead last among real competitors
        points += scoredCounts[workoutKey] + 1
      }
    }
    return { ...c, workoutRanks: wRanks, points }
  })

  result.sort((a, b) => a.points - b.points)

  let overallRank = 1
  for (let i = 0; i < result.length; i++) {
    if (i > 0 && result[i].points !== result[i - 1].points) overallRank = i + 1
    result[i] = { ...result[i], overallRank }
  }

  return result
}

/**
 * Derive distinct filter options from a competitor/team array.
 * @param {any[]} items
 */
export function deriveFilterOptions(items) {
  const distinct = (key) =>
    [...new Set(items.map(c => c[key]).filter(Boolean))].sort()
  return {
    divisions:  distinct('division'),
    age_groups: distinct('age_group'),
    categories: distinct('category'),
    events:     distinct('event'),
  }
}

/**
 * Derive component columns for a workout-filtered table view.
 * Prefers the schema's component list for ordering and labels;
 * falls back to keys found in the actual data.
 *
 * @param {Competitor[]} competitors
 * @param {string} workoutKey
 * @param {WorkoutDef|null} workoutDef
 * @returns {Array<{ id: string, label: string, unit: string, getValue: (c: Competitor) => number|null }>}
 */
export function deriveComponentColumns(competitors, workoutKey, workoutDef) {
  const unit = workoutDef?.unit || 'unknown'

  const ids = workoutDef?.components?.length
    ? workoutDef.components.map(c => c.id)
    : [...new Set(competitors.flatMap(c => Object.keys(c.scores?.[workoutKey]?.components || {})))]

  return ids.map(id => {
    const schemaDef = workoutDef?.components?.find(c => c.id === id)
    const label = schemaDef?.label || componentLabel(id)
    return {
      id,
      label,
      unit,
      getValue: c => c.scores?.[workoutKey]?.components?.[id] ?? null,
    }
  })
}

/**
 * Format a workout total value for display, using the workout's unit.
 * For time workouts, prefers the stored display string over re-formatting seconds.
 * @param {any} competitor
 * @param {string} workoutKey
 * @param {WorkoutDef} workoutDef
 * @returns {string}
 */
export function formatWorkoutTotal(competitor, workoutKey, workoutDef) {
  const entry = competitor?.scores?.[workoutKey]
  if (!entry) return '—'
  if (entry.total != null) {
    if (workoutDef.unit === 'time') return entry.time || formatTime(entry.total)
    if (workoutDef.unit === 'kg')   return `${entry.total} kg`
    if (workoutDef.unit === 'km')   return `${Number(entry.total).toFixed(3)} km`
    return String(entry.total)
  }
  const vals = Object.values(entry.components || {})
  if (!vals.length) return '—'
  const sum = vals.reduce((a, b) => a + b, 0)
  if (workoutDef.unit === 'kg')   return `${sum} kg`
  if (workoutDef.unit === 'km')   return `${Number(sum).toFixed(3)} km`
  if (workoutDef.unit === 'time') return formatTime(sum)
  return String(sum)
}

/**
 * Summarise a member's scores for a single workout.
 * Members get component data from TI records; they may not have a team-level total.
 * Falls back to summing components when no total is stored.
 * @param {any} member
 * @param {string} workoutKey
 * @param {WorkoutDef} workoutDef
 * @returns {string}
 */
export function formatMemberWorkout(member, workoutKey, workoutDef) {
  const entry = member?.scores?.[workoutKey]
  if (!entry) return null
  if (entry.total != null) return formatWorkoutTotal(member, workoutKey, workoutDef)
  const comps = entry.components || {}
  const vals = Object.values(comps)
  if (!vals.length) return null
  const sum = vals.reduce((a, b) => a + b, 0)
  if (workoutDef.unit === 'kg') return `${sum} kg`
  if (workoutDef.unit === 'km') return `${Number(sum).toFixed(3)} km`
  if (workoutDef.unit === 'time') return formatTime(sum)
  return String(sum)
}

/**
 * Convert a snake_case component id to a readable label.
 * Handles rm prefixes like 1rm_, 3rm_, 5rm_ correctly.
 * @param {string} id
 */
export function componentLabel(id) {
  return id.split('_')
    .map(w => /^\d+rm$/.test(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/**
 * Format seconds as mm:ss or h:mm:ss.
 * @param {number} seconds
 */
export function formatTime(seconds) {
  if (!seconds && seconds !== 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}
