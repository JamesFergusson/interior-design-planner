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
