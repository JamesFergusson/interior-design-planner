// Layer 1: the real planner template running against the claude.ai stand-in.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { openPlanner, ready, dump, closeBrowser, OUT, loadFixture } from "./harness.mjs";

const require = createRequire(import.meta.url);
const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
after(closeBrowser);

const noErrors = (errors) => assert.deepEqual(errors, [], "page logged errors:\n" + errors.join("\n"));
const text = (page, sel) => page.locator(sel).innerText();

// ---------- startup ----------
test("without Claude the page says how to open it", async () => {
  const { page, ctx, errors } = await openPlanner({ noClaude: true });
  await page.waitForTimeout(200);
  assert.match(await text(page, "#loading"), /Open this page in Claude/);
  noErrors(errors); await ctx.close();
});

test("empty planner shows setup, and setup builds the room from its type", async () => {
  const { page, ctx, errors } = await openPlanner({});
  await ready(page);
  assert.equal(await page.locator("#setup").isVisible(), true);
  assert.equal(await page.locator("#app").isVisible(), false);
  // validation first
  await page.click("#setup-form button[type=submit]");
  assert.match(await text(page, "#su-error"), /name/);
  await page.fill("#su-name", "Front room");
  await page.selectOption("#su-type", "living-room");
  await page.fill("#su-len", "four");
  await page.click("#setup-form button[type=submit]");
  assert.match(await text(page, "#su-error"), /numbers/);
  await page.fill("#su-len", "4.8"); await page.fill("#su-wid", "3.6"); await page.fill("#su-hei", "2.5"); await page.fill("#su-budget", "£6,000");
  await page.click("#setup-form button[type=submit]");
  await page.waitForSelector("#app:not([hidden])");
  const d = await dump(page);
  assert.equal(d["room/brief"].name, "Front room");
  assert.equal(d["room/brief"].length_mm, 4800);
  assert.equal(d["room/brief"].budget, 6000);
  assert.equal(d["elements/paint"].qty, 35.7, "net wall area 2(L+W)H x 0.85");
  assert.equal(d["elements/flooring"].qty, 19, "floor area + 10%");
  assert.ok(d["state/selection"]);
  assert.equal(await page.locator(".element").count(), 16);
  noErrors(errors); await ctx.close();
});

test("imperial setup converts feet and uses square feet", async () => {
  const { page, ctx, errors } = await openPlanner({});
  await ready(page);
  await page.fill("#su-name", "Den"); await page.selectOption("#su-units", "imperial");
  assert.match(await text(page, "#su-len-l"), /ft/);
  await page.fill("#su-len", "14"); await page.fill("#su-wid", "12"); await page.fill("#su-hei", "8");
  await page.click("#setup-form button[type=submit]");
  await page.waitForSelector("#app:not([hidden])");
  const d = await dump(page);
  assert.equal(d["room/brief"].length_mm, 4267);
  assert.equal(d["elements/flooring"].unit, "ft²");
  assert.ok(Math.abs(d["elements/flooring"].qty - 184.8) < 0.2, "14x12 ft + 10% = 184.8 sq ft, got " + d["elements/flooring"].qty);
  assert.match(await text(page, "#facts"), /14 ft × 12 ft/);
  noErrors(errors); await ctx.close();
});

// ---------- seeded rooms ----------
for (const fx of ["living-room", "bedroom-imperial", "bathroom", "kitchen-eur"]) {
  test(`${fx}: renders every part and option from the seed, totals match the script`, async () => {
    const { page, ctx, errors } = await openPlanner({ fixture: fx });
    await ready(page);
    const { store } = loadFixture(fx);
    const els = Object.keys(store).filter((k) => k.startsWith("elements/")).length;
    const opts = Object.entries(store).filter(([k, v]) => k.startsWith("options/") && v.status !== "rejected").length;
    assert.equal(await page.locator(".element").count(), els);
    assert.equal(await page.locator(".opt").count(), opts);
    // same total as planner.py's summary
    const out = execFileSync("python3", ["plugins/interior-design-planner/skills/room-planner/scripts/planner.py", "check", `tests/fixtures/${fx}/room.json`], { encoding: "utf8" });
    const scriptTotal = Number(out.match(/Starting choices \(picks \+ shortlisted\): \D*([\d,.]+)/)[1].replace(/,/g, ""));
    const pageTotal = await page.evaluate(() => window.RoomPlanner.totals().total);
    assert.ok(Math.abs(scriptTotal - pageTotal) < 0.01, `script ${scriptTotal} vs page ${pageTotal}`);
    noErrors(errors); await ctx.close();
  });
}

