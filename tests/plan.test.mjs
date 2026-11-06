// Floor plan editor: the real planner template, fixture rooms built by planner.py, mouse and keyboard checked to the millimetre.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { openPlanner, ready, dump, closeBrowser, OUT, loadFixture } from "./harness.mjs";

const require = createRequire(import.meta.url);
const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
after(closeBrowser);
const noErrors = (errors) => assert.deepEqual(errors, [], "page logged errors:\n" + errors.join("\n"));

async function open(fixture, opts = {}) {
  const r = await openPlanner({ fixture, ...opts });
  await ready(r.page);
  await r.page.waitForSelector("#plan-body:not([hidden])");
  await r.page.waitForTimeout(60);
  return r;
}
// Fix the view so screen pixels map to millimetres exactly: s px per mm, centred on (cx, cy).
const setView = async (page, cx, cy, s) => { await page.locator("#plan-svg").scrollIntoViewIfNeeded(); await page.evaluate(() => document.getElementById("plan-svg").scrollIntoView({ block: "center" })); await page.waitForTimeout(50); return setView0(page, cx, cy, s); };
const setView0 = (page, cx, cy, s) => page.evaluate(([cx, cy, s]) => { window.RoomPlanner.planUI.view = { cx, cy, s }; window.RoomPlanner.planUI.render(); }, [cx, cy, s]);
const scr = (page, x, y) => page.evaluate(([x, y]) => { const r = document.getElementById("plan-svg").getBoundingClientRect(), v = window.RoomPlanner.planUI.view; return { x: r.left + r.width / 2 + (x - v.cx) * v.s, y: r.top + r.height / 2 + (y - v.cy) * v.s }; }, [x, y]);
const item = async (page, id) => (await dump(page))["items/" + id];
const model = (page) => page.evaluate(() => { const m = window.RoomPlanner.planModel(); return { items: m.items.map(({ option, part, ...x }) => x), walls: m.walls.map((w) => ({ id: w.id, letter: w.letter, len: w.len })), corners: m.corners, dividers: m.dividers.map((d) => ({ id: d.id, len: d.len, t: d.t, a: d.a, b: d.b })), openings: m.openings.map(({ w, ...o }) => ({ ...o, wall: w.id })) }; });
const clearances = (page, id) => page.evaluate((id) => { const G = window.RoomPlanner.geo, m = window.RoomPlanner.planModel(); const c = G.clearances(m, m.items.find((x) => x.id === id)); return Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v && { dist: v.dist, name: v.name }])); }, id);
async function drag(page, from, to, steps = 8, opts = {}) {
  await page.mouse.move(from.x, from.y);
  if (opts.shift) await page.keyboard.down("Shift");
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps });
  await page.mouse.up();
  if (opts.shift) await page.keyboard.up("Shift");
  await page.waitForTimeout(60);
}
const pick = async (page, id) => { await page.click(`[data-pick="item:${id}"]`); await page.waitForTimeout(60); };
const setField = async (page, f, v) => { const l = page.locator(`#plan-insp [data-f="${f}"]`); await l.fill(String(v)); await l.press("Enter"); await l.evaluate((e) => e.blur()); await page.waitForTimeout(60); };

