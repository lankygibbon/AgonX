# AgonX — CLAUDE.md

## What This Is

AgonX is a fitness competition leaderboard and rank prediction tool. Competitor scores are scraped from results pages, transformed into flat JSON, and served statically. The Vue 3 webapp reads the JSON at runtime, computes ranks dynamically, and lets users predict where they would place.

Current data: **ATHX 2026** (individuals + teams).  
Live site: `https://lankygibbon.github.io/AgonX/`

---

## Repo Layout

```
AgonX/
  scrapers/               ← Python scraper + transform (see below)
    transform_athx.py     ← main transform: builds all JSON output files
    data/                 ← raw scrape output (gitignored)
  webapp/                 ← Vue 3 app
    public/
      data/               ← JSON served statically (committed to repo)
        workouts.json
        events.json
        competitors_athx_2026.json
        teams_athx_2026.json
    src/
      components/
        LeaderboardTable.vue   ← main ranked table + accordion member rows
        RankAnalysis.vue       ← predicted rank summary cards + ECharts histograms
        FilterBar.vue          ← division / age group / category / event dropdowns
      pages/
        LeaderboardPage.vue
        PredictPage.vue        ← individual + team rank prediction
        AthletePage.vue        ← per-athlete profile with scores
      stores/
        filters.js             ← Pinia: active filter state
        prediction.js          ← Pinia: prediction inputs + virtual competitor builder
      lib/
        ranking.js             ← pure ranking logic (no Vue dependency)
        useData.js             ← reactive data loader composable
      router/index.js          ← hash-mode Vue Router
  .github/workflows/deploy.yml ← GitHub Actions: build + deploy to GitHub Pages
  AGONX_DATA_ARCHITECTURE.md  ← original design doc (data shape intentions)
```

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | Vue 3 + Vite, plain JS with JSDoc (no TypeScript) |
| Styling | Tailwind CSS v4 (`@tailwindcss/vite` plugin) |
| State | Pinia |
| Routing | Vue Router — **hash mode** (`createWebHashHistory`) for GitHub Pages |
| Charts | Apache ECharts via `vue-echarts` — registered locally per component |
| Data fetching | Native `fetch()` with a module-level cache in `useData.js` |

**PrimeVue was removed** — it was injecting Aura light-mode CSS at runtime and overriding the dark theme. Do not re-add it.

---

## Running Locally

```bash
cd webapp
npm ci
npm run dev        # dev server at localhost:5173
npm run build      # production build → dist/
```

Data files live in `webapp/public/data/` and are fetched at runtime — no build step required for data changes.

---

## Deployment

Push to `main` → GitHub Actions builds the webapp and deploys via the official Pages API (`actions/upload-pages-artifact` + `actions/deploy-pages`). The Pages source must be set to **GitHub Actions** (not a branch) in repo settings.

`vite.config.js` has `base: '/AgonX/'` for the sub-path. All data fetches are prefixed with `import.meta.env.BASE_URL` in `useData.js` — do not use absolute `/data/...` paths directly.

If switching to a custom domain: change `base: '/'` in `vite.config.js` and update the CNAME. Hash routing can optionally be switched to history mode if the host supports URL rewrites.

---

## Data Shape (Actual)

The architecture doc (`AGONX_DATA_ARCHITECTURE.md`) describes the original intended format. The actual scraped + transformed data uses a normalised shape:

**Score entry** (same structure for every workout type):
```json
{
  "total": 293,
  "components": {
    "back_squat": 100,
    "strict_press": 50,
    "deadlift": 143
  }
}
```
Time-based workouts also carry a display string:
```json
{ "total": 546, "time": "09:06" }
```

`total` may be `null` when only components were captured — `getWorkoutTotal()` in `ranking.js` falls back to summing components.

**`workouts.json`** schema per workout:
```json
{
  "name": "Strength",
  "scoring": "desc",
  "unit": "kg",
  "components": [
    { "id": "back_squat", "label": "Back Squat", "unit": "kg", "per_person": true }
  ]
}
```
`per_person: true` means each team member contributes independently (totals sum); `false` means the team shares one combined score. This flag is inferred by `transform_athx.py` by comparing team totals against sum of member values.

---

## Ranking Logic (`src/lib/ranking.js`)

1. Filter the competitor pool by active filter state (division, age_group, category, event)
2. For each workout: sort filtered pool by `total` in schema `scoring` direction; assign ranks with tie-sharing (1, 1, 3 not 1, 1, 2)
3. Points = sum of per-workout ranks (lower = better)
4. Overall rank = sort by points ascending

**Predicted competitor:** built by `prediction.js` and injected into the pool before ranking. If the user has not entered a score for a workout, they receive `real_scored_count + 1` points for that workout (dead last) rather than 0 — this prevents empty inputs from placing the user first.

---

## Scraper (`scrapers/transform_athx.py`)

Reads raw JSON from `scrapers/data/`, transforms and merges, writes output JSON to `webapp/public/data/`.

Key steps:
- Normalises score structure to `{ total, components }` for all workout types
- `embed_team_members()`: matches TI (team-individual) records to teams by name similarity. Mixed division teams are matched against Male + Female TI pools (there is no "Mixed" TI division in the source data)
- `infer_component_contributions()`: sets `per_person` on schema components by statistical comparison of team totals vs sum of member values
- `used_ids` guard: only adds `user_id` to the deduplication set when it is not `None`, to avoid blocking all subsequent None-uid records

Run with:
```bash
cd scrapers
python transform_athx.py            # full transform
python transform_athx.py --embed-only  # re-embed team members without re-scraping
```

---

## Key Design Decisions

- **Ranks are never stored** — always computed at runtime against the filtered pool. This means filtering to an age group gives you points as if that were a standalone competition.
- **Hash routing** — `/#/leaderboard`, `/#/predict`. No server config needed for GitHub Pages deep links.
- **ECharts registered locally** — `use([CanvasRenderer, BarChart, GridComponent, TooltipComponent])` called inside `RankAnalysis.vue` only, not globally. This avoids inflating the bundle for components that don't need charts.
- **`useData.js` module-level cache** — `allWorkouts`, `indexLoaded`, and `cache{}` are module-level singletons. Multiple `useData()` callers share the same fetched data without re-requesting.
