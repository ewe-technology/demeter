// Run a built PnL page's scripts against a stub DOM and report what each container received.
// Exit code 1 on a script error, on NaN / undefined in rendered HTML, or on an empty container or card part.
//   node check_page.js page.html
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const containers = [...html.matchAll(/id="(pnl-[a-z]+)"/g)].map(m => m[1]).filter(i => i !== "pnl-tip");

const els = {};
const mk = id => ({
  id, _h: "", kids: [], hidden: false, style: {}, className: "", dataset: {}, offsetWidth: 0, offsetHeight: 0,
  set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h; },
  appendChild(c) { this.kids.push(c); }, addEventListener() {}, setAttribute() {},
  querySelector() { return mk("q"); }, querySelectorAll() { return []; },
});
global.document = { getElementById: id => els[id] ||= mk(id), createElement: () => mk("new"), body: mk("body"), querySelectorAll: () => [] };
global.window = global; global.innerWidth = 1200; global.innerHeight = 800;

try { for (const s of scripts) (0, eval)(s); }
catch (e) { console.log("SCRIPT ERROR:", e.message); process.exit(1); }

let failed = false;
const BAD = /NaN|undefined/;
for (const id of containers) {
  const el = els[id];
  const body = el ? el._h + el.kids.map(k => k._h).join("") : "";
  const note = !body.length ? "  EMPTY" : BAD.test(body) ? "  BAD VALUES" : "";
  console.log(`${id.padEnd(16)} ${String(body.length).padStart(7)} chars${el && el.kids.length ? `, ${el.kids.length} cards` : ""}${note}`);
  if (note) failed = true;
}
for (const [id, el] of Object.entries(els)) {  // each card's legend, chart and table
  if (!/-(chart|table|legend)$/.test(id)) continue;
  if (!el._h.length || BAD.test(el._h)) { console.log(`${id}: ${el._h.length ? "BAD VALUES" : "EMPTY"}`); failed = true; }
}
console.log(failed ? "PAGE CHECK FAILED" : "PAGE CHECK OK");
process.exit(failed ? 1 : 0);