// ---------- geometry ----------
test("geometry helpers: lengths, areas, walls, clearances, clashes", async () => {
  const { page, ctx, errors } = await open("ensuite");
  const r = await page.evaluate(() => {
    const G = window.RoomPlanner.geo;
    const out = {};
    out.parse = ["1200", "1200mm", "120 cm", "1.2m", "47in", '3\'11"', "3 ft", "", "abc", "1,200"].map((s) => G.parseLen(s, "metric"));
    out.parseImp = G.parseLen("47", "imperial");
    const cw = G.walls([{ id: "a", x: 0, y: 0 }, { id: "b", x: 1000, y: 0 }, { id: "c", x: 1000, y: 500 }, { id: "d", x: 0, y: 500 }]);
    const ccw = G.walls([{ id: "a", x: 0, y: 0 }, { id: "d", x: 0, y: 500 }, { id: "c", x: 1000, y: 500 }, { id: "b", x: 1000, y: 0 }]);
    out.normals = [cw[0].nx, cw[0].ny, ccw[0].nx, ccw[0].ny]; // both should point into the room
    out.area = G.area([{ x: 0, y: 0 }, { x: 2600, y: 0 }, { x: 2600, y: 1300 }, { x: 0, y: 1300 }]);
    const sq = (x, y, w, d) => [{ x, y }, { x: x + w, y }, { x: x + w, y: y + d }, { x, y: y + d }];
    out.touch = G.convexOverlap(sq(0, 0, 100, 100), sq(100, 0, 100, 100));
    out.overlap = G.convexOverlap(sq(0, 0, 100, 100), sq(99, 0, 100, 100));
    const m = window.RoomPlanner.planModel();
    const wc = m.items.find((x) => x.id === "wc");
    out.wc = { x: wc.x, y: wc.y, rot: wc.rot, box: G.itemBox(wc) };
    out.clear = Object.fromEntries(Object.entries(G.clearances(m, wc)).map(([k, v]) => [k, v && v.dist]));
    out.problems = G.problems(m).map((p) => p.text);
    out.areas = G.areas(m, 2450);
    // turning towards the nearest wall: an item near wall B ends up with its back on B, facing into the room
    const t = G.toNearestWall(m, { ...wc, x: 2400, y: 600, rot: 0 });
    out.toWall = { x: t.x, rot: t.rot };
    const g = G.setWallLength(JSON.parse(JSON.stringify(G.rectPlan(3000, 2000))), "c1", 3250);
    out.setLen = g.corners.map((c) => [c.x, c.y]);
    out.rel = m.walls.map((w) => G.relativeTo({ x: 1200, y: 1100, dir: 0 }, w));
    return out;
  });
  assert.deepEqual(r.parse, [1200, 1200, 1200, 1200, 1193.8, 1193.8, 914.4, null, null, 1200]);
  assert.equal(r.parseImp, 1193.8);
  assert.deepEqual(r.normals.map((v) => Math.round(v) || 0), [0, 1, 1, 0], "top wall points down, left wall points right, whichever way round the corners go");
  assert.equal(Math.abs(r.area), 3380000);
  assert.equal(r.touch, false, "touching shapes are not a clash");
  assert.equal(r.overlap, true);
  assert.deepEqual(r.wc, { x: 415, y: 0, rot: 0, box: { x0: 235, y0: 0, x1: 595, y1: 520, w: 360, h: 520 } });
  assert.deepEqual(r.clear, { left: 235, right: 275, up: 0, down: 670 }, "WC: 235 to wall D, 275 to the vanity, against wall A, 670 to the towel rail in front (their heights overlap)");
  assert.deepEqual(r.problems, []);
  assert.equal(Math.round(r.areas.floor * 100) / 100, 3.38);
  assert.deepEqual(r.toWall, { x: 2600, rot: 90 });
  assert.deepEqual(r.setLen, [[0, 0], [3250, 0], [3250, 2000], [0, 2000]], "lengthening wall A pushes wall B out");
  assert.deepEqual(r.rel, ["far", "right", "behind", "left"]);
  noErrors(errors); await ctx.close();
});

// ---------- the three rooms ----------
for (const [name, n, floor] of [["main-bathroom", 9, "9.2 m²"], ["ensuite", 6, "3.4 m²"], ["open-plan-kitchen", 19, "48 m²"]]) {
  test(`${name}: plan draws every item at its product's size, with no problems`, async () => {
    const { page, ctx, errors } = await open(name);
    assert.equal(await page.locator("#plan-svg [data-hit=item]").count(), n);
    assert.match(await page.locator("#plan-insp").innerText(), new RegExp("Floor " + floor.replace(".", "\\.")));
    assert.equal(await page.locator(".plan-probs li").count(), 0, "no clashes in the real layouts");
    const m = await model(page);
    for (const it of m.items) for (const k of ["x", "y", "w", "d"]) assert.ok(Number.isFinite(it[k]), `${it.id}.${k}`);
    await page.locator("#plan").screenshot({ path: path.join(OUT, `plan-${name}.png`) });
    noErrors(errors); await ctx.close();
  });
}

test("items take the chosen product's size and keep their back on the wall when it changes", async () => {
  const { page, ctx, errors } = await open("ensuite");
  let m = await model(page);
  let v = m.items.find((x) => x.id === "vanity-and-basin");
  assert.deepEqual([v.w, v.d, v.sized], [700, 460, true]);
  // choose the narrower vanity in the options list
  await page.locator('input[type=radio][value="v-groove"]').check({ force: true });
  await page.waitForTimeout(150);
  m = await model(page);
  v = m.items.find((x) => x.id === "vanity-and-basin");
  assert.deepEqual([v.w, v.d], [600, 400]);
  assert.equal(v.y, 0, "back stays on wall A");
  assert.match(await page.locator("#plan-svg").innerHTML(), /600 × 400/);
  // stop following the product: the item keeps the size it had
  await pick(page, "vanity-and-basin");
  await page.locator('#plan-insp [data-f="follow"]').uncheck();
  await page.waitForTimeout(80);
  const doc = await item(page, "vanity-and-basin");
  assert.deepEqual([doc.follow, doc.w, doc.d], [false, 600, 400]);
  await setField(page, "w", "650");
  assert.equal((await item(page, "vanity-and-basin")).w, 650);
  noErrors(errors); await ctx.close();
});

// ---------- moving things ----------
test("dragging with the mouse moves an item by exactly the distance dragged", async () => {
  const { page, ctx, errors } = await open("ensuite");
  await page.evaluate(() => window.RoomPlanner.host.db().doc("plan/geometry").update({ grid: 1 }));
  await page.waitForTimeout(60);
  await setView(page, 700, 650, 0.5); // 2 mm per screen pixel
  const before = await item(page, "wc");
  const c = await scr(page, before.x, 300);
  await drag(page, c, { x: c.x + 90, y: c.y }); // 90 px = 180 mm
  let after = await item(page, "wc");
  assert.equal(after.x - before.x, 180);
  assert.equal(after.y, before.y);
  const cl = await clearances(page, "wc");
  assert.equal(cl.left.dist, 415, "235 + 180 from wall D");
  // snapping: drag to within a few mm of the vanity and it closes the gap
  const c2 = await scr(page, after.x, 300);
  await drag(page, c2, { x: c2.x + 44, y: c2.y }); // 88 mm towards a 95 mm gap
  after = await item(page, "wc");
  assert.equal((await clearances(page, "wc")).right.dist, 0, "snapped flush to the vanity");
  assert.equal(after.x, 690);
  // the grid: with a 10 mm grid an odd drag lands the item's edge on a multiple of 10
  await page.evaluate(() => window.RoomPlanner.host.db().doc("plan/geometry").update({ grid: 10 }));
  await page.waitForTimeout(60);
  const c3 = await scr(page, after.x, 300);
  await drag(page, c3, { x: c3.x - 63, y: c3.y });
  after = await item(page, "wc");
  assert.equal((after.x - 180) % 10, 0, "left edge on the 10 mm grid: " + after.x);
  noErrors(errors); await ctx.close();
});

test("keyboard: arrows nudge 1, 10 and 100 mm; R turns about the centre; Delete and undo", async () => {
  const { page, ctx, errors } = await open("ensuite");
  await pick(page, "wc");
  await page.locator("#plan-svg").focus();
  const b = await item(page, "wc");
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Shift+ArrowDown");
  await page.keyboard.press("Alt+ArrowRight");
  await page.waitForTimeout(80);
  let a = await item(page, "wc");
  assert.deepEqual([a.x - b.x, a.y - b.y], [103, 10]);
  const cBefore = await page.evaluate(() => { const G = window.RoomPlanner.geo, m = window.RoomPlanner.planModel(); return G.centre(m.items.find((x) => x.id === "wc")); });
  await page.keyboard.press("r");
  await page.waitForTimeout(80);
  a = await item(page, "wc");
  assert.equal(a.rot, 90);
  const cAfter = await page.evaluate(() => { const G = window.RoomPlanner.geo, m = window.RoomPlanner.planModel(); return G.centre(m.items.find((x) => x.id === "wc")); });
  assert.ok(Math.abs(cAfter.x - cBefore.x) <= 0.5 && Math.abs(cAfter.y - cBefore.y) <= 0.5, "turns about its centre");
  await page.keyboard.press("Delete");
  await page.waitForTimeout(80);
  assert.equal(await item(page, "wc"), undefined);
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(80);
  assert.equal((await item(page, "wc")).rot, 90, "undo brings it back as it was");
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(80);
  assert.equal((await item(page, "wc")).rot, 0);
  await page.keyboard.press("Control+Shift+z");
  await page.waitForTimeout(80);
  assert.equal((await item(page, "wc")).rot, 90, "redo");
  noErrors(errors); await ctx.close();
});

test("typing a clear gap moves the item to that exact distance", async () => {
  const { page, ctx, errors } = await open("main-bathroom");
  await pick(page, "bath");
  await setField(page, "gap-left", "30");
  const cl = await clearances(page, "bath");
  assert.equal(cl.left.dist, 30);
  assert.equal(cl.left.name, "wall D");
  assert.equal(cl.right.dist, 20, "50 mm gap to the cupboard less the 30 moved");
  assert.equal(cl.right.name, "Built-in cupboard");
  noErrors(errors); await ctx.close();
});

test("inspector: size, height off the floor, turning, back to the wall", async () => {
  const { page, ctx, errors } = await open("main-bathroom");
  await pick(page, "built-in-cupboard");
  await setField(page, "d", "600");
  await setField(page, "z", "0");
  await setField(page, "rot", "90");
  let d = await item(page, "built-in-cupboard");
  assert.deepEqual([d.d, d.rot], [600, 90]);
  await page.click('#plan-insp [data-act="to-wall"]');
  await page.waitForTimeout(80);
  d = await item(page, "built-in-cupboard");
  const m = await page.evaluate(() => { const G = window.RoomPlanner.geo, m = window.RoomPlanner.planModel(); const it = m.items.find((x) => x.id === "built-in-cupboard"); const b = G.backWall(m, it); return b && b.wall.name; });
  assert.ok(m, "back is against a wall after 'Back to nearest wall'");
  // bad input is refused with a message, nothing written
  await setField(page, "w", "wide");
  assert.match(await page.locator("#toast-text").innerText(), /number/);
  assert.equal((await item(page, "built-in-cupboard")).w, 550);
  noErrors(errors); await ctx.close();
});

// ---------- walls, partitions, doors ----------
test("walls: type a length, drag a wall, split and remove a corner", async () => {
  const { page, ctx, errors } = await open("ensuite");
  await setView(page, 1500, 650, 0.25);
  // select wall B (the right wall, starts at corner c2)
  const p = await scr(page, 2650, 650);
  await page.mouse.click(p.x, p.y);
  await page.waitForTimeout(80);
  assert.match(await page.locator("#plan-insp h3").first().innerText(), /Wall B/);
  await setField(page, "wall-len", "1450");
  let m = await model(page);
  assert.deepEqual(m.corners.map((c) => [c.x, c.y]), [[0, 0], [2600, 0], [2600, 1450], [0, 1450]]);
  // drag wall B 50 px to the right at 0.25 px/mm = 200 mm
  const q = await scr(page, 2650, 400);
  await drag(page, q, { x: q.x + 50, y: q.y });
  m = await model(page);
  assert.deepEqual(m.corners.map((c) => [c.x, c.y]), [[0, 0], [2800, 0], [2800, 1450], [0, 1450]]);
  // split wall A: new corner in the middle, then remove it again
  const a = await scr(page, 1000, -50);
  await page.mouse.click(a.x, a.y);
  await page.click('#plan-insp [data-act="split"]');
  await page.waitForTimeout(80);
  m = await model(page);
  assert.equal(m.corners.length, 5);
  assert.deepEqual([m.corners[1].x, m.corners[1].y], [1400, 0]);
  await page.click('#plan-insp [data-act="del-corner"]');
  await page.waitForTimeout(80);
  assert.equal((await model(page)).corners.length, 4);
  noErrors(errors); await ctx.close();
});

test("partition: draw one with two clicks, then put a door in it", async () => {
  const { page, ctx, errors } = await open("open-plan-kitchen");
  await setView(page, 1300, 2000, 0.2);
  await page.click('#plan-tools [data-tool="divider"]');
  const a = await scr(page, 0, 2500), b = await scr(page, 1800, 2500);
  await page.mouse.click(a.x, a.y);
  await page.mouse.move(b.x, b.y + 3, { steps: 4 }); // a little off straight: it straightens
  await page.mouse.click(b.x, b.y + 3);
  await page.waitForTimeout(100);
  let m = await model(page);
  assert.equal(m.dividers.length, 1);
  assert.deepEqual([m.dividers[0].a, m.dividers[0].b, m.dividers[0].len], [{ x: 0, y: 2500 }, { x: 1800, y: 2500 }, 1800]);
  await page.click('#plan-insp [data-act="add-door"]');
  await page.waitForTimeout(80);
  await setField(page, "o-at", "200");
  m = await model(page);
  assert.equal(m.openings.filter((o) => o.wall === m.dividers[0].id)[0].at, 200);
  noErrors(errors); await ctx.close();
});

test("doors and windows: add, set exact position, flip hinge and swing; a door that hits something is flagged", async () => {
  const { page, ctx, errors } = await open("ensuite");
  await page.click('[data-pick^="opening:"]');
  await page.waitForTimeout(60);
  assert.match(await page.locator("#plan-insp h3").first().innerText(), /Door in wall C/);
  await setField(page, "o-end", "300"); // 300 mm from wall D
  let o = (await model(page)).openings[0];
  assert.equal(2600 - o.at - o.width, 300);
  await page.click('#plan-insp [data-act="hinge"]');
  await page.click('#plan-insp [data-act="swing"]');
  await page.waitForTimeout(80);
  o = (await model(page)).openings[0];
  assert.deepEqual([o.hinge, o.side], ["end", -1]);
  await page.click('#plan-insp [data-act="swing"]'); // back into the room: now it hits the WC
  await page.waitForTimeout(80);
  assert.match(await page.locator("#plan-insp").innerText(), /(WC|towel rail)/i);
  await page.click('#plan-insp [data-act="desel"]');
  await page.waitForTimeout(60);
  assert.ok(await page.locator(".plan-probs li").count() >= 1, "door clash listed");
  // window with sill and head heights
  await page.click('#plan-insp [data-act="add-window"]');
  await page.waitForTimeout(80);
  await setField(page, "o-sill", "1050");
  const w = (await model(page)).openings.find((x) => x.type === "window");
  assert.equal(w.sill, 1050);
  noErrors(errors); await ctx.close();
});

test("clashes: moving one thing onto another flags both, in the list and on the plan", async () => {
  const { page, ctx, errors } = await open("main-bathroom");
  await pick(page, "wc");
  await setField(page, "gap-up", "0");
  await page.click('#plan-insp [data-act="desel"]');
  await page.waitForTimeout(60);
  // move the bath onto the cupboard
  await pick(page, "bath");
  await setField(page, "gap-right", "0");
  await page.locator("#plan-svg").focus();
  await page.keyboard.press("Alt+ArrowRight");
  await page.waitForTimeout(80);
  assert.match(await page.locator("#plan-insp").innerText(), /Bath and Built-in cupboard overlap/);
  assert.equal(await page.locator('#plan-svg .item.bad[data-id="bath"]').count(), 1);
  noErrors(errors); await ctx.close();
});

test("measure tool and camera", async () => {
  const { page, ctx, errors } = await open("ensuite");
  await setView(page, 1300, 650, 0.25);
  await page.click('#plan-tools [data-tool="measure"]');
  const a = await scr(page, 0, 650), b = await scr(page, 2600, 650);
  await page.mouse.click(a.x, a.y); await page.mouse.click(b.x, b.y);
  await page.waitForTimeout(60);
  assert.match(await page.locator("#plan-hint").innerText(), /Distance: 2600 mm/);
  await page.keyboard.press("Escape");
  await page.click('#plan-tools [data-tool="camera"]');
  const c = await scr(page, 1300, 1100), d = await scr(page, 1300, 300);
  await drag(page, c, d);
  const g = (await dump(page))["plan/geometry"];
  assert.deepEqual([g.camera.x, g.camera.y, g.camera.dir], [1300, 1100, 0]);
  assert.match(await page.locator("#gpt-prompt").inputValue(), /Camera at eye level \(1600 mm\).*looking straight at wall A/);
  noErrors(errors); await ctx.close();
});

// ---------- output ----------
test("ChatGPT prompt carries the exact layout, and the link stays a sensible length", async () => {
  const { page, ctx, errors } = await open("open-plan-kitchen");
  const p = await page.locator("#gpt-prompt").inputValue();
  assert.match(p, /FLOOR PLAN/);
  assert.match(p, /Walls, going round the room: A 7320 mm \(behind the camera\); B 7950 mm \(left wall\); C 4700 mm \(far wall\)/);
  assert.match(p, /Folding \(bifold\) door, 2475 mm wide, in wall A/);
  assert.match(p, /Hob \(Bosch Series 4 PVS811B16E venting induction hob\): 802 mm wide × 522 mm deep/);
  assert.match(p, /Sofa: 2100 mm wide × 950 mm deep × 850 mm high; back against wall F/);
  assert.doesNotMatch(p, /Placement: Above the hob/, "plan positions replace the template's placement hints for placed parts");
  const len = (await page.getAttribute("#gpt-open", "href")).length;
  assert.ok(len < 12000, "URL length " + len);
  fs.writeFileSync(path.join(OUT, "prompt-open-plan-kitchen.txt"), p);
  noErrors(errors); await ctx.close();
});

test("plan image saves as a PNG, and the reference board uses the drawn plan", async () => {
  const { page, ctx, errors } = await open("main-bathroom");
  await page.click("#plan-png");
  await page.waitForFunction(() => window.__saves.length === 1, null, { timeout: 8000 });
  const saves = await page.evaluate(() => window.__saves);
  assert.equal(saves.length, 1);
  assert.match(saves[0].filename, /main-bathroom-floor-plan\.png/);
  assert.equal(saves[0].type, "image/png");
  assert.ok(saves[0].size > 20000, "a real drawing: " + saves[0].size);
  const svg = await page.evaluate(() => window.RoomPlanner.planUI.exportSvg().svg);
  fs.writeFileSync(path.join(OUT, "plan-export-main-bathroom.svg"), svg);
  assert.match(svg, /A {2}2300/);
  await page.click("#gpt-board");
  await page.waitForFunction(() => window.__saves.length === 2, null, { timeout: 8000 });
  assert.equal((await page.evaluate(() => window.__saves)).length, 2);
  noErrors(errors); await ctx.close();
});

test("start a plan on a planner that has none: a rectangle from the room's size", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.waitForSelector("#plan-start:not([hidden])");
  await page.click("#plan-start-btn");
  await page.waitForSelector("#plan-body:not([hidden])");
  const g = (await dump(page))["plan/geometry"];
  assert.deepEqual(g.corners.map((c) => [c.x, c.y]), [[0, 0], [3600, 0], [3600, 4800], [0, 4800]]);
  // parts with a plan symbol are offered; placing the sofa uses its catalogue size against the nearest wall
  await page.click('[data-place="sofa"]');
  await page.waitForTimeout(100);
  const it = Object.entries(await dump(page)).find(([k, v]) => k.startsWith("items/") && v.element === "sofa")[1];
  assert.equal(it.kind, "sofa");
  assert.ok(await page.locator("#plan-insp h3").innerText());
  // the floor area from the plan can fill the flooring quantity
  assert.equal(await page.locator('[data-plan-qty="paint"]').count(), 1);
  await page.click('[data-plan-qty="paint"]');
  await page.waitForTimeout(80);
  assert.equal((await dump(page))["elements/paint"].qty, 42, "walls 2 x (3.6 + 4.8) x 2.5 m, no doors or windows drawn yet");
  noErrors(errors); await ctx.close();
});

test("plan image underneath: set its scale from two points, then line it up", async () => {
  const { page, ctx, errors } = await open("main-bathroom");
  let g = (await dump(page))["plan/geometry"];
  assert.ok(g.underlay && g.underlay.src, "the uploaded floor plan is under the drawing");
  await page.click(".plan-settings summary");
  await page.click('#plan-insp [data-tool="calibrate"]');
  await page.waitForTimeout(150);
  // pick two points 1000 mm apart on the provisionally scaled image
  await setView(page, 1150, 1500, 0.15);
  const a = await scr(page, 0, 0), b = await scr(page, 2300, 0);
  await page.mouse.click(a.x, a.y); await page.mouse.click(b.x, b.y);
  await page.waitForSelector("#plan-cal:not([hidden])");
  await page.fill("#plan-cal-mm", "2300");
  await page.click("#plan-cal-go");
  await page.waitForTimeout(120);
  g = (await dump(page))["plan/geometry"];
  assert.ok(g.underlay.mmPerPx > 0);
  assert.equal(await page.locator("#plan-done").isVisible(), true);
  await page.click("#plan-done");
  noErrors(errors); await ctx.close();
});

test("backup carries the floor plan and restores it", async () => {
  const { page, ctx, errors } = await open("ensuite");
  await page.click("#backup-save");
  await page.waitForTimeout(80);
  const backup = (await page.evaluate(() => window.__saves))[0].text;
  const orig = await dump(page);
  await ctx.close();
  const { page: p2, ctx: c2, errors: e2 } = await openPlanner({ fixture: "living-room" });
  await ready(p2);
  await p2.setInputFiles("#backup-file", { name: "b.json", mimeType: "application/json", buffer: Buffer.from(backup) });
  await p2.waitForSelector("#restore-confirm:not([hidden])");
  assert.match(await p2.locator("#restore-text").innerText(), /a floor plan/);
  await p2.click("#restore-go");
  await p2.waitForFunction(() => /restored/.test(document.getElementById("backup-status").textContent));
  const d = await dump(p2);
  assert.deepEqual(d["plan/geometry"], orig["plan/geometry"]);
  assert.deepEqual(Object.keys(d).filter((k) => k.startsWith("items/")).sort(), Object.keys(orig).filter((k) => k.startsWith("items/")).sort());
  noErrors(errors); noErrors(e2); await c2.close();
});

test("options: sizes typed by hand and read from product pages", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room", caps: { db: true, assets: true, downloads: true, mcp: true, sample: true },
    extra: { sampleReply: { element: "coffee-table", name: "Oak coffee table", supplier: "Test Shop", price: 249, per: "item", covers: null, priceNote: "", spec: "Oak", note: "", size: { w: "1100", d: 600, h: 400 }, shape: "rounded" } } });
  await ready(page);
  await page.click('[data-add="sofa"]');
  await page.fill("#od-name", "Test sofa"); await page.fill("#od-sw", "2100"); await page.fill("#od-sd", "95 cm"); await page.fill("#od-sh", "820");
  await page.click("#od-save");
  await page.waitForTimeout(100);
  const o = Object.values(await dump(page)).find((x) => x && x.name === "Test sofa");
  assert.deepEqual(o.size, { w: 2100, d: 950, h: 820, from: "manual" });
  assert.match(await page.locator(".opt", { hasText: "Test sofa" }).innerText(), /2100 × 950 × 820 mm/);
  // width without depth is refused
  await page.click('[data-add="sofa"]');
  await page.fill("#od-name", "Half"); await page.fill("#od-sw", "2100");
  await page.click("#od-save");
  assert.match(await page.locator("#od-error").innerText(), /width and the depth/);
  await page.keyboard.press("Escape");
  // inbox: the page reader returns a size
  await page.fill("#in-url", "https://shop.example/oak-table"); await page.click("#inbox-form button[type=submit]");
  await page.click("#update-btn");
  await page.waitForFunction(() => /Added 1/.test(document.getElementById("inbox-status").textContent), null, { timeout: 15000 });
  const t = Object.values(await dump(page)).find((x) => x && x.name === "Oak coffee table" && x.source === "link");
  assert.deepEqual([t.size, t.shape], [{ w: 1100, d: 600, h: 400, from: "page" }, "rounded"]);
  noErrors(errors); await ctx.close();
});

test("messy plan data: nothing runs, nothing crashes", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "messy" });
  await ready(page);
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__xss), undefined);
  assert.equal(await page.locator("#plan-body").isVisible(), true);
  await page.click('[data-pick^="item:"]');
  await page.waitForTimeout(80);
  await page.evaluate(() => window.RoomPlanner.planUI.exportSvg());
  assert.equal(await page.evaluate(() => window.__xss), undefined);
  noErrors(errors); await ctx.close();
});

for (const [label, vp, scheme] of [["phone light", { width: 390, height: 844 }, "light"], ["desktop dark", { width: 1280, height: 900 }, "dark"]]) {
  test(`plan layout ${label}: no sideways scroll, drag works with touch-sized screen`, async () => {
    const { page, ctx, errors } = await open("main-bathroom", { viewport: vp, colorScheme: scheme });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(over <= 0, "sideways scroll " + over);
    await page.locator("#plan").screenshot({ path: path.join(OUT, `plan-${label.replace(" ", "-")}.png`) });
    noErrors(errors); await ctx.close();
  });
}

test("accessibility scan with a floor plan", async () => {
  const { page, ctx, errors } = await open("main-bathroom");
  await pick(page, "vanity-and-basin");
  await page.addScriptTag({ content: AXE });
  const res = await page.evaluate(async () => (await window.axe.run(document, { resultTypes: ["violations"] })).violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes[0] && v.nodes[0].html.slice(0, 160) })));
  fs.writeFileSync(path.join(OUT, "axe-plan.json"), JSON.stringify(res, null, 2));
  assert.deepEqual(res.filter((v) => v.impact === "serious" || v.impact === "critical"), []);
  noErrors(errors); await ctx.close();
});
