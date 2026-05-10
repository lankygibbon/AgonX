// @ts-check
import { ref, watch, computed } from 'vue'
import { useFiltersStore } from '../stores/filters.js'

const cache = {}

async function fetchJson(path) {
  if (cache[path]) return cache[path]
  const res = await fetch(path)
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`)
  cache[path] = await res.json()
  return cache[path]
}

/**
 * All available families + years derived from workouts.json structure.
 * Shared across all useData() callers — only fetched once.
 */
const allWorkouts = ref(null)
const indexLoaded = ref(false)

async function loadIndex() {
  if (indexLoaded.value) return
  const w = await fetchJson('/data/workouts.json')
  allWorkouts.value = w
  indexLoaded.value = true
}

/**
 * Derived families and years from workouts.json.
 * @returns {{ families: string[], yearsForFamily: (f: string) => string[] }}
 */
export function useWorkoutsIndex() {
  loadIndex()
  const families = computed(() => Object.keys(allWorkouts.value ?? {}))
  const yearsForFamily = (family) =>
    Object.keys(allWorkouts.value?.[family] ?? {}).sort().reverse()
  return { allWorkouts, families, yearsForFamily }
}

/**
 * Reactive data loader — reloads automatically when filters.family or filters.year changes.
 */
export function useData() {
  const filters = useFiltersStore()

  const workoutSchema = ref(null)
  const events = ref(null)
  const competitors = ref([])
  const teams = ref([])
  const loading = ref(true)
  const error = ref(null)

  async function load() {
    const family = filters.family
    const year = filters.year

    loading.value = true
    error.value = null
    try {
      const [w, e, c, t] = await Promise.all([
        fetchJson('/data/workouts.json'),
        fetchJson('/data/events.json'),
        fetchJson(`/data/competitors_${family}_${year}.json`).catch(() => ({ competitors: [] })),
        fetchJson(`/data/teams_${family}_${year}.json`).catch(() => ({ teams: [] })),
      ])
      allWorkouts.value = w
      workoutSchema.value = w[family]?.[String(year)] ?? null
      events.value = e.events ?? []
      competitors.value = c.competitors ?? []
      teams.value = t.teams ?? []
    } catch (err) {
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  watch([() => filters.family, () => filters.year], load, { immediate: true })

  return { workoutSchema, events, competitors, teams, loading, error }
}
