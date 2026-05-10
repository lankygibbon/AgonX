#!/usr/bin/env python3
"""
AgonX - ATHX Transform

Reads the raw scrape files produced by scraper_athx.py and transforms them
into the structured output files consumed by the webapp.

Inputs  (data/raw/):
  athx_{year}_workouts.json          (preferred — run scraper --type workouts first)
  athx_{year}_events.json            (preferred — run scraper --type events first)
  athx_{year}_individuals.json
  athx_{year}_team_individuals.json
  athx_{year}_teams.json

Outputs (data/ + synced to ../webapp/public/data/):
  workouts.json
  events.json
  competitors_athx_{year}.json       individual leaderboard records
  teams_athx_{year}.json             team records with members embedded

Usage:
  python transform_athx.py                        # transform all discovered years
  python transform_athx.py --year 2026            # specific year
  python transform_athx.py --year 2025 2026       # multiple years
  python transform_athx.py --embed-only           # re-embed members into existing teams
"""

import argparse
import difflib
import json
import os
import re
import shutil

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAW_DIR = os.path.join("data", "raw")
OUT_DIR = "data"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEBAPP_SYNC_DIRS = ["../webapp/public/data"]

# Lowercase column names that are never score data
INDIVIDUAL_META_COLS = {"rank", "user", "event", "country", "year", "division", "points"}
TEAM_META_COLS       = {"rank", "team", "event", "country", "year", "division", "points"}
TI_META_COLS         = {"rank", "user", "event", "country", "year", "division", "points", "team"}

# Hints for unit detection from column names when cell values aren't available
_KG_HINTS = {"squat", "press", "deadlift", "clean", "snatch", "overhead", "1rm", "3rm", "5rm", "10rm", "rep max"}
_KM_HINTS = {"run", "row", "bike", "ski", "erg", "swim", "distance", "km", "endurance", "treadmill"}

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def extract_user_name(user_field) -> str:
    if isinstance(user_field, dict):
        return user_field.get("name", "").strip()
    return str(user_field).strip()


def extract_country(user_field, fallback: str = "") -> str:
    if isinstance(user_field, dict):
        profile = user_field.get("profile_info") or {}
        nationality = profile.get("nationality") or {}
        code = nationality.get("code", "")
        if code:
            return code
    return fallback


def extract_user_id(user_field) -> str | None:
    if isinstance(user_field, dict):
        return user_field.get("id")
    return None


def parse_score_string(score_str: str) -> tuple[int | None, str | None]:
    """Parse '1 (293KG)' → (1, '293KG'). Returns (None, None) on failure."""
    if not score_str or score_str == "-":
        return None, None
    m = re.match(r"(\d+)\s+\((.+)\)", str(score_str).strip())
    if m:
        return int(m.group(1)), m.group(2)
    return None, str(score_str).strip()


def parse_kg(val: str) -> float | None:
    if val and str(val).upper().endswith("KG"):
        try:
            return float(str(val)[:-2])
        except ValueError:
            pass
    return None


def parse_km(val: str) -> float | None:
    if val and str(val).upper().endswith("KM"):
        try:
            return float(str(val)[:-2])
        except ValueError:
            pass
    return None


def time_to_seconds(t: str) -> int | None:
    if not t:
        return None
    parts = t.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return None


def parse_score_value(val, unit: str) -> float | int | None:
    """Convert a raw score string to a pure numeric value based on workout unit."""
    s = str(val).strip()
    if not s or s == "-":
        return None
    if unit == "kg":
        return parse_kg(s)
    if unit == "km":
        return parse_km(s)
    if unit == "time":
        return time_to_seconds(s)
    return None


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def load_json(path: str):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def save_json(path: str, data, sync: bool = True) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {path}")
    if sync:
        _sync(path)


