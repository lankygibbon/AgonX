#!/usr/bin/env python3
"""
AgonX - ATHX Raw Leaderboard Scraper

Fetches data from athxgames.com and stores it as faithfully as possible,
with filter context attached to each batch of results. No parsing or merging
is done here — run transform_athx.py to produce the processed output files.

Outputs (to data/raw/):
  athx_{year}_workouts.json          workout metadata (filter IDs, columns, blocks)
  athx_{year}_individuals.json       raw individual leaderboard batches
  athx_{year}_team_individuals.json  raw team-individual leaderboard batches
  athx_{year}_teams.json             raw team leaderboard batches

Usage:
  python scraper_athx.py                              # scrape all discovered years, all types
  python scraper_athx.py --year 2026                  # specific year only
  python scraper_athx.py --year 2025 2026             # multiple years
  python scraper_athx.py --type events                # event metadata only (fast)
  python scraper_athx.py --type workouts              # workout metadata only (fast)
  python scraper_athx.py --type individuals           # individuals only
  python scraper_athx.py --type team-individuals      # team-individuals only
  python scraper_athx.py --type teams                 # teams only
  python scraper_athx.py --test                       # first page / first combo only
"""

import argparse
import html as html_module
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://athxgames.com"
INDIVIDUAL_PATH = "/individual-leaderboards"
TEAM_INDIVIDUAL_PATH = "/team-individual-leaderboards"
TEAM_PATH = "/team-leaderboards"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "X-Inertia": "true",
    "X-Inertia-Version": "",
    "User-Agent": "Mozilla/5.0 (compatible; AgonX-Scraper/1.0)",
}

DELAY = 0.75  # seconds between requests

RAW_DIR = os.path.join("data", "raw")

# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def connect(path: str = INDIVIDUAL_PATH) -> requests.Session:
    """
    Warm up (plain GET to extract the Inertia version from the HTML),
    then return an authenticated session.
    """
    print("Connecting to athxgames.com...")
    warmup = requests.get(
        f"{BASE_URL}{path}",
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=15,
    )
    warmup.raise_for_status()
    m = re.search(r'data-page="([^"]+)"', warmup.text)
    if m:
        page_data = json.loads(html_module.unescape(m.group(1)))
        HEADERS["X-Inertia-Version"] = page_data.get("version", "")
        print(f"Inertia version: {HEADERS['X-Inertia-Version']}")

    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_page(session: requests.Session, url: str) -> dict:
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "version" in data:
        HEADERS["X-Inertia-Version"] = data["version"]
        session.headers.update({"X-Inertia-Version": data["version"]})
    return data.get("props", {})


def build_url(path: str, params: dict) -> str:
    parts = [f"filters%5B{k}%5D={v}" for k, v in params.items()]
    parts.append("search=")
    return f"{BASE_URL}{path}?{'&'.join(parts)}"


def build_filter_lookup(filters: list) -> dict:
    return {
        f["key"]: {opt["label"]: opt["value"] for opt in f["options"]}
        for f in filters
    }


def paginate(session: requests.Session, first_url: str, test_mode: bool = False) -> list:
    """Fetch all pages for a URL and return the combined row list."""
    rows = []
    url = first_url
    while url:
        props = get_page(session, url)
        results = props.get("results", {})
        rows.extend(results.get("data", []))
        next_url = results.get("links", {}).get("next")
        if next_url and not test_mode:
            url = next_url
            time.sleep(DELAY)
        else:
            break
    return rows


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {path}")


def load_json(path: str):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Filter option extraction (saved alongside raw batches)
# ---------------------------------------------------------------------------


def fetch_filter_options(session: requests.Session, year: str) -> dict:
    """
    Fetch filter options from all three leaderboard endpoints and return
    a combined dict keyed by leaderboard type.
    """
    options = {}
    endpoints = {
        "individuals": INDIVIDUAL_PATH,
        "team_individuals": TEAM_INDIVIDUAL_PATH,
        "teams": TEAM_PATH,
    }
    for key, path in endpoints.items():
        try:
            props = get_page(session, build_url(path, {"year": year}))
            lookup = build_filter_lookup(props.get("filters", []))
            options[key] = {k: {l: v for l, v in vs.items() if v or l == "All"}
                            for k, vs in lookup.items()}
            time.sleep(DELAY)
        except Exception as e:
            print(f"  Warning: could not fetch filters for {key}: {e}")
    return options


# ---------------------------------------------------------------------------
# Year discovery
# ---------------------------------------------------------------------------