test("cost rules agree between page and script on a grid of cases", async () => {
  const cases = [];
  for (const unit of ["item", "m²", "m"]) for (const qty of [null, 1, 2, 7.7, 19]) for (const per of ["item", "m²", "m", "box", "tin"]) for (const covers of [null, 0.53, 16]) for (const price of [null, 0, 9.99, 44.94])
    cases.push({ o: { price, per, covers }, el: { unit, qty } });
  fs.writeFileSync(path.join(OUT, "cases.json"), JSON.stringify(cases));
  const py = JSON.parse(execFileSync("python3", ["-c", `
import json,sys; sys.path.insert(0,'plugins/interior-design-planner/skills/room-planner/scripts'); import planner
cases=json.load(open('tests/output/cases.json')); print(json.dumps([ (lambda r: None if r is None else r[0])(planner.cost(c['o'],c['el'])) for c in cases]))`], { encoding: "utf8" }));
  const { page, ctx } = await openPlanner({});
  await ready(page);
  const js = await page.evaluate((cs) => cs.map((c) => { const r = window.RoomPlanner.cost(c.o, c.el); return r ? r.cost : null; }), cases);
  const bad = cases.map((c, i) => [c, py[i], js[i]]).filter(([, a, b]) => !(a === b || (a != null && b != null && Math.abs(a - b) < 0.005)));
  assert.equal(bad.length, 0, "mismatches: " + JSON.stringify(bad.slice(0, 5)));
  await ctx.close();
});

test("choosing, clearing, quantities and budget", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  const before = await page.evaluate(() => window.RoomPlanner.totals().total);
  await page.click('.opt[data-opt="sofa-linen"] .pick');
  await page.waitForTimeout(60);
  let d = await dump(page);
  assert.equal(d["state/selection"].map.sofa, "sofa-linen");
  const after = await page.evaluate(() => window.RoomPlanner.totals().total);
  assert.equal(Math.round((before - after) * 100) / 100, 1495 - 899);
  assert.match(await text(page, "#budget-text"), /left of £6,000/);
  // quantity change re-prices flooring (54.99 per m²)
  await page.fill('input[data-qty="flooring"]', "25");
  await page.locator('input[data-qty="flooring"]').press("Tab");
  await page.waitForTimeout(80);
  d = await dump(page);
  assert.equal(d["elements/flooring"].qty, 25);
  const total2 = await page.evaluate(() => window.RoomPlanner.totals().total);
  assert.ok(Math.abs(total2 - after - (25 - 19) * 54.99) < 0.01);
  // bad quantity rejected politely
  await page.fill('input[data-qty="flooring"]', "lots");
  await page.locator('input[data-qty="flooring"]').press("Tab");
  await page.waitForSelector("#toast:not([hidden])");
  assert.match(await text(page, "#toast-text"), /number/);
  // clear
  await page.click('button[data-clear="sofa"]');
  await page.waitForTimeout(60);
  d = await dump(page);
  assert.equal(d["state/selection"].map.sofa, null);
  // over budget
  await page.fill('input[data-qty="flooring"]', "200");
  await page.locator('input[data-qty="flooring"]').press("Tab");
  await page.waitForTimeout(80);
  assert.match(await text(page, "#budget-text"), /over/);
  assert.equal(await page.locator("#bar.over").count(), 1);
  noErrors(errors); await ctx.close();
});

test("status, filters, presets", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  assert.equal(await page.locator('.opt[data-opt="sofa-corner"]').count(), 0, "rejected hidden by default");
  await page.click('button[data-filter="rejected"]');
  await page.waitForTimeout(60);
  assert.equal(await page.locator('.opt[data-opt="sofa-corner"]').count(), 1);
  await page.click('button[data-filter="active"]');
  await page.waitForTimeout(60);
  await page.selectOption('select[data-status="sofa-linen"]', "rejected");
  await page.waitForTimeout(80);
  assert.equal((await dump(page))["options/sofa-linen"].status, "rejected");
  assert.equal(await page.locator('.opt[data-opt="sofa-linen"]').count(), 0);
  // presets: change a pick, then re-apply starting picks
  await page.click('.opt[data-opt="paint-pointing"] .pick');
  await page.click('button[data-preset="suggested"]');
  await page.waitForTimeout(80);
  assert.equal((await dump(page))["state/selection"].map.paint, "paint-slaked");
  await page.click("#save-preset");
  await page.waitForTimeout(80);
  assert.equal(Object.keys(await dump(page)).filter((k) => k.startsWith("presets/")).length, 3, "suggested + cheapest + the saved set");
  noErrors(errors); await ctx.close();
});

test("add, edit and validate an option by hand, with a photo", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.click('button[data-add="side-table"]');
  await page.click("#od-save");
  assert.match(await text(page, "#od-error"), /name/);
  await page.fill("#od-name", "Marble side table");
  await page.fill("#od-price", "£1,2x");
  await page.click("#od-save");
  assert.match(await text(page, "#od-error"), /number/);
  await page.fill("#od-price", "£129");
  await page.fill("#od-url", "ftp://nope");
  await page.click("#od-save");
  assert.match(await text(page, "#od-error"), /https/);
  await page.fill("#od-url", "https://example.com/marble");
  await page.setInputFiles("#od-photo", { name: "t.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mPg4+MDAAAuABdIcdHPAAAAAElFTkSuQmCC", "base64") });
  await page.click("#od-save");
  await page.waitForTimeout(120);
  let d = await dump(page);
  const [id, o] = Object.entries(d).find(([k, v]) => k.startsWith("options/") && v.name === "Marble side table");
  assert.equal(o.price, 129); assert.equal(o.element, "side-table"); assert.match(o.image, /^\/_blob\/up\d+$/); assert.equal(o.status, "idea");
  // edit: pack pricing on flooring needs covers
  const oid = id.split("/")[1];
  await page.click(`button[data-edit="${oid}"]`);
  assert.equal(await page.inputValue("#od-name"), "Marble side table");
  await page.fill("#od-name", "Marble side table, small");
  await page.click("#od-save");
  await page.waitForTimeout(80);
  d = await dump(page);
  assert.equal(d[id].name, "Marble side table, small");
  await page.click('button[data-add="flooring"]');
  await page.fill("#od-name", "Oak boards"); await page.fill("#od-price", "60");
  await page.selectOption("#od-per", "box");
  assert.equal(await page.locator("#od-covers-f").isVisible(), true);
  await page.fill("#od-covers", "2.2");
  await page.click("#od-save");
  await page.waitForTimeout(80);
  const boards = Object.values(await dump(page)).find((v) => v.name === "Oak boards");
  assert.equal(boards.per, "box"); assert.equal(boards.covers, 2.2);
  const c = await page.evaluate((b) => window.RoomPlanner.cost(b, { unit: "m²", qty: 19 }), boards);
  assert.equal(c.cost, 9 * 60);
  noErrors(errors); await ctx.close();
});

test("photo on an existing card", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.click('button[data-photo="sofa-linen"]')]);
  await chooser.setFiles({ name: "s.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mPg4+MDAAAuABdIcdHPAAAAAElFTkSuQmCC", "base64") });
  await page.waitForTimeout(150);
  assert.match((await dump(page))["options/sofa-linen"].image, /^\/_blob\//);
  noErrors(errors); await ctx.close();
});

test("remove with undo, for options and whole parts", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.click('button[data-del-opt="sofa-olive"]');
  await page.waitForTimeout(80);
  let d = await dump(page);
  assert.equal(d["options/sofa-olive"], undefined);
  assert.equal(d["state/selection"].map.sofa, null);
  await page.click("#toast-undo");
  await page.waitForTimeout(120);
  d = await dump(page);
  assert.equal(d["options/sofa-olive"].name, "Three-seat sofa in olive velvet");
  assert.equal(d["state/selection"].map.sofa, "sofa-olive");
  // part: needs a second click to confirm
  await page.click('button[data-del-el="sofa"]');
  assert.match(await page.locator('button[data-del-el="sofa"]').innerText(), /3 options/);
  await page.click('button[data-del-el="sofa"]');
  await page.waitForTimeout(120);
  d = await dump(page);
  assert.equal(d["elements/sofa"], undefined); assert.equal(d["options/sofa-linen"], undefined);
  await page.click("#toast-undo");
  await page.waitForTimeout(150);
  d = await dump(page);
  assert.ok(d["elements/sofa"] && d["options/sofa-linen"] && d["options/sofa-corner"]);
  assert.equal(d["state/selection"].map.sofa, "sofa-olive");
  noErrors(errors); await ctx.close();
});

test("add a new part of the room", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.click("#add-part");
  await page.fill("#pd-name", "Window seat cushion");
  await page.fill("#pd-group", "Seating");
  await page.click('#part-form button[value="save"]');
  await page.waitForTimeout(80);
  const d = await dump(page);
  assert.equal(d["elements/window-seat-cushion"].group, "Seating");
  assert.equal(await page.locator("#el-window-seat-cushion").count(), 1);
  noErrors(errors); await ctx.close();
});

test("schedule copy and spreadsheet download", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.click("#copy-btn");
  await page.waitForTimeout(80);
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  assert.match(clip, /^Part\tChosen\tSupplier/);
  assert.match(clip, /Engineered oak, natural oiled\tExample Shop\t19 m²\t£1,045/);
  await page.click("#csv-btn");
  await page.waitForTimeout(80);
  const saves = await page.evaluate(() => window.__saves);
  assert.equal(saves[0].filename, "living-room-12-mill-lane-schedule.csv");
  assert.match(saves[0].text, /"Little Greene Slaked Lime Mid, 2.5 L"/);
  noErrors(errors); await ctx.close();
});

test("ChatGPT prompt, link and reference board", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  const prompt = await page.evaluate(() => window.RoomPlanner.buildPrompt());
  assert.match(prompt, /Sofa: Three-seat sofa in olive velvet/);
  assert.match(prompt, /Size: 4\.8 m × 3\.6 m, ceiling 2\.5 m/);
  assert.match(prompt, /NOT CHOSEN YET[\s\S]*Armchair/);
  const href = await page.getAttribute("#gpt-open", "href");
  assert.ok(href.startsWith("https://chatgpt.com/?q="));
  assert.equal(decodeURIComponent(href.slice(23)), prompt);
  assert.ok(href.length < 8000, "link length " + href.length);
  assert.equal(await page.getAttribute("#gpt-top", "href"), href);
  // edited prompt is used until a choice changes
  await page.click("#gpt summary");
  await page.fill("#gpt-prompt", "custom prompt");
  assert.equal(await page.getAttribute("#gpt-open", "href"), "https://chatgpt.com/?q=custom%20prompt");
  await page.click('.opt[data-opt="sofa-linen"] .pick');
  await page.waitForTimeout(80);
  assert.match(decodeURIComponent(await page.getAttribute("#gpt-open", "href")), /Linen-look/);
  await page.click("#gpt-board");
  await page.waitForTimeout(400);
  const saves = await page.evaluate(() => window.__saves);
  assert.equal(saves.length, 1); assert.match(saves[0].filename, /reference-board\.png$/); assert.ok(saves[0].size > 2000, "board size " + saves[0].size);
  noErrors(errors); await ctx.close();
});

test("ChatGPT link stays a sensible length for a big room", async () => {
  const { store } = loadFixture("living-room");
  const big = structuredClone(store);
  for (const k of Object.keys(big)) if (k.startsWith("options/")) big[k].spec = "A long specification line about materials, sizes and finishes. ".repeat(3);
  for (const k of Object.keys(big)) if (k.startsWith("elements/")) big["state/selection"].map[k.slice(9)] = Object.keys(big).find((x) => x.startsWith("options/") && big[x].element === k.slice(9))?.slice(8) ?? null;
  const { page, ctx } = await openPlanner({ store: big });
  await ready(page);
  const len = (await page.getAttribute("#gpt-open", "href")).length;
  assert.ok(len < 12000, "URL length " + len);
  await ctx.close();
});

test("backup out and back in restores the same planner", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.click("#backup-save");
  await page.waitForTimeout(80);
  const backup = (await page.evaluate(() => window.__saves))[0].text;
  const original = await dump(page);
  await ctx.close();
  // restore into a planner that already has different content
  const { page: p2, ctx: c2, errors: e2 } = await openPlanner({ fixture: "bathroom" });
  await ready(p2);
  await p2.setInputFiles("#backup-file", { name: "b.json", mimeType: "application/json", buffer: Buffer.from(backup) });
  await p2.waitForSelector("#restore-confirm:not([hidden])");
  assert.match(await p2.locator("#restore-text").innerText(), /Living room, 12 Mill Lane/);
  await p2.click("#restore-go");
  await p2.waitForFunction(() => /restored/.test(document.getElementById("backup-status").textContent));
  const restored = await dump(p2);
  const pick = (d) => Object.fromEntries(Object.entries(d).filter(([k]) => /^(elements|options|presets|state)\//.test(k)));
  assert.deepEqual(pick(restored), pick(original));
  assert.equal(restored["room/brief"].name, original["room/brief"].name);
  // a non-backup file is refused
  await p2.setInputFiles("#backup-file", { name: "x.json", mimeType: "application/json", buffer: Buffer.from('{"hello":1}') });
  await p2.waitForTimeout(80);
  assert.match(await p2.locator("#backup-status").innerText(), /isn't a Room Planner backup/);
  noErrors(errors); noErrors(e2); await c2.close();
});

test("inbox without the desktop app queues links and explains", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room" });
  await ready(page);
  await page.fill("#in-url", "not a link");
  await page.click("#inbox-form button[type=submit]");
  assert.match(await text(page, "#inbox-status"), /doesn't look like a web link/);
  await page.fill("#in-url", "https://example.com/table");
  await page.click("#inbox-form button[type=submit]");
  await page.waitForTimeout(80);
  await page.click("#update-btn");
  await page.waitForTimeout(150);
  assert.match(await text(page, "#inbox-status"), /Queued/);
  const items = Object.entries(await dump(page)).filter(([k]) => k.startsWith("inbox/"));
  assert.equal(items[0][1].state, "queued");
  noErrors(errors); await ctx.close();
});

test("inbox with the desktop app reads the page and adds an option", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room", caps: { db: true, assets: true, downloads: true, mcp: true, sample: true } });
  await ready(page);
  await page.fill("#in-url", "https://example.com/table");
  await page.selectOption("#in-el", "coffee-table");
  await page.click("#inbox-form button[type=submit]");
  await page.waitForTimeout(80);
  await page.click("#update-btn");
  await page.waitForFunction(() => /Added 1 option/.test(document.getElementById("inbox-status").textContent), null, { timeout: 20000 });
  const d = await dump(page);
  const o = Object.values(d).find((v) => v.name === "Oak coffee table");
  assert.equal(o.price, 249); assert.equal(o.source, "link"); assert.equal(o.element, "coffee-table");
  assert.equal(Object.entries(d).find(([k]) => k.startsWith("inbox/"))[1].state, "done");
  noErrors(errors); await ctx.close();
});

test("save failures are explained, not silent", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "living-room", failWrites: "quota_exceeded" });
  await ready(page);
  await page.click('.opt[data-opt="sofa-linen"] .pick');
  await page.waitForSelector("#toast:not([hidden])");
  assert.match(await text(page, "#toast-text"), /planner is full/);
  noErrors(errors); await ctx.close();
});

test("estimated sizes, kept items and owned products are shown and described", async () => {
  const { store } = loadFixture("living-room");
  const st = structuredClone(store);
  st["room/brief"].sizesEstimated = true;
  st["room/brief"].keeping = "the grey three-seat sofa and the fireplace";
  st["options/sofa-mine"] = { element: "sofa", name: "Our grey sofa", owned: true, price: 0, status: "shortlisted" };
  st["state/selection"].map.sofa = "sofa-mine";
  const { page, ctx, errors } = await openPlanner({ store: st });
  await ready(page);
  assert.match(await text(page, "#facts"), /Size \(estimate\)/);
  assert.match(await text(page, "#room-text"), /Staying: the grey three-seat sofa/);
  assert.match(await text(page, '.opt[data-opt="sofa-mine"]'), /Already yours/);
  const prompt = await page.evaluate(() => window.RoomPlanner.buildPrompt());
  assert.match(prompt, /Size \(approximate\)/);
  assert.match(prompt, /Staying as they are: the grey three-seat sofa/);
  noErrors(errors); await ctx.close();
});

test("messy and hostile data: no script runs, nothing crashes", async () => {
  const { page, ctx, errors } = await openPlanner({ fixture: "messy" });
  await ready(page);
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__xss), undefined, "injected markup ran");
  assert.equal(await page.locator("#app").isVisible(), true);
  assert.equal(await page.locator('a[href^="javascript"]').count(), 0);
  assert.equal(await page.locator('img[src^="https://evil"]').count(), 0);
  assert.match(await text(page, "#room-title"), /<img src=x/);
  assert.match(await text(page, "#el-a"), /Set the quantity to see a total/);
  assert.equal(await page.evaluate(() => window.RoomPlanner.totals().unpriced), 1, "only the per-m² option without a quantity is unpriced");
  await page.click('button[data-preset="p"]');
  await page.waitForTimeout(80);
  assert.equal((await dump(page))["state/selection"].map.zzz, undefined, "preset ignores parts that no longer exist");
  noErrors(errors); await ctx.close();
});

// ---------- layout, themes, accessibility ----------
for (const [label, viewport] of [["desktop", { width: 1280, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
  for (const scheme of ["light", "dark"]) {
    test(`layout ${label} ${scheme}: no sideways scroll, readable, screenshot`, async () => {
      const { page, ctx, errors } = await openPlanner({ fixture: "living-room", viewport, colorScheme: scheme });
      await ready(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      assert.ok(overflow <= 0, `page scrolls sideways by ${overflow}px`);
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      assert.equal(bg, scheme === "dark" ? "rgb(21, 25, 24)" : "rgb(239, 240, 237)");
      await page.screenshot({ path: path.join(OUT, `${label}-${scheme}.png`), fullPage: true });
      noErrors(errors); await ctx.close();
    });
  }
}

test("setup screen on a phone", async () => {
  const { page, ctx, errors } = await openPlanner({ viewport: { width: 390, height: 844 } });
  await ready(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(overflow <= 0);
  await page.screenshot({ path: path.join(OUT, "phone-setup.png"), fullPage: true });
  noErrors(errors); await ctx.close();
});

for (const scheme of ["light", "dark"]) {
  test(`accessibility scan (${scheme})`, async () => {
    const { page, ctx } = await openPlanner({ fixture: "living-room", colorScheme: scheme });
    await ready(page);
    await page.addScriptTag({ content: AXE });
    const res = await page.evaluate(async () => (await window.axe.run(document, { resultTypes: ["violations"] })).violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes[0] && v.nodes[0].html.slice(0, 120) })));
    fs.writeFileSync(path.join(OUT, `axe-${scheme}.json`), JSON.stringify(res, null, 2));
    const serious = res.filter((v) => v.impact === "serious" || v.impact === "critical");
    assert.deepEqual(serious, [], "accessibility problems: " + JSON.stringify(serious, null, 1));
    await ctx.close();
  });
}