def _sync(src_path: str) -> None:
    filename = os.path.basename(src_path)
    for dest_dir in WEBAPP_SYNC_DIRS:
        dest = os.path.join(SCRIPT_DIR, dest_dir, filename)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src_path, dest)
            print(f"  Synced: {dest_dir}/{filename}")
        except Exception as e:
            print(f"  Sync skipped ({dest_dir}): {e}")


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def build_schema_lookups(workout_schema: dict) -> tuple[dict, dict]:
    """
    Returns:
      label_to_key  — {"Strength": "strength", "Endurance": "endurance", ...}
      comp_label_to_id — {"strength": {"1RM Strict Press": "1rm_strict_press", ...}, ...}
    """
    label_to_key = {v["name"]: k for k, v in workout_schema.items()}
    comp_label_to_id = {
        k: {c["label"]: c["id"] for c in v.get("components", [])}
        for k, v in workout_schema.items()
    }
    return label_to_key, comp_label_to_id


def _detect_unit(rows: list, cols: list) -> str:
    """
    Detect workout unit from cell values, falling back to column name heuristics
    when no cell data is available (e.g. years with no individual leaderboard).
    Returns 'kg', 'km', 'time', or 'unknown'.
    """
    for row in rows:
        for col in cols:
            v = str(row.get(col, "")).strip().upper()
            if not v or v == "-":
                continue
            if v.endswith("KG"):
                return "kg"
            if v.endswith("KM"):
                return "km"
            if re.match(r"^\d+:\d+", v):
                return "time"
    # No cell values — infer from column names
    for col in cols:
        lower = col.lower()
        if any(t in lower for t in _KG_HINTS):
            return "kg"
        if any(t in lower for t in _KM_HINTS):
            return "km"
    return "unknown"


def derive_workout_schema(
    raw_individuals: dict,
    raw_team_individuals: dict = None,
    raw_workouts: dict = None,
) -> dict:
    """
    Derive a fully data-driven workout schema.

    When raw_workouts is provided (from --type workouts scrape), its filter IDs,
    component block IDs, and column lists take precedence. Unit is still detected
    from cell values in the individuals batches, falling back to column name
    heuristics for years where no individual data exists.
    """
    year = raw_individuals["year"]

    if raw_workouts:
        workout_filter_ids    = raw_workouts.get("workouts", {})
        workout_blocks        = raw_workouts.get("workout_blocks", {})
        workout_cols_override = raw_workouts.get("workout_columns", {})
    else:
        workout_filter_ids    = raw_individuals.get("filter_options", {}).get("workouts", {})
        workout_blocks        = {}
        workout_cols_override = {}
        if raw_team_individuals:
            workout_blocks = raw_team_individuals.get("filter_options", {}).get("workout_blocks", {})

    UNIT_TO_RESULT_FIELD = {"kg": "total_kg", "km": "total_km", "time": "time"}

    batches_by_workout: dict[str, list] = {}
    for batch in raw_individuals.get("batches", []):
        w_label = batch["filters"].get("workout")
        if w_label:
            batches_by_workout.setdefault(w_label, []).append(batch)

    schema = {}
    for w_label, w_filter_id in workout_filter_ids.items():
        schema_key = w_label.lower().replace(" ", "_")

        if w_label in workout_cols_override:
            score_cols = [
                col for col in workout_cols_override[w_label]
                if col.lower() not in INDIVIDUAL_META_COLS
            ]
            w_batches = batches_by_workout.get(w_label, [])
            first_batch = next((b for b in w_batches if b["rows"]), None)
            sample_rows = first_batch["rows"] if first_batch else []
        else:
            w_batches = batches_by_workout.get(w_label, [])
            first_batch = next((b for b in w_batches if b["rows"]), None)
            if not first_batch:
                schema[schema_key] = {
                    "name": w_label, "filter_id": w_filter_id,
                    "scoring": "desc", "unit": "unknown",
                    "result_field": "score", "components": [],
                }
                continue
            score_cols = [
                col for col in first_batch["rows"][0]
                if col.lower() not in INDIVIDUAL_META_COLS
            ]
            sample_rows = first_batch["rows"]

        unit         = _detect_unit(sample_rows, score_cols)
        scoring      = "asc" if unit == "time" else "desc"
        result_field = UNIT_TO_RESULT_FIELD.get(unit, "score")

        single_result      = len(score_cols) == 1 and score_cols[0] == w_label
        blocks_for_workout = workout_blocks.get(w_label, {})
        components = [] if single_result else [
            {
                "id":        col.lower().replace(" ", "_"),
                "label":     col,
                "unit":      unit,
                "filter_id": blocks_for_workout.get(col, ""),
            }
            for col in score_cols
        ]

        schema[schema_key] = {
            "name":         w_label,
            "filter_id":    w_filter_id,
            "scoring":      scoring,
            "unit":         unit,
            "result_field": result_field,
            "components":   components,
        }

    return {year: schema}