def discover_years(session: requests.Session) -> list[str]:
    """
    Fetch available years from all three leaderboard endpoints and union the
    results. Different endpoints may cover different year ranges.
    """
    print("Discovering available years...")
    years: dict[str, None] = {}  # ordered set via insertion-order dict
    for label, path in [
        ("individuals",  INDIVIDUAL_PATH),
        ("team-indiv",   TEAM_INDIVIDUAL_PATH),
        ("teams",        TEAM_PATH),
    ]:
        props = get_page(session, f"{BASE_URL}{path}")
        lookup = build_filter_lookup(props.get("filters", []))
        ep_years = [v for v in lookup.get("year", {}).values() if v]
        new = [y for y in ep_years if y not in years]
        for y in ep_years:
            years[y] = None
        print(f"  {label}: {ep_years} ({len(new)} new)")
        time.sleep(DELAY)
    result = list(years)
    print(f"  Total years: {result}")
    return result


# ---------------------------------------------------------------------------
# Raw scrape functions
# ---------------------------------------------------------------------------


def scrape_events_raw(session: requests.Session, year: str) -> dict:
    """
    Lightweight events metadata scrape — no athlete pagination.
    Checks all three leaderboard endpoints and unions the results so that
    events which only appear in team data are not missed.
    """
    print(f"\n{'='*60}\n  Scraping EVENTS (metadata only) — {year}\n{'='*60}")
    events: dict[str, str] = {}
    for label, path in [
        ("individuals",    INDIVIDUAL_PATH),
        ("team-indiv",     TEAM_INDIVIDUAL_PATH),
        ("teams",          TEAM_PATH),
    ]:
        props = get_page(session, build_url(path, {"year": year}))
        lookup = build_filter_lookup(props.get("filters", []))
        new = {l: v for l, v in lookup.get("event", {}).items() if v and l != "All"}
        before = len(events)
        events.update(new)
        print(f"  {label}: {len(new)} events ({len(events) - before} new)")
        time.sleep(DELAY)
    print(f"  Total: {list(events.keys())}")
    return {"events": events}


def scrape_workouts_raw(session: requests.Session, year: str) -> dict:
    """
    Lightweight workout metadata scrape — no athlete pagination.

    Fetches:
      - event_workout filter IDs (from individual leaderboard seed)
      - First-page column headers per workout (to discover component column names)
      - event_workout_block filter IDs per workout (from team-individual leaderboard)

    Returns a dict ready to be saved as athx_{year}_workouts.json.
    """
    print(f"\n{'='*60}\n  Scraping WORKOUTS (metadata only) — {year}\n{'='*60}")

    # Workout filter IDs + column headers from individual leaderboard seed.
    # For older years the individual leaderboard may have no workout data, in
    # which case we fall back to the team endpoint for columns.
    props = get_page(session, build_url(INDIVIDUAL_PATH, {"year": year}))
    lookup = build_filter_lookup(props.get("filters", []))
    workouts = {l: v for l, v in lookup.get("event_workout", {}).items() if v}
    print(f"  Individual workouts: {list(workouts.keys())}")
    time.sleep(DELAY)

    workout_columns: dict[str, list[str]] = {}
    for w_label, w_id in workouts.items():
        w_props = get_page(session, build_url(INDIVIDUAL_PATH, {"year": year, "event_workout": w_id}))
        rows = w_props.get("results", {}).get("data", [])
        workout_columns[w_label] = list(rows[0].keys()) if rows else []
        print(f"  {w_label} columns (individual): {workout_columns[w_label]}")
        time.sleep(DELAY)

    # For years with no individual workout data, derive workouts + columns from
    # the team endpoint (which covers all years).
    if not workouts:
        print("  No individual workout data — falling back to team endpoint for columns")
        team_seed = get_page(session, build_url(TEAM_PATH, {"year": year}))
        team_lookup = build_filter_lookup(team_seed.get("filters", []))
        team_workouts = {l: v for l, v in team_lookup.get("event_workout", {}).items() if v}
        print(f"  Team workouts: {list(team_workouts.keys())}")
        time.sleep(DELAY)

        for w_label, w_id in team_workouts.items():
            w_props = get_page(session, build_url(TEAM_PATH, {"year": year, "event_workout": w_id}))
            rows = w_props.get("results", {}).get("data", [])
            workout_columns[w_label] = list(rows[0].keys()) if rows else []
            print(f"  {w_label} columns (team): {workout_columns[w_label]}")
            time.sleep(DELAY)

        # Use team workout IDs as canonical when individual has none
        workouts = team_workouts

    # Workout block (component) filter IDs — check both team-individual and team
    # endpoints. Each endpoint has its own workout filter IDs (different from the
    # individual endpoint), so we seed each one to get its correct IDs first.
    # Blocks from both endpoints are merged per workout.
    workout_blocks: dict[str, dict[str, str]] = {}

    for ep_label, ep_path in [("team-indiv", TEAM_INDIVIDUAL_PATH), ("teams", TEAM_PATH)]:
        seed_props = get_page(session, build_url(ep_path, {"year": year}))
        seed_lookup = build_filter_lookup(seed_props.get("filters", []))
        ep_workouts = {l: v for l, v in seed_lookup.get("event_workout", {}).items() if v}
        print(f"  {ep_label} workouts: {list(ep_workouts.keys())}")
        time.sleep(DELAY)

        for w_label, w_id in ep_workouts.items():
            w_props = get_page(session, build_url(ep_path, {"year": year, "event_workout": w_id}))
            w_lookup = build_filter_lookup(w_props.get("filters", []))
            all_blocks = {l: v for l, v in w_lookup.get("event_workout_block", {}).items() if v}
            # Only keep blocks whose names appear in this workout's actual score columns
            w_cols = set(workout_columns.get(w_label, []))
            valid_blocks = {l: v for l, v in all_blocks.items() if l in w_cols}
            if valid_blocks:
                workout_blocks.setdefault(w_label, {}).update(valid_blocks)
                print(f"  {ep_label} blocks for {w_label}: {list(valid_blocks.keys())}")
            time.sleep(DELAY)

    for w_label in workouts:
        if w_label in workout_blocks:
            print(f"  Final blocks for {w_label}: {list(workout_blocks[w_label].keys())}")
        else:
            print(f"  Final blocks for {w_label}: none")

    return {
        "workouts": workouts,
        "workout_columns": workout_columns,
        "workout_blocks": workout_blocks,
    }


