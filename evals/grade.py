#!/usr/bin/env python3
"""Grade one eval run: python3 evals/grade.py <run-dir> <scenario-id>. Prints a JSON report."""
import json, pathlib, subprocess, sys, urllib.request, random

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/interior-design-planner/skills/room-planner/scripts/planner.py"
sys.path.insert(0, str(SCRIPT.parent))
import planner  # noqa: E402

def url_ok(u):
    try:
        req = urllib.request.Request(u, method="GET", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 400
    except urllib.error.HTTPError as e:
        return e.code in (401, 403, 405, 429)   # exists but blocks bots
    except Exception:
        return None                              # network unreachable from here: unknown

def main(run_dir, sid):
    run = pathlib.Path(run_dir)
    sc = next(s for s in json.loads((ROOT / "evals/scenarios.json").read_text()) if s["id"] == sid)
    exp, rep, fails = sc["expect"], {"scenario": sid}, []
    rj = run / "room.json"
    if not rj.exists():
        print(json.dumps({"scenario": sid, "pass": False, "fails": ["no room.json"]})); return
    data = json.loads(rj.read_text()); planner.assign_option_ids(data)
    types = planner.load_types()
    errors, warnings = planner.check(data, run, types)
    rep["check_errors"] = errors; rep["warnings"] = len(warnings)
    if errors: fails.append(f"{len(errors)} check errors")
    room = data["room"]
    for k in ("type", "currency", "units"):
        if k in exp and room.get(k) != exp[k]: fails.append(f"room.{k} = {room.get(k)!r}, expected {exp[k]!r}")
    els = planner.resolve_elements(data, types) if not errors else []
    opts = data.get("options") or []
    rep["parts"] = len(els); rep["options"] = len(opts)
    if "min_parts" in exp and len(els) < exp["min_parts"]: fails.append(f"only {len(els)} parts")
    if "max_parts" in exp and len(els) > exp["max_parts"]: fails.append(f"{len(els)} parts; user asked for a narrow scope")
    per_part = {e["id"]: sum(1 for o in opts if o.get("element") == e["id"]) for e in els}
    covered = sum(1 for n in per_part.values() if n >= 2)
    rep["parts_with_2plus"] = f"{covered}/{len(els)}"
    if els and covered / len(els) < 0.6: fails.append("fewer than 60% of parts have 2+ options")
    priced = sum(1 for o in opts if isinstance(o.get("price"), (int, float)))
    rep["priced"] = f"{priced}/{len(opts)}"
    if opts and priced / len(opts) < 0.75: fails.append("under 75% of options priced")
    linked = [o["url"] for o in opts if o.get("url")]
    unlinked = [o for o in opts if not o.get("url") and not o.get("owned")]
    if unlinked: fails.append(f"{len(unlinked)} options without links")
    rep["photos"] = f"{sum(1 for o in opts if o.get('image_file'))}/{len(opts)}"
    if exp.get("unknown_size") and any(room.get(k) for k in ("length_mm", "width_mm")) and not room.get("sizesEstimated"): fails.append("stated a room size the user didn't know without marking it as an estimate")
    if exp.get("tile_qty_set"):
        tiles = [e for e in els if "tile" in e["id"] or e["id"] == "floor"]
        if any(not planner.pos(e.get("qty")) for e in tiles): fails.append("tile quantities not set")
    if exp.get("must_drop_or_pick") == "sofa":
        if any(e["id"] == "sofa" for e in els) and not (data.get("picks") or {}).get("sofa") and per_part.get("sofa", 0) > 0 and not any("grey" in (o.get("name", "") + o.get("note", "")).lower() for o in opts if o.get("element") == "sofa"):
            fails.append("researched new sofas although the user is keeping theirs")
    # cheapest-per-part total vs budget
    cheapest = 0
    for e in els:
        cs = [planner.cost(o, e) for o in opts if o.get("element") == e["id"]]
        cs = [c[0] for c in cs if c]
        if cs: cheapest += min(cs)
    rep["cheapest_total"] = round(cheapest, 2); rep["budget"] = room.get("budget")
    if not errors:
        start = planner.starting_selection(data, types)
        rep["starting_total"], rep["starting_unpriced"] = planner.selection_total(data, types, start)
        rep["parts_chosen_at_start"] = f"{len(start)}/{len(els)}"
        if len(start) < 0.6 * len(els): fails.append("page would open with most parts unchosen")
    if room.get("budget") and cheapest > room["budget"]: fails.append("even the cheapest options exceed the budget")
    sample = random.Random(1).sample(linked, min(8, len(linked)))
    checks = [url_ok(u) for u in sample]
    rep["links_checked"] = {"ok": checks.count(True), "dead": checks.count(False), "unknown": checks.count(None)}
    if checks.count(False) >= 2: fails.append(f"{checks.count(False)} dead links in a sample of {len(sample)}")
    rep["fails"] = fails; rep["pass"] = not fails
    print(json.dumps(rep, indent=1))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
