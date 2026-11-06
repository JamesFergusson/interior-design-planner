"""Tests for scripts/planner.py: the checks Claude relies on during setup, and the seed output."""
import json, pathlib, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/interior-design-planner/skills/room-planner/scripts/planner.py"
sys.path.insert(0, str(SCRIPT.parent))
import planner  # noqa: E402

TYPES = planner.load_types()


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def base(**room):
    r = {"name": "Test room", "type": "living-room", "units": "metric", "currency": "GBP", "length_mm": 4000, "width_mm": 3000, "height_mm": 2400}
    r.update(room)
    return {"room": r, "options": []}


class Quantities(unittest.TestCase):
    def test_areas(self):
        a = planner.areas({"length_mm": 4000, "width_mm": 3000, "height_mm": 2400})
        self.assertAlmostEqual(a["floor"], 12)
        self.assertAlmostEqual(a["perimeter"], 14)
        self.assertAlmostEqual(a["walls"], 14 * 2.4 * 0.85)

    def test_template_quantities(self):
        els = {e["id"]: e for e in planner.resolve_elements(base(), TYPES)}
        self.assertEqual(els["flooring"]["qty"], 13.2)
        self.assertEqual(els["paint"]["qty"], 28.6)
        self.assertEqual(els["sofa"]["qty"], 1)

    def test_unknown_size_gives_null_quantity(self):
        els = {e["id"]: e for e in planner.resolve_elements(base(length_mm=None), TYPES)}
        self.assertIsNone(els["flooring"]["qty"])

    def test_imperial_units(self):
        els = {e["id"]: e for e in planner.resolve_elements(base(units="imperial"), TYPES)}
        self.assertEqual(els["flooring"]["unit"], "ft²")
        self.assertAlmostEqual(els["flooring"]["qty"], 142.1, places=1)

    def test_drop_override_extra(self):
        d = base(); d["drop"] = ["plants"]; d["override"] = {"rug": {"qty": 2}}; d["extra"] = [{"id": "bench", "group": "Seating", "name": "Bench"}]
        els = {e["id"]: e for e in planner.resolve_elements(d, TYPES)}
        self.assertNotIn("plants", els); self.assertEqual(els["rug"]["qty"], 2); self.assertEqual(els["bench"]["qty"], 1)


class Costs(unittest.TestCase):
    def test_rules(self):
        m2 = {"unit": "m²", "qty": 19}
        self.assertEqual(planner.cost({"price": 54.99, "per": "m²"}, m2)[0], 1044.81)
        self.assertEqual(planner.cost({"price": 32.5, "per": "box", "covers": 1.8}, m2), (357.5, 11))
        self.assertEqual(planner.cost({"price": 420}, {"unit": "item", "qty": 1})[0], 420)
        self.assertEqual(planner.cost({"price": 249}, {"unit": "item", "qty": 2})[0], 498)
        self.assertEqual(planner.cost({"price": 59, "per": "tin", "covers": 16}, {"unit": "m²", "qty": 35.7}), (177, 3))
        self.assertIsNone(planner.cost({"price": None}, m2))
        self.assertIsNone(planner.cost({"price": 30, "per": "m²"}, {"unit": "m²", "qty": None}))
        # exact multiple of a pack must not round up an extra pack
        self.assertEqual(planner.cost({"price": 10, "per": "box", "covers": 0.1}, {"unit": "m²", "qty": 0.3})[1], 3)


class Check(unittest.TestCase):
    def errors(self, data):
        return planner.check(data, ROOT, TYPES)[0]

    def test_good_room_passes(self):
        d = base(); d["options"] = [{"id": "s1", "element": "sofa", "name": "Sofa", "url": "https://x.example/s", "price": 899}]
        d["picks"] = {"sofa": "s1"}
        self.assertEqual(self.errors(d), [])

    def test_catches_common_mistakes(self):
        cases = [
            (base(type="garage"), "room.type"),
            (base(length_mm=4.2), "looks wrong"),
            (base(currency="AUD"), "currency"),
            ({"room": {"name": "x", "type": "living-room"}, "options": [{"element": "nope", "name": "x"}]}, "not a part"),
            ({**base(), "options": [{"element": "sofa", "name": "x", "price": "£899"}]}, "price must be a number"),
            ({**base(), "options": [{"element": "flooring", "name": "x", "price": 30, "per": "box"}]}, "covers"),
            ({**base(), "options": [{"element": "sofa", "name": "x", "price": 3, "per": "m²"}]}, "measured in item"),
            ({**base(), "options": [{"element": "sofa", "name": "x", "url": "www.example.com"}]}, "url"),
            ({**base(), "options": [{"element": "sofa", "name": "x", "status": "maybe"}]}, "status"),
            ({**base(), "options": [{"element": "sofa", "name": "x", "image_file": "missing.jpg"}]}, "not found"),
            ({**base(), "options": [{"id": "a", "element": "sofa", "name": "x"}], "picks": {"rug": "a"}}, "belongs to"),
            ({**base(), "options": [{"id": "a", "element": "sofa", "name": "x"}, {"id": "a", "element": "rug", "name": "y"}]}, "duplicate option"),
            ({**base(swatches=[{"hex": "green"}])}, "hex"),
        ]
        for data, expect in cases:
            msgs = " | ".join(self.errors(data) or planner.check(data, ROOT, TYPES)[1])
            self.assertIn(expect, msgs, f"expected {expect!r} in: {msgs}")

    def test_fake_image_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "x.jpg"; p.write_text("<html>Access denied</html>")
            d = base(); d["options"] = [{"element": "sofa", "name": "x", "image_file": str(p)}]
            self.assertTrue(any("not a real image" in e for e in planner.check(d, pathlib.Path(t), TYPES)[0]))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "room.json"
            p.write_text(json.dumps(base(type="garage")))
            self.assertEqual(run("check", str(p)).returncode, 1)
            p.write_text(json.dumps(base()))
            r = run("check", str(p)); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("OK:", r.stdout)
            p.write_text("{not json")
            self.assertEqual(run("check", str(p)).returncode, 2)