def scrape_individuals_raw(
    session: requests.Session, year: str, test_mode: bool = False
) -> tuple[dict, list]:
    path = INDIVIDUAL_PATH
    print(f"\n{'='*60}\n  Scraping INDIVIDUALS (raw) — {year}\n{'='*60}")

    props = get_page(session, build_url(path, {"year": year}))
    lookup = build_filter_lookup(props.get("filters", []))

    genders    = {l: v for l, v in lookup.get("gender", {}).items() if v}
    categories = {l: v for l, v in lookup.get("event_category", {}).items() if v}
    age_groups = {l: v for l, v in lookup.get("age_group", {}).items() if v}
    workouts   = {l: v for l, v in lookup.get("event_workout", {}).items() if v}
    events     = {l: v for l, v in lookup.get("event", {}).items() if v and l != "All"}

    filter_options = {
        "genders": genders, "categories": categories,
        "age_groups": age_groups, "workouts": workouts, "events": events,
    }

    batches = []
    total = len(genders) * len(categories) * len(age_groups)
    n = 0

    for gender_label, gender_id in genders.items():
        for cat_label, cat_id in categories.items():
            for age_label, age_val in age_groups.items():
                n += 1
                print(f"\n  [{n}/{total}] {gender_label} / {cat_label} / {age_label}")

                base_params = {
                    "year": year, "country": "", "event": "",
                    "gender": gender_id, "age_group": age_val,
                    "event_category": cat_id, "event_workout": "",
                }
                base_ctx = {
                    "gender": gender_label, "gender_id": gender_id,
                    "category": cat_label, "category_id": cat_id,
                    "age_group": age_label, "age_group_id": age_val,
                    "workout": None, "workout_id": "",
                }

                rows = paginate(session, build_url(path, base_params), test_mode)
                print(f"    Overall: {len(rows)} rows")
                batches.append({"filters": base_ctx, "count": len(rows), "rows": rows})
                time.sleep(DELAY)

                for w_label, w_id in workouts.items():
                    rows = paginate(
                        session,
                        build_url(path, {**base_params, "event_workout": w_id}),
                        test_mode,
                    )
                    print(f"    {w_label}: {len(rows)} rows")
                    batches.append({
                        "filters": {**base_ctx, "workout": w_label, "workout_id": w_id},
                        "count": len(rows),
                        "rows": rows,
                    })
                    time.sleep(DELAY)

                if test_mode:
                    break
            if test_mode:
                break
        if test_mode:
            break

    print(f"\n  Total batches: {len(batches)}")
    return filter_options, batches


