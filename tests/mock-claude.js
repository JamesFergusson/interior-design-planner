// In-memory stand-in for the claude.ai runtime used by the planner page.
// Loaded with page.addInitScript BEFORE the page runs. Configure with window.__MOCK__ = {store, caps, failWrites}.
// Mirrors the documented contract (db.d.ts 0.2.x): set = full replace, update = merge and REQUIRES the doc to exist,
// snapshots are async, query ordering by one field with missing values last, ids from add().
(() => {
  const cfg = window.__MOCK__ || {};
  const store = new Map(Object.entries(cfg.store || {})); // "coll/id" -> body
  const listeners = new Set();
  const log = (window.__mockLog = []);
  window.__saves = [];
  window.__uploads = [];
  let seq = 0;

  const clone = (x) => (x === undefined ? undefined : JSON.parse(JSON.stringify(x)));
  const err = (code, message) => Object.assign(new Error(message || code), { code });
  const deepMerge = (a, b) => {
    const out = { ...(a || {}) };
    for (const [k, v] of Object.entries(b)) {
      out[k] = v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k]) ? deepMerge(out[k], v) : clone(v);
    }
    return out;
  };
  const SEG = /^[A-Za-z0-9_\-.~:@+]{1,200}$/;
  function checkPath(p, even) {
    const segs = p.split("/");
    if (segs.some((s) => !SEG.test(s)) || (segs.length % 2 === 0) !== even) throw new TypeError("bad path " + p);
  }
  function notify() {
    setTimeout(() => { for (const l of [...listeners]) l(); }, 0);
  }
  function guard(op, path) {
    log.push([op, path]);
    if (cfg.failWrites) return Promise.reject(err(cfg.failWrites));
    return null;
  }
  function docSnap(path) {
    const body = store.get(path);
    const id = path.split("/").pop();
    const frozen = body === undefined ? undefined : Object.freeze(clone(body));
    return { id, exists: body !== undefined, data: () => frozen, metadata: {} };
  }
  function docRef(path) {
    checkPath(path, true);
    return {
      id: path.split("/").pop(), path,
      async get() { return docSnap(path); },
      set(data) { const g = guard("set", path); if (g) return g; if (!data || typeof data !== "object" || Array.isArray(data)) return Promise.reject(err("invalid_argument")); store.set(path, clone(data)); notify(); return Promise.resolve(); },
      update(data) { const g = guard("update", path); if (g) return g; if (!store.has(path)) return Promise.reject(err("invalid_argument", "update on missing doc " + path)); store.set(path, deepMerge(store.get(path), data)); notify(); return Promise.resolve(); },
      delete() { const g = guard("delete", path); if (g) return g; store.delete(path); notify(); return Promise.resolve(); },
      onSnapshot(next) { let last; const fire = () => { const s = docSnap(path); const key = JSON.stringify(s.exists ? s.data() : null); if (key !== last) { last = key; next(s); } }; listeners.add(fire); setTimeout(fire, 0); return () => listeners.delete(fire); },
      collection(sub) { return collRef(path + "/" + sub); },
    };
  }
  function query(coll, order) {
    const docs = [...store.keys()].filter((k) => k.startsWith(coll + "/") && k.split("/").length === coll.split("/").length + 1).sort().map(docSnap);
    if (order) docs.sort((a, b) => { const x = a.data()[order], y = b.data()[order]; if (x === undefined && y === undefined) return 0; if (x === undefined) return 1; if (y === undefined) return -1; return x < y ? -1 : x > y ? 1 : 0; });
    return { docs, size: docs.length, empty: !docs.length, docChanges: () => [], metadata: {} };
  }
  function collRef(coll, order) {
    checkPath(coll, false);
    const q = {
      path: coll,
      orderBy(f) { return collRef(coll, f); },
      where() { return q; }, limit() { return q; },
      async get() { return query(coll, order); },
      onSnapshot(next) { let last; const fire = () => { const s = query(coll, order); const key = JSON.stringify(s.docs.map((d) => [d.id, d.data()])); if (key !== last) { last = key; next(s); } }; listeners.add(fire); setTimeout(fire, 0); return () => listeners.delete(fire); },
      doc(id) { return docRef(coll + "/" + (id || "m" + (++seq).toString(36) + Date.now().toString(36))); },
      async add(data) { const r = q.doc(); await r.set(data); return r; },
    };
    return q;
  }
  const db = { doc: docRef, collection: (c) => collRef(c) };

  const assets = {
    async upload(blob) { const id = "up" + (++seq); window.__uploads.push({ id, size: blob.size, type: blob.type }); (window.__blobUrls = window.__blobUrls || {})[id] = blob; return { id, url: "/_blob/" + id, sizeBytes: blob.size, contentType: blob.type }; },
    async list() { return { assets: [], usage: {} }; }, async delete() {},
  };
  const downloads = {
    async save({ filename, data }) {
      if (cfg.declineDownloads) throw err("declined");
      let size = 0, text = null, type = "";
      if (data instanceof Blob) { size = data.size; type = data.type; if (/json|csv|text/.test(type) || /\.(csv|json)$/.test(filename)) text = await data.text(); }
      else if (typeof data === "string") { size = data.length; text = data; }
      window.__saves.push({ filename, size, text, type });
    },
  };
  const caps = cfg.caps || { db: true, assets: true, downloads: true, mcp: false, sample: false };
  const fakeMcp = {
    async listTools() { return { servers: [{ server: "host:claude_browser", tools: [{ name: "preview_start" }] }] }; },
    async callTool(server, tool, input) {
      log.push(["mcp", tool, input && input.url]);
      if (tool === "preview_start") return { content: [{ type: "text", text: "Opened tabId T1." }] };
      if (tool === "navigate") return { content: [{ type: "text", text: "ok" }] };
      if (tool === "get_page_text") return { content: [{ type: "text", text: (cfg.pageText || "Oak coffee table. Price £249.00. 1100 x 600 x 400 mm, solid oak. ").repeat(20) }] };
      throw err("tool_error");
    },
  };
  const fakeSample = Object.assign(async () => ({ text: "", truncated: false }), {
    async json(prompt) { log.push(["sample", prompt.length]); return cfg.sampleReply || { element: "coffee-table", name: "Oak coffee table", supplier: "Test Shop", price: 249, per: "item", covers: null, priceNote: "", spec: "1100 x 600 mm, solid oak", note: "" }; },
    async limits() { return {}; },
  });
  // Real runtime timing: use() resolves later, never synchronously.
  window.claude = {
    use(name) {
      return new Promise((res) => setTimeout(() => {
        if (!caps[name]) return res(null);
        res({ db, assets, downloads, mcp: fakeMcp, sample: fakeSample }[name] || null);
      }, 5));
    },
  };
  window.__mockStore = store;
  window.__dump = () => Object.fromEntries([...store.entries()].map(([k, v]) => [k, clone(v)]));
})();