class Seed(unittest.TestCase):
    def test_new_then_seed(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            r = run("new", "bedroom"); self.assertEqual(r.returncode, 0)
            data = json.loads(r.stdout)
            data["room"].update({"name": "Spare room", "length_mm": 3200, "width_mm": 3000, "height_mm": 2400})
            data["options"] = [{"id": f"o{i}", "element": "bed", "name": f"Bed {i}", "url": "https://x.example/b", "price": 300 + i} for i in range(70)]
            data["picks"] = {"bed": "o3"}
            (t / "room.json").write_text(json.dumps(data))
            (t / "up.json").write_text(json.dumps({"o1": "/_blob/abc"}))
            r = run("seed", str(t / "room.json"), "--out", str(t / "seed"), "--photos", str(t / "up.json"))
            self.assertEqual(r.returncode, 0, r.stderr)
            batches = json.loads((t / "seed/batches.json").read_text())
            self.assertTrue(all(len(b) <= 50 for b in batches))
            flat = [w for b in batches for w in b]
            self.assertEqual(flat[-1]["collection"], "room", "room/brief must be written last")
            docs = {f"{w['collection']}/{w['doc_id']}": json.loads(pathlib.Path(w["file_path"]).read_text()) for w in flat}
            self.assertTrue(docs["room/brief"]["setupDone"])
            self.assertEqual(docs["state/selection"]["map"], {"bed": "o3"})
            self.assertEqual(docs["presets/suggested"]["map"], {"bed": "o3"})
            self.assertEqual(docs["presets/cheapest"]["map"], {"bed": "o0"})
            self.assertEqual(docs["options/o1"]["image"], "/_blob/abc")
            self.assertEqual(docs["options/o2"]["image"], "")
            self.assertEqual(len([k for k in docs if k.startswith("elements/")]), len(TYPES["bedroom"]["elements"]))

    def test_seed_refuses_bad_photo_map(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            (t / "room.json").write_text(json.dumps(base()))
            (t / "up.json").write_text(json.dumps({"x": "https://evil.example/a.png"}))
            self.assertEqual(run("seed", str(t / "room.json"), "--out", str(t / "s"), "--photos", str(t / "up.json")).returncode, 1)

    def test_seed_refuses_invalid_room(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "room.json"; p.write_text(json.dumps(base(type="garage")))
            self.assertEqual(run("seed", str(p)).returncode, 1)


class Selection(unittest.TestCase):
    def test_shortlisted_become_starting_choices(self):
        d = base()
        d["options"] = [
            {"id": "s1", "element": "sofa", "name": "A", "url": "https://x.example/a", "price": 900},
            {"id": "s2", "element": "sofa", "name": "B", "url": "https://x.example/b", "price": 700, "status": "shortlisted"},
            {"id": "s3", "element": "sofa", "name": "C", "url": "https://x.example/c", "price": 500, "status": "rejected"},
            {"id": "r1", "element": "rug", "name": "Rug", "url": "https://x.example/r", "price": 200, "status": "shortlisted"},
            {"id": "c1", "element": "armchair", "name": "Ours", "owned": True, "price": 0},
        ]
        d["picks"] = {"rug": None, "armchair": "c1"}
        sel = planner.starting_selection(d, TYPES)
        self.assertEqual(sel["sofa"], "s2")
        self.assertEqual(sel["armchair"], "c1")
        self.assertEqual(sel["rug"], "r1", "a null pick does not block the shortlisted suggestion")
        self.assertEqual(planner.cheapest_selection(d, TYPES)["sofa"], "s2", "rejected options are never the cheapest suggestion")
        errors, warnings = planner.check(d, ROOT, TYPES)
        self.assertEqual(errors, [])
        self.assertFalse(any("Ours" in w for w in warnings), "owned items need no link or price")
        r = None
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "room.json"; p.write_text(json.dumps(d))
            r = run("check", str(p))
        self.assertIn("Starting choices (picks + shortlisted): £900.00", r.stdout)
        self.assertIn("Cheapest option in every part: £900.00", r.stdout)

    def test_more_pack_kinds(self):
        self.assertEqual(planner.cost({"price": 16.74, "per": "tile", "covers": 0.36}, {"unit": "m²", "qty": 2.6}), (133.92, 8))
        self.assertEqual(planner.cost({"price": 12.9, "per": "set", "covers": 4}, {"unit": "item", "qty": 12}), (38.7, 3))


class Templates(unittest.TestCase):
    def test_every_room_type_is_valid(self):
        for k, v in TYPES.items():
            ids = [e["id"] for e in v["elements"]]
            self.assertEqual(len(ids), len(set(ids)), k)
            for e in v["elements"]:
                self.assertIn(e["unit"], planner.UNITS, (k, e["id"]))
                self.assertTrue(planner.ID_RE.match(e["id"]), (k, e["id"]))
                q = e["qtyFrom"]
                self.assertTrue(q is None or isinstance(q, (int, float)) or q in ("walls", "floor", "ceiling", "perimeter"), (k, e["id"]))

    def test_template_in_page_matches_json(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools/build.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_versions_agree(self):
        plugin = json.loads((ROOT / "plugins/interior-design-planner/.claude-plugin/plugin.json").read_text())["version"]
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())["plugins"][0]["version"]
        skill = (SCRIPT.parent.parent / "SKILL.md").read_text()
        html = (SCRIPT.parent.parent / "assets/planner.html").read_text()
        self.assertEqual(plugin, market)
        self.assertEqual(planner.VERSION, plugin)
        self.assertIn(f'version: "{plugin}"', skill)
        self.assertIn(f'const VERSION = "{plugin}"', html)


if __name__ == "__main__":
    unittest.main()


def bath_room(**plan):
    d = base(name="Bathroom", type="bathroom", length_mm=3000, width_mm=2000)
    d["options"] = [
        {"id": "wc-a", "element": "wc", "name": "WC", "url": "https://x.example/wc", "price": 200, "status": "shortlisted", "size": {"w": 360, "d": 650, "h": 800}},
        {"id": "van-a", "element": "vanity", "name": "Vanity", "url": "https://x.example/v", "price": 500, "status": "shortlisted", "size": {"w": 800, "d": 460, "h": 850}},
        {"id": "van-b", "element": "vanity", "name": "Vanity with no size", "url": "https://x.example/v2", "price": 400},
    ]
    d["plan"] = {"corners": [[0, 0], [2000, 0], [2000, 3000], [0, 3000]],
                 "openings": [{"type": "door", "wall": "C", "at": 200, "width": 700}],
                 "items": [{"part": "wc", "against": "A", "from": 100}, {"part": "vanity", "against": "B", "from": 0}]}
    d["plan"].update(plan)
    return d


class FloorPlan(unittest.TestCase):
    def plan(self, d):
        return planner.build_plan(d, TYPES, planner.starting_selection(d, TYPES))

    def test_items_against_walls_take_product_sizes(self):
        g, items, errors, warnings, lines = self.plan(bath_room())
        self.assertEqual(errors, [])
        its = dict(items)
        # WC on wall A (top): back on the wall, 100 mm from the corner with wall D
        self.assertEqual((its["wc"]["x"], its["wc"]["y"], its["wc"]["rot"]), (280, 0, 0))
        # vanity on wall B (right), facing into the room: turned 90 degrees, back on x = 2000
        self.assertEqual((its["vanity-and-basin"]["x"], its["vanity-and-basin"]["y"], its["vanity-and-basin"]["rot"]), (2000, 400, 90))
        self.assertEqual([c["id"] for c in g["corners"]], ["c1", "c2", "c3", "c4"])
        self.assertEqual(g["openings"][0]["wall"], "c3")
        self.assertTrue(any("WC" in l and "360 x 650" in l for l in lines))

    def test_same_result_whichever_way_round_the_corners_go(self):
        d = bath_room(corners=[[0, 0], [0, 3000], [2000, 3000], [2000, 0]], openings=[], items=[{"part": "wc", "against": "A", "from": 100}])
        g, items, errors, _, _ = self.plan(d)
        self.assertEqual(errors, [])
        wc = dict(items)["wc"]
        # wall A now runs down the left side: the WC's back is on x = 0, facing right
        self.assertEqual((wc["x"], wc["y"], wc["rot"]), (0, 280, 270))

    def test_box_placement_and_partitions(self):
        d = bath_room(partitions=[{"from": [0, 1000], "to": [2000, 1000], "t": 100}],
                      openings=[{"type": "door", "wall": "P1", "at": 600, "width": 700, "side": "-"}],
                      items=[{"name": "Cabinet", "kind": "cabinet", "box": [0, 1050], "rot": 90, "w": 600, "d": 300}, {"part": "wc", "against": "P1", "side": "+", "from": 1200}])
        g, items, errors, warnings, _ = self.plan(d)
        self.assertEqual(errors, [])
        its = dict(items)
        self.assertEqual((its["cabinet"]["x"], its["cabinet"]["y"]), (300, 1350))
        self.assertEqual((its["wc"]["x"], its["wc"]["y"], its["wc"]["rot"]), (1380, 1050, 0))
        self.assertEqual(g["dividers"][0]["id"], "p1")
        self.assertEqual(g["openings"][0]["side"], -1)

    def test_mistakes_are_caught(self):
        cases = [
            (dict(corners=[[0, 0], [2000, 0]]), "at least 3 corners"),
            (dict(corners=[[0, 0], [2, 0], [2, 3], [0, 3]]), "almost no area"),
            (dict(openings=[{"type": "door", "wall": "Q", "at": 0, "width": 700}]), "not a wall letter"),
            (dict(openings=[{"type": "window", "wall": "A", "at": 1500, "width": 700}]), "runs past the end of wall A"),
            (dict(openings=[{"type": "door", "wall": "A", "at": 0, "width": 700, "style": "revolving"}]), "style must be"),
            (dict(items=[{"part": "wc"}]), "give its position"),
            (dict(items=[{"part": "nope", "against": "A", "from": 0}]), "not a part of this room"),
            (dict(items=[{"kind": "spaceship", "against": "A", "from": 0}]), "kind 'spaceship'"),
            (dict(items=[{"part": "wc", "against": "A"}]), "give from"),
            (dict(items=[{"part": "wc", "box": [0, 0], "rot": 45}]), "rot 0, 90, 180 or 270"),
            (dict(camera={"dir": 0}), "plan.camera needs x and y"),
        ]
        for patch, msg in cases:
            with self.subTest(msg=msg):
                errors, _ = planner.check(bath_room(**patch), ROOT, TYPES)
                self.assertTrue(any(msg in e for e in errors), errors)

    def test_clashes_and_doors_are_warned(self):
        d = bath_room(items=[{"part": "wc", "against": "A", "from": 100}, {"name": "Box", "kind": "box", "against": "A", "from": 300, "w": 400, "d": 400},
                             {"name": "In the doorway", "kind": "box", "against": "C", "from": 300, "w": 400, "d": 400},
                             {"name": "Off the edge", "kind": "box", "box": [1800, 100], "rot": 0, "w": 400, "d": 400}])
        errors, warnings = planner.check(d, ROOT, TYPES)
        self.assertEqual(errors, [])
        text = "\n".join(warnings)
        self.assertIn("'WC' and 'Box' overlap", text)
        self.assertIn("hits 'In the doorway'", text)
        self.assertIn("'Off the edge' goes outside the room", text)
        _, warnings = planner.check(bath_room(), ROOT, TYPES)  # the vanity is placed in this one
        self.assertIn("'Vanity with no size' (vanity) is placed in the floor plan but has no size", "\n".join(warnings))

    def test_option_sizes_are_checked(self):
        d = bath_room()
        d["options"][0]["size"] = {"w": 3.6, "d": 6.5}
        errors, _ = planner.check(d, ROOT, TYPES)
        self.assertTrue(any("looks wrong" in e for e in errors), errors)
        d["options"][0]["size"] = {"w": "360", "d": 650}
        errors, _ = planner.check(d, ROOT, TYPES)
        self.assertTrue(any("positive numbers" in e for e in errors), errors)

    def test_seed_writes_plan_and_items_before_the_room(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "room.json"
            p.write_text(json.dumps(bath_room()))
            r = run("seed", str(p), "--out", str(pathlib.Path(t) / "seed"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            writes = [w for b in json.loads((pathlib.Path(t) / "seed" / "batches.json").read_text()) for w in b]
            keys = [f"{w['collection']}/{w['doc_id']}" for w in writes]
            self.assertIn("plan/geometry", keys)
            self.assertIn("items/wc", keys)
            self.assertEqual(keys[-1], "room/brief")
            opt = json.loads(pathlib.Path(next(w["file_path"] for w in writes if w["doc_id"] == "wc-a")).read_text())
            self.assertEqual(opt["size"], {"w": 360, "d": 650, "h": 800, "from": "page"})

    def test_kinds_in_page_match_json(self):
        html = (ROOT / "plugins/interior-design-planner/skills/room-planner/assets/planner.html").read_text()
        kinds = json.loads((ROOT / "plugins/interior-design-planner/skills/room-planner/references/plan-kinds.json").read_text())
        self.assertIn("const PLAN_KINDS = " + json.dumps({k: v for k, v in kinds.items() if not k.startswith("_")}, ensure_ascii=False, separators=(",", ":")) + ";", html)
        parts = set().union(*[{e["id"] for e in t["elements"]} for t in TYPES.values()])
        for part, kind in kinds["parts"].items():
            self.assertIn(kind, kinds["kinds"], part)