def derive_events(raw_individuals: dict, raw_events: dict = None) -> list[dict]:
    """
    Derive event list from a dedicated events raw file or the individuals raw file.
    """
    year = raw_individuals["year"]
    if raw_events:
        events_map = raw_events.get("events", {})
    else:
        events_map = raw_individuals.get("filter_options", {}).get("events", {})
    return [
        {
            "id":             val,
            "name":           label,
            "year":           int(year),
            "schema_family":  "athx",
            "workout_schema": year,
            "status":         "completed",
        }
        for label, val in events_map.items()
        if val and label != "All"
    ]


# ---------------------------------------------------------------------------
# Transform: individuals
# ---------------------------------------------------------------------------


def transform_individuals(raw: dict, workout_schema: dict) -> list[dict]:
    """
    Merge multi-pass individual batches into one record per athlete.

    Batches with workout=None are the 'Overall' pass (workout totals).
    Batches with a workout label are per-workout component passes.

    All score values are pure numerics — no unit suffixes. The unit is
    defined by the workout schema and available in workouts.json.
    For time-based workouts, 'total' is seconds and 'time' holds the
    display string.
    """
    year = raw["year"]
    label_to_key, comp_label_to_id = build_schema_lookups(workout_schema)
    merged: dict[tuple, dict] = {}

    for batch in raw["batches"]:
        f             = batch["filters"]
        workout_label = f.get("workout")
        workout_key   = label_to_key.get(workout_label) if workout_label else None
        workout_def   = workout_schema.get(workout_key) if workout_key else None

        for row in batch["rows"]:
            user_field = row.get("user")
            name  = extract_user_name(user_field)
            event = row.get("event", "").strip()
            key   = (name, event)

            if key not in merged:
                merged[key] = {
                    "name":      name,
                    "user_id":   extract_user_id(user_field),
                    "event":     event,
                    "country":   extract_country(user_field, row.get("country", "")),
                    "year":      int(year),
                    "division":  f["gender"],
                    "age_group": f["age_group"],
                    "category":  f["category"],
                    "scores":    {},
                }

            comp = merged[key]

            if workout_label is None:
                # Overall pass — workout totals from combined score strings e.g. "1 (293KG)"
                for wk, wdef in workout_schema.items():
                    raw_score = row.get(wdef["name"])
                    if raw_score is None:
                        continue
                    _, val_str = parse_score_string(str(raw_score))
                    if not val_str:
                        continue
                    total = parse_score_value(val_str, wdef["unit"])
                    if total is None:
                        continue
                    entry = comp["scores"].setdefault(wk, {})
                    entry["total"] = total
                    if wdef["unit"] == "time":
                        entry["time"] = val_str

            elif workout_def:
                # Per-workout pass — individual component scores
                unit           = workout_def["unit"]
                comp_map       = comp_label_to_id.get(workout_key, {})
                has_components = bool(workout_def.get("components"))
                entry          = comp["scores"].setdefault(workout_key, {})

                for col, val in row.items():
                    if col.lower() in INDIVIDUAL_META_COLS:
                        continue
                    numeric = parse_score_value(val, unit)
                    if has_components:
                        comp_id = comp_map.get(col, col.lower().replace(" ", "_"))
                        if numeric is not None:
                            entry.setdefault("components", {})[comp_id] = numeric
                    else:
                        # Single-result workout (e.g. MetCon X) — just store total
                        if numeric is not None:
                            entry["total"] = numeric
                        if unit == "time":
                            t = str(val).strip()
                            if t and t != "-":
                                entry["time"] = t

    competitors = list(merged.values())
    print(f"  Merged {len(competitors)} unique individuals from {len(raw['batches'])} batches")
    return competitors


# ---------------------------------------------------------------------------
# Transform: team-individuals (intermediate — embedded into teams)
# ---------------------------------------------------------------------------


def transform_team_individuals(raw: dict, workout_schema: dict) -> list[dict]:
    """
    Deduplicate team-individual batches into one record per athlete.
    Each batch is for a specific workout; rows contain that workout's
    component scores. There is no overall pass on this endpoint.

    This output is used as an intermediate step to embed member data
    into team records — it is not a primary webapp output.
    """
    year = raw["year"]
    label_to_key, comp_label_to_id = build_schema_lookups(workout_schema)
    merged: dict[tuple, dict] = {}

    for batch in raw["batches"]:
        f             = batch["filters"]
        workout_label = f.get("workout")
        workout_key   = label_to_key.get(workout_label) if workout_label else None
        workout_def   = workout_schema.get(workout_key) if workout_key else None

        if not workout_def:
            continue

        unit           = workout_def["unit"]
        comp_map       = comp_label_to_id.get(workout_key, {})
        has_components = bool(workout_def.get("components"))

        for row in batch["rows"]:
            user_field = row.get("user")
            name  = extract_user_name(user_field)
            event = row.get("event", "").strip()
            key   = (name, event)

            if key not in merged:
                merged[key] = {
                    "name":      name,
                    "user_id":   extract_user_id(user_field),
                    "event":     event,
                    "country":   extract_country(user_field, row.get("country", "")),
                    "year":      int(year),
                    "division":  f["gender"],
                    "age_group": f["age_group"],
                    "category":  f["category"],
                    "scores":    {},
                }

            ti    = merged[key]
            entry = ti["scores"].setdefault(workout_key, {})

            for col, val in row.items():
                if col.lower() in TI_META_COLS:
                    continue
                numeric = parse_score_value(val, unit)
                if has_components:
                    comp_id = comp_map.get(col, col.lower().replace(" ", "_"))
                    if numeric is not None:
                        entry.setdefault("components", {})[comp_id] = numeric
                else:
                    if numeric is not None:
                        entry["total"] = numeric
                    if unit == "time":
                        t = str(val).strip()
                        if t and t != "-":
                            entry["time"] = t

    result = list(merged.values())
    print(f"  Merged {len(result)} unique team-individuals from {len(raw['batches'])} batches")
    return result


# ---------------------------------------------------------------------------
# Transform: teams
# ---------------------------------------------------------------------------