def scrape_team_individuals_raw(
    session: requests.Session, year: str, test_mode: bool = False
) -> tuple[dict, list]:
    """
    Scrape the team-individual leaderboard.

    The endpoint has an event_workout filter (Strength / Endurance / MetCon X)
    just like the individual endpoint. The overall/unfiltered view defaults to
    one workout type, so we must iterate through each workout to capture all
    athletes. The event_workout_block sub-filter (individual lift names) is NOT
    iterated — each row already contains all the component scores for that athlete.
    """
    path = TEAM_INDIVIDUAL_PATH
    print(f"\n{'='*60}\n  Scraping TEAM-INDIVIDUALS (raw) — {year}\n{'='*60}")

    props = get_page(session, build_url(path, {"year": year}))
    lookup = build_filter_lookup(props.get("filters", []))

    genders    = {l: v for l, v in lookup.get("gender", {}).items() if v}
    categories = {l: v for l, v in lookup.get("event_category", {}).items() if v}
    age_groups = {l: v for l, v in lookup.get("age_group", {}).items() if v}
    workouts   = {l: v for l, v in lookup.get("event_workout", {}).items() if v}

    # Fetch the workout_block filter IDs for each workout type with a lightweight
    # seed request per workout. The available blocks change dynamically depending
    # on which event_workout is active, so a single seed only returns one set.
    workout_blocks: dict[str, dict[str, str]] = {}
    for w_label, w_id in workouts.items():
        w_props = get_page(session, build_url(path, {"year": year, "event_workout": w_id}))
        w_lookup = build_filter_lookup(w_props.get("filters", []))
        blocks = {l: v for l, v in w_lookup.get("event_workout_block", {}).items() if v}
        if blocks:
            workout_blocks[w_label] = blocks
            print(f"  Blocks for {w_label}: {list(blocks.keys())}")
        time.sleep(DELAY)

    filter_options = {
        "genders": genders, "categories": categories,
        "age_groups": age_groups, "workouts": workouts,
        "workout_blocks": workout_blocks,
    }

    print(f"  Genders:    {list(genders.keys())}")
    print(f"  Categories: {list(categories.keys())}")
    print(f"  Age groups: {list(age_groups.keys())}")
    print(f"  Workouts:   {list(workouts.keys())}")

    batches = []
    total = len(genders) * len(categories) * len(age_groups)
    n = 0

    for gender_label, gender_id in genders.items():
        for cat_label, cat_id in categories.items():
            for age_label, age_val in age_groups.items():
                n += 1
                print(f"\n  [{n}/{total}] {gender_label} / {cat_label} / {age_label}")

                base_params = {
                    "year": year, "country": "", "event": "",
                    "gender": gender_id, "age_group": age_val,
                    "event_category": cat_id, "event_workout": "",
                }
                base_ctx = {
                    "gender": gender_label, "gender_id": gender_id,
                    "category": cat_label, "category_id": cat_id,
                    "age_group": age_label, "age_group_id": age_val,
                    "workout": None, "workout_id": "",
                }

                # Per-workout passes — each returns the athletes who participated
                # in that workout with their component scores in the row columns
                for w_label, w_id in workouts.items():
                    rows = paginate(
                        session,
                        build_url(path, {**base_params, "event_workout": w_id}),
                        test_mode,
                    )
                    print(f"    {w_label}: {len(rows)} rows")
                    batches.append({
                        "filters": {**base_ctx, "workout": w_label, "workout_id": w_id},
                        "count": len(rows),
                        "rows": rows,
                    })
                    time.sleep(DELAY)

                if test_mode:
                    break
            if test_mode:
                break
        if test_mode:
            break

    print(f"\n  Total batches: {len(batches)}")
    return filter_options, batches


def scrape_teams_raw(
    session: requests.Session, year: str, test_mode: bool = False
) -> tuple[dict, list]:
    path = TEAM_PATH
    print(f"\n{'='*60}\n  Scraping TEAMS (raw) — {year}\n{'='*60}")

    props = get_page(session, build_url(path, {"year": year}))
    lookup = build_filter_lookup(props.get("filters", []))

    genders    = {l: v for l, v in lookup.get("gender", {}).items() if v}
    categories = {l: v for l, v in lookup.get("event_category", {}).items() if v}
    age_groups = {l: v for l, v in lookup.get("age_group", {}).items() if v}
    workouts   = {l: v for l, v in lookup.get("event_workout", {}).items() if v}

    filter_options = {
        "genders": genders, "categories": categories,
        "age_groups": age_groups, "workouts": workouts,
    }

    batches = []
    total = len(genders) * len(categories) * len(age_groups)
    n = 0

    for gender_label, gender_id in genders.items():
        for cat_label, cat_id in categories.items():
            for age_label, age_val in age_groups.items():
                n += 1
                print(f"\n  [{n}/{total}] {gender_label} / {cat_label} / {age_label}")

                base_params = {
                    "year": year, "country": "", "event": "",
                    "gender": gender_id, "age_group": age_val,
                    "event_category": cat_id, "event_workout": "",
                }
                base_ctx = {
                    "gender": gender_label, "gender_id": gender_id,
                    "category": cat_label, "category_id": cat_id,
                    "age_group": age_label, "age_group_id": age_val,
                    "workout": None, "workout_id": "",
                }

                rows = paginate(session, build_url(path, base_params), test_mode)
                print(f"    Overall: {len(rows)} rows")
                batches.append({"filters": base_ctx, "count": len(rows), "rows": rows})
                time.sleep(DELAY)

                for w_label, w_id in workouts.items():
                    rows = paginate(
                        session,
                        build_url(path, {**base_params, "event_workout": w_id}),
                        test_mode,
                    )
                    print(f"    {w_label}: {len(rows)} rows")
                    batches.append({
                        "filters": {**base_ctx, "workout": w_label, "workout_id": w_id},
                        "count": len(rows),
                        "rows": rows,
                    })
                    time.sleep(DELAY)

                if test_mode:
                    break
            if test_mode:
                break
        if test_mode:
            break

    print(f"\n  Total batches: {len(batches)}")
    return filter_options, batches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AgonX ATHX raw scraper")
    parser.add_argument(
        "--year", nargs="*", default=None,
        help="Years to scrape (default: all years discovered from the site)",
    )
    parser.add_argument(
        "--type",
        choices=["events", "workouts", "individuals", "team-individuals", "teams", "all"],
        default="all",
    )
    parser.add_argument("--test", action="store_true",
                        help="First page / first combo only")
    args = parser.parse_args()

    if args.test:
        print("*** TEST MODE — first page / first combo only ***")

    session = connect()
    years = args.year or discover_years(session)

    for year in years:
        print(f"\n{'#'*60}\n  YEAR: {year}\n{'#'*60}")
        scraped_at = datetime.now(timezone.utc).isoformat()

        if args.type in ("events", "all"):
            event_data = scrape_events_raw(session, year)
            save_json(
                os.path.join(RAW_DIR, f"athx_{year}_events.json"),
                {
                    "schema_family": "athx", "year": year,
                    "scraped_at": scraped_at,
                    **event_data,
                },
            )

        if args.type in ("workouts", "all"):
            workout_data = scrape_workouts_raw(session, year)
            save_json(
                os.path.join(RAW_DIR, f"athx_{year}_workouts.json"),
                {
                    "schema_family": "athx", "year": year,
                    "scraped_at": scraped_at,
                    **workout_data,
                },
            )

        if args.type in ("individuals", "all"):
            filter_opts, batches = scrape_individuals_raw(session, year, args.test)
            save_json(
                os.path.join(RAW_DIR, f"athx_{year}_individuals.json"),
                {
                    "schema_family": "athx", "year": year,
                    "scraped_at": scraped_at,
                    "filter_options": filter_opts,
                    "batches": batches,
                },
            )

        if args.type in ("team-individuals", "all"):
            filter_opts, batches = scrape_team_individuals_raw(session, year, args.test)
            save_json(
                os.path.join(RAW_DIR, f"athx_{year}_team_individuals.json"),
                {
                    "schema_family": "athx", "year": year,
                    "scraped_at": scraped_at,
                    "filter_options": filter_opts,
                    "batches": batches,
                },
            )

        if args.type in ("teams", "all"):
            filter_opts, batches = scrape_teams_raw(session, year, args.test)
            save_json(
                os.path.join(RAW_DIR, f"athx_{year}_teams.json"),
                {
                    "schema_family": "athx", "year": year,
                    "scraped_at": scraped_at,
                    "filter_options": filter_opts,
                    "batches": batches,
                },
            )

    print("\nDone. Run transform_athx.py to produce processed output files.")


if __name__ == "__main__":
    main()
