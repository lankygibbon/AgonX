# AgonX Data Architecture

## Overview

AgonX is a multi-competition fitness leaderboard and rank prediction tool. The data layer is built around three JSON files that reference each other via compound keys. The architecture is designed to support multiple competition families (ATHX, HYROX, CrossFit) and multiple years without restructuring.

---

## File Structure

```
/data
  workouts.json            ← scoring schemas per family and year
  events.json              ← event metadata, references workout schema
  competitors_athx_2026.json   ← competitor scores, one file per family/year
  competitors_athx_2027.json
  competitors_hyrox_2026.json
```

---

## workouts.json

Defines what is being tested and how it is scored. Keyed by `schema_family` then `year`. Each workout has a `scoring` direction (`asc` or `desc`), a `unit`, and an optional `components` array for sub-elements. An empty `components` array means the workout is atomic (no breakdown).

Ranking logic must use `scoring` direction per workout — time is `asc` (lower is better), kg and km are `desc` (higher is better).

```json
{
  "athx": {
    "2026": {
      "strength": {
        "scoring": "desc",
        "unit": "kg",
        "components": [
          { "id": "back_squat", "label": "Back Squat", "unit": "kg" },
          { "id": "strict_press", "label": "Strict Press", "unit": "kg" },
          { "id": "deadlift", "label": "Deadlift", "unit": "kg" }
        ]
      },
      "endurance": {
        "scoring": "desc",
        "unit": "km",
        "components": [
          { "id": "run_km", "label": "Run", "unit": "km" },
          { "id": "row_km", "label": "Row", "unit": "km" }
        ]
      },
      "metcon_x": {
        "scoring": "asc",
        "unit": "seconds",
        "components": []
      }
    }
  },
  "hyrox": {
    "2026": { }
  }
}
```

---

## events.json

Lightweight event metadata. A single file covering all families and years. Each event references its workout schema via `schema_family` + `workout_schema`. These two keys form a compound lookup into `workouts.json`.

`status` values: `upcoming` | `in_progress` | `completed`

Available filter options (divisions, age groups, categories) are **never declared here** — they are derived dynamically from the competitor data to avoid empty filter states.

```json
{
  "events": [
    {
      "id": "athx-london-2026",
      "name": "ATHX LONDON 2026",
      "year": 2026,
      "date": "2026-03-15",
      "country": "GB",
      "city": "London",
      "venue": "ExCeL London",
      "status": "completed",
      "schema_family": "athx",
      "workout_schema": "2026"
    }
  ]
}
```

---

## competitors_[family]_[year].json

One file per schema family per year. Each competitor record stores raw scores only — ranks and points are never stored, always computed at query time from the filtered dataset.

**Strength** stores individual lift values plus a `total_kg` taken from the source (use this as the source of truth and validate component maths against it).

**Endurance** stores individual segment distances plus a `total_km`.

**MetCon X** stores the display time string and `time_seconds` for sorting without parsing.

```json
{
  "schema_family": "athx",
  "workout_schema": "2026",
  "competitors": [
    {
      "name": "Sara Lofberg",
      "event_id": "athx-london-2026",
      "country": "SE",
      "year": 2026,
      "division": "Female",
      "age_group": "Open",
      "category": "ATHX",
      "scores": {
        "strength": {
          "lifts": {
            "back_squat": 100,
            "strict_press": 50,
            "deadlift": 143
          },
          "total_kg": 293
        },
        "endurance": {
          "segments": {
            "run_km": 2.687,
            "row_km": 2.000
          },
          "total_km": 4.687
        },
        "metcon_x": {
          "time": "09:06",
          "time_seconds": 546
        }
      }
    }
  ]
}
```

---

## Ranking Logic

Ranks and points are computed at runtime against the **filtered** competitor pool, never stored.

```
1. Apply filters (division, age_group, category, event, year)
2. For each workout:
   - Sort filtered pool by the workout's total score in schema scoring direction
   - Assign rank position (handle ties as shared rank, next rank skips — e.g. 1, 1, 3)
3. Points = sum of all workout ranks for each competitor
4. Overall rank = sort by points ascending
```

To look up scoring direction:
```
workouts[event.schema_family][event.workout_schema][workout_id].scoring
```

---

## Filter Derivation

All available filter options are derived dynamically from the competitor dataset:

```
distinct(competitors, 'division')    → Division filter options
distinct(competitors, 'age_group')   → Age Group filter options
distinct(competitors, 'category')    → Category filter options
distinct(competitors, 'event_id')    → Event filter options
```

Filter by `event_id` to join to `events.json` for display metadata (city, date, venue).

---

## Predicted Score / Rank Simulation

To simulate where a user would place, construct a virtual competitor object in the same shape as a competitor record and inject it into the filtered pool before running the ranking logic. No special handling required — it runs through the same pipeline as real data.

The UI should allow users to enter scores at the **component level** (individual lifts, run km, row km separately) rather than totals only. Totals are then derived by summing components. This matches how athletes naturally think about their performance and makes the tool more useful for goal-setting.

```json
{
  "name": "You (predicted)",
  "event_id": null,
  "division": "Female",
  "age_group": "Open",
  "category": "ATHX",
  "scores": {
    "strength": {
      "lifts": {
        "back_squat": 90,
        "strict_press": 45,
        "deadlift": 125
      },
      "total_kg": 260
    },
    "endurance": {
      "segments": {
        "run_km": 2.5,
        "row_km": 2.0
      },
      "total_km": 4.5
    },
    "metcon_x": { "time": "10:30", "time_seconds": 630 }
  }
}
```

Component fields are optional — if the user enters only a total (or the workout has no components), ranking still works. Where components are provided, `total_*` is derived from them; where only a total is provided it is taken at face value.

The input form should be driven by the `components` array in `workouts.json` for the selected schema, so it automatically adapts to different competition families and years without hardcoding field names.

---

## Data Sourcing (Scraping)

Competitor data is sourced by scraping competition results pages. Scrapers are expected to run in **multiple passes** — a single pass may not yield all required fields, and different data (e.g. overall results vs. workout breakdowns vs. component scores) may live on different pages or require separate requests.

Design principles for scrapers:

- **Additive passes**: each pass writes only the fields it collects; a merge step combines passes into the final competitor record. Never overwrite a field that was already populated by a prior pass.
- **Partial records are valid during collection**: a competitor record mid-scrape may be missing components or totals. Validation (checking totals match component sums, checking required fields exist) runs only after all passes are complete.
- **Idempotent runs**: re-running a pass should produce the same output. Scrapers should not duplicate competitor entries.
- **Source fields**: each competitor record should carry a `_source` metadata block (stripped before production use) noting which pass populated which fields, to aid debugging.

The `components` array in `workouts.json` defines exactly which per-component fields the scraper needs to collect for each workout. This is the authoritative checklist — a pass is considered complete when all component `id` values for a workout are present in the competitor record.

---

## Adding a New Competition Family

1. Add a new family key to `workouts.json` with the year block and workout definitions
2. Add events to `events.json` with the correct `schema_family` and `workout_schema`
3. Create a `competitors_[family]_[year].json` file with scores shaped to match the new schema

No changes to ranking logic or filter derivation are required.