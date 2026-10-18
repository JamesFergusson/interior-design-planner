// Opens the planner template in headless Chromium, wrapped the way the Artifact tool wraps a published page,
// with the in-memory claude.ai stand-in (tests/mock-claude.js) and fixture photos served at /_blob/<id>.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const TEMPLATE = path.join(ROOT, "plugins/interior-design-planner/skills/room-planner/assets/planner.html");
const MOCK = fs.readFileSync(path.join(ROOT, "tests/mock-claude.js"), "utf8");
export const OUT = path.join(ROOT, "tests/output");
fs.mkdirSync(OUT, { recursive: true });

const SKELETON = (body) => `<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}html{scroll-padding-top:env(safe-area-inset-top,0px)}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#fff;color:#000}img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style></head><body>${body}</body></html>`;

const GREY_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mPg4+MDAAAuABdIcdHPAAAAAElFTkSuQmCC", "base64");

export function loadFixture(name) {
  if (!name) return { store: {}, blobs: {} };
  const dir = path.join(ROOT, "tests/fixtures", name);
  return { store: JSON.parse(fs.readFileSync(path.join(dir, "store.json"), "utf8")), blobs: JSON.parse(fs.readFileSync(path.join(dir, "blobs.json"), "utf8")) };
}

let browser;
export async function getBrowser() { if (!browser) browser = await chromium.launch(); return browser; }
export async function closeBrowser() { if (browser) await browser.close(); browser = null; }

export async function openPlanner({ fixture, store, caps, failWrites, noClaude, colorScheme = "light", viewport = { width: 1280, height: 900 }, extra = {} } = {}) {
  const b = await getBrowser();
  const ctx = await b.newContext({ viewport, colorScheme, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await ctx.newPage();
  const fx = loadFixture(fixture);
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push("console: " + m.text()); });
  const html = SKELETON(fs.readFileSync(TEMPLATE, "utf8"));
  await ctx.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.host === "planner.test" && url.pathname === "/") return route.fulfill({ contentType: "text/html", body: html });
    if (url.host === "planner.test" && url.pathname.startsWith("/_blob/")) {
      const id = url.pathname.slice(7);
      const f = fx.blobs[id];
      return route.fulfill({ contentType: "image/png", body: f ? fs.readFileSync(path.join(ROOT, f)) : GREY_PNG });
    }
    return route.abort(); // fonts and anything external: keep tests offline and deterministic
  });
  if (!noClaude) {
    const cfg = { store: store || fx.store, caps: caps || { db: true, assets: true, downloads: true, mcp: false, sample: false }, failWrites, ...extra };
    await page.addInitScript(`window.__MOCK__ = ${JSON.stringify(cfg)};`);
    await page.addInitScript(MOCK);
  }
  await page.goto("https://planner.test/");
  return { page, ctx, errors };
}

export async function ready(page) {
  await page.waitForFunction(() => document.getElementById("loading").hidden === true, null, { timeout: 5000 });
  await page.waitForTimeout(80);
}
export const dump = (page) => page.evaluate(() => window.__dump());