def transform_teams(raw: dict, workout_schema: dict) -> list[dict]:
    """
    Merge team batches into one record per team.

    Overall pass gives workout totals; per-workout passes give component
    scores (the team's combined result per component).
    All values are pure numerics.
    """
    year = raw["year"]
    label_to_key, comp_label_to_id = build_schema_lookups(workout_schema)
    merged: dict[tuple, dict] = {}

    for batch in raw["batches"]:
        f             = batch["filters"]
        workout_label = f.get("workout")
        workout_key   = label_to_key.get(workout_label) if workout_label else None
        workout_def   = workout_schema.get(workout_key) if workout_key else None

        for row in batch["rows"]:
            team  = row.get("team", "").strip()
            event = row.get("event", "").strip()
            key   = (team, event)

            if key not in merged:
                merged[key] = {
                    "team":      team,
                    "event":     event,
                    "country":   row.get("country", ""),
                    "year":      int(year),
                    "division":  f["gender"],
                    "age_group": f["age_group"],
                    "category":  f["category"],
                    "scores":    {},
                }

            comp = merged[key]

            if workout_label is None:
                # Overall pass — workout totals from combined score strings
                for wk, wdef in workout_schema.items():
                    raw_score = row.get(wdef["name"])
                    if raw_score is None:
                        continue
                    _, val_str = parse_score_string(str(raw_score))
                    if not val_str:
                        continue
                    total = parse_score_value(val_str, wdef["unit"])
                    if total is None:
                        continue
                    entry = comp["scores"].setdefault(wk, {})
                    entry["total"] = total
                    if wdef["unit"] == "time":
                        entry["time"] = val_str

            elif workout_def:
                # Per-workout pass — team's combined component scores
                unit           = workout_def["unit"]
                comp_map       = comp_label_to_id.get(workout_key, {})
                has_components = bool(workout_def.get("components"))
                entry          = comp["scores"].setdefault(workout_key, {})

                for col, val in row.items():
                    if col.lower() in TEAM_META_COLS:
                        continue
                    numeric = parse_score_value(val, unit)
                    if has_components:
                        comp_id = comp_map.get(col, col.lower().replace(" ", "_"))
                        if numeric is not None:
                            entry.setdefault("components", {})[comp_id] = numeric
                    else:
                        if numeric is not None:
                            entry["total"] = numeric
                        if unit == "time":
                            t = str(val).strip()
                            if t and t != "-":
                                entry["time"] = t

    result = list(merged.values())
    print(f"  Merged {len(result)} unique teams from {len(raw['batches'])} batches")
    return result


# ---------------------------------------------------------------------------
# Member embedding
# ---------------------------------------------------------------------------


def embed_team_members(teams: list[dict], team_individuals: list[dict]) -> list[dict]:
    """
    Embed individual member records (with their per-workout component scores)
    directly into each team object.

    Splits team names on ' & ' or ',' to find member names, then matches
    against team-individual records at the same event + division using
    difflib similarity. The full scores object from the matched TI record
    is embedded in the team's members array.
    """
    by_event_div: dict[tuple, list] = {}
    for ti in team_individuals:
        k = (ti["event"], ti.get("division"))
        by_event_div.setdefault(k, []).append(ti)

    total_slots   = 0
    total_matched = 0

    for team in teams:
        member_names = [
            n.strip()
            for n in re.split(r"\s*&\s*|\s*,\s*", team["team"])
            if n.strip()
        ]
        # Mixed teams: each athlete files under their own gender in TI records,
        # so search all gender buckets for this event rather than just "Mixed".
        division = team.get("division")
        if division == "Mixed":
            candidates = [
                ti
                for k, tis in by_event_div.items()
                if k[0] == team["event"]
                for ti in tis
            ]
        else:
            candidates = by_event_div.get((team["event"], division), [])
        members    = []
        used_ids: set = set()

        for target_name in member_names:
            best_ti, best_sim = None, 0.0
            for ti in candidates:
                if ti.get("user_id") in used_ids:
                    continue
                sim = difflib.SequenceMatcher(
                    None, target_name.lower(), ti["name"].lower()
                ).ratio()
                if sim > best_sim:
                    best_sim, best_ti = sim, ti

            total_slots += 1
            if best_ti and best_sim >= 0.6:
                if best_ti["user_id"] is not None:
                    used_ids.add(best_ti["user_id"])
                total_matched += 1
                members.append({
                    "name":             best_ti["name"],
                    "user_id":          best_ti["user_id"],
                    "match_confidence": round(best_sim, 3),
                    "scores":           best_ti["scores"],
                })
            else:
                members.append({
                    "name":             target_name,
                    "user_id":          None,
                    "match_confidence": round(best_sim, 3),
                    "scores":           {},
                })

        team["members"] = members

    print(f"  Members embedded: {total_matched}/{total_slots} matched")
    return teams


# ---------------------------------------------------------------------------
# Component contribution inference
# ---------------------------------------------------------------------------


def infer_component_contributions(teams: list[dict], workout_schema: dict) -> dict:
    """
    Determine whether each workout component is per_person (each athlete
    contributes independently; team total = sum) or combined (team acts as
    one unit; team total ≠ sum of members).

    Method: for each (workout, component), collect pairs of
    (team_value, sum_of_matched_member_values) across all teams that have
    both. If ≥60% of samples are additive (within 5% relative tolerance)
    → per_person = True. Otherwise → per_person = False.

    Requires at least 3 samples to make a determination; defaults to True
    when data is insufficient.
    """
    import copy
    schema = copy.deepcopy(workout_schema)

    for wkey, wdef in schema.items():
        if not wdef.get("components"):
            continue

        for comp in wdef["components"]:
            comp_id = comp["id"]
            matches = 0
            samples = 0

            for team in teams:
                team_val = (
                    team.get("scores", {})
                        .get(wkey, {})
                        .get("components", {})
                        .get(comp_id)
                )
                if team_val is None:
                    continue

                member_vals = [
                    m.get("scores", {}).get(wkey, {}).get("components", {}).get(comp_id)
                    for m in team.get("members", [])
                ]
                member_vals = [v for v in member_vals if v is not None]
                if not member_vals:
                    continue

                member_sum = sum(member_vals)
                samples += 1
                denom = max(abs(team_val), 0.001)
                if abs(team_val - member_sum) / denom <= 0.05:
                    matches += 1

            if samples >= 3:
                per_person = (matches / samples) >= 0.6
            else:
                per_person = True  # not enough data — assume additive

            comp["per_person"] = per_person
            flag = "per-person" if per_person else "combined"
            print(f"    {wkey}.{comp_id}: {flag} ({matches}/{samples} additive)")

    return schema


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AgonX ATHX transform")
    parser.add_argument(
        "--year", nargs="*", default=None,
        help="Years to transform (default: all years with raw data)",
    )
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Re-embed members into existing team files without re-transforming",
    )
    args = parser.parse_args()

    # Discover years from available raw files if not specified
    if args.year:
        years = args.year
    else:
        years = sorted(
            {
                f.split("_")[1]
                for f in os.listdir(RAW_DIR)
                if re.match(r"athx_\d{4}_teams\.json", f)
            },
            reverse=True,
        )
        print(f"Discovered years from raw files: {years}")

    # --embed-only: re-run member embedding on existing processed files
    if args.embed_only:
        print("*** EMBED ONLY — re-embedding members into existing team files ***")
        workouts_path = os.path.join(OUT_DIR, "workouts.json")
        all_workouts  = load_json(workouts_path) or {"athx": {}}
        for year in years:
            ti_path    = os.path.join(OUT_DIR, f"team_individuals_athx_{year}.json")
            teams_path = os.path.join(OUT_DIR, f"teams_athx_{year}.json")
            if not os.path.exists(ti_path) or not os.path.exists(teams_path):
                print(f"  Missing processed files for {year}, skipping.")
                continue
            workout_schema = all_workouts.get("athx", {}).get(year)
            if not workout_schema:
                print(f"  No workout schema for {year} in workouts.json, skipping.")
                continue
            ti_data    = load_json(ti_path)
            teams_data = load_json(teams_path)
            print(f"\nEmbedding {year}...")
            teams = embed_team_members(
                [dict(t) for t in teams_data.get("teams", [])],
                ti_data.get("team_individuals", []),
            )
            print(f"  Inferring component contributions for {year}...")
            workout_schema = infer_component_contributions(teams, workout_schema)
            all_workouts["athx"][year] = workout_schema
            save_json(workouts_path, all_workouts)
            save_json(
                teams_path,
                {"schema_family": "athx", "workout_schema": year, "teams": teams},
            )
        print("\nDone.")
        return

    # Load existing workouts/events to merge into
    workouts_path      = os.path.join(OUT_DIR, "workouts.json")
    events_path        = os.path.join(OUT_DIR, "events.json")
    all_workouts       = load_json(workouts_path) or {"athx": {}}
    all_events         = load_json(events_path)   or {"events": []}
    existing_event_ids = {e["id"] for e in all_events.get("events", [])}

    for year in years:
        print(f"\n{'#'*60}\n  YEAR: {year}\n{'#'*60}")

        # Load raw files
        raw_workouts_file = load_json(os.path.join(RAW_DIR, f"athx_{year}_workouts.json"))
        raw_events_file   = load_json(os.path.join(RAW_DIR, f"athx_{year}_events.json"))
        raw_individuals   = load_json(os.path.join(RAW_DIR, f"athx_{year}_individuals.json"))
        raw_ti            = load_json(os.path.join(RAW_DIR, f"athx_{year}_team_individuals.json"))
        raw_teams         = load_json(os.path.join(RAW_DIR, f"athx_{year}_teams.json"))

        if not raw_workouts_file and not raw_individuals and not raw_ti and not raw_teams:
            print(f"  No raw data found for {year}, skipping.")
            continue

        # Derive workout schema — stub minimal raw_individuals if not available
        # (2024/2023 have no individual leaderboard data)
        ind_for_schema = raw_individuals or {"year": year, "filter_options": {}, "batches": []}
        raw_ti_for_schema = raw_ti if not raw_workouts_file else None
        year_schema    = derive_workout_schema(ind_for_schema, raw_ti_for_schema, raw_workouts_file)
        workout_schema = year_schema[year]

        if not workout_schema:
            print(f"  Could not derive workout schema for {year}, skipping.")
            continue

        print(f"\n  Workout schema: {list(workout_schema.keys())}")

        # Save / merge workouts.json
        all_workouts.setdefault("athx", {})[year] = workout_schema
        save_json(workouts_path, all_workouts)

        # Save / merge events.json
        events_src = raw_events_file or ind_for_schema
        for evt in derive_events(ind_for_schema, raw_events_file):
            if evt["id"] not in existing_event_ids:
                all_events["events"].append(evt)
                existing_event_ids.add(evt["id"])
        save_json(events_path, all_events)

        # ── Individuals ────────────────────────────────────────────────────
        if raw_individuals and raw_individuals.get("batches"):
            print(f"\nTransforming individuals — {year}")
            competitors = transform_individuals(raw_individuals, workout_schema)
            if competitors:
                save_json(
                    os.path.join(OUT_DIR, f"competitors_athx_{year}.json"),
                    {"schema_family": "athx", "workout_schema": year, "competitors": competitors},
                )
            else:
                print(f"  No individual records found for {year}")
        else:
            print(f"\n  No individual leaderboard data for {year} — skipping competitors file")

        # ── Team-individuals (intermediate) ────────────────────────────────
        team_individuals = None
        if raw_ti:
            print(f"\nTransforming team-individuals — {year}")
            team_individuals = transform_team_individuals(raw_ti, workout_schema)
            # Save as intermediate (not synced to webapp)
            save_json(
                os.path.join(OUT_DIR, f"team_individuals_athx_{year}.json"),
                {"schema_family": "athx", "workout_schema": year, "team_individuals": team_individuals},
                sync=False,
            )

        # ── Teams ──────────────────────────────────────────────────────────
        if raw_teams:
            print(f"\nTransforming teams — {year}")
            teams = transform_teams(raw_teams, workout_schema)

            # Fall back to saved TI if not freshly transformed
            if team_individuals is None:
                saved_ti = load_json(os.path.join(OUT_DIR, f"team_individuals_athx_{year}.json"))
                if saved_ti:
                    team_individuals = saved_ti.get("team_individuals", [])

            if team_individuals:
                print(f"  Embedding member data...")
                teams = embed_team_members(teams, team_individuals)
                print(f"  Inferring component contributions...")
                workout_schema = infer_component_contributions(teams, workout_schema)
                all_workouts["athx"][year] = workout_schema
                save_json(workouts_path, all_workouts)
            else:
                print("  No team-individual data available — members will not be embedded")

            save_json(
                os.path.join(OUT_DIR, f"teams_athx_{year}.json"),
                {"schema_family": "athx", "workout_schema": year, "teams": teams},
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
