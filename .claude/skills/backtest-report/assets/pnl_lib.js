/*
 * PnL page renderer for backtest yearly reports. Everything renders expanded (no toggles), so the page prints to
 * PDF complete. Call PNL.render(config) once; it fills the elements whose ids are listed below, skipping any the
 * page does not have.
 *
 *   #pnl-takeaways  summary tiles              config.takeaways
 *   #pnl-tables     yearly return / maxDD       config.tables (one table each: absolute, or minus a control)
 *   #pnl-cum        year-end NAV chart + table  config.cum
 *   #pnl-attr       one card per strategy       config.attrCards: each year split into components
 *   #pnl-diff       one card per pair           config.diffCards: (strategy - reference) split into components
 *
 * config = {
 *   years: ["2022", ...], yearLabels: {"2026": "2026（到 9/30）"},
 *   series: { key: { name, desc, tag: "ctrl" | {kind: "pass"|"fail"|"list", label},
 *                    years: {"2022": {ret, mdd}, ...},            // fractions: 0.12 = +12%
 *                    attr: {"2022": {component: fraction of the year's starting NAV}},
 *                    info: {"2022": {"重建次數": 12}} } },         // extra grey rows under the attribution table
 *   groups: [{label, keys: [...]}],                               // rows of the yearly tables, in order
 *   tables: [{base: "abs" | seriesKey, title}],
 *   chains: [{label, years: [...]}],                              // compounded columns in the yearly tables
 *   cum: {keys: [...]},
 *   components: {component: {name, color: 1..8}},                 // color slots --s1 .. --s8
 *   attrCards: [{key, components: [...], names: {component: name}, explain: "<ul>...</ul>"}],
 *   diffCards: [{key, ref, components: [...], explain}],          // per component: attr[key] - attr[ref]
 *   takeaways: [{big, label, text}],
 * }
 */
(function () {
  const pct = (x, d = 1) => (x == null || isNaN(x)) ? "—" : (x >= 0 ? "+" : "−") + Math.abs(x * 100).toFixed(d) + "%";
  const pt = (x, d = 1) => (x == null || isNaN(x)) ? "—" : (x >= 0 ? "+" : "−") + Math.abs(x * 100).toFixed(d);
  const el = id => document.getElementById(id);
  function heat(x, scale) {
    if (x == null || isNaN(x)) return "";
    const a = Math.min(Math.abs(x) / scale, 1) * 0.32 + 0.04;
    return `background: rgba(var(${x >= 0 ? "--pos-bg" : "--neg-bg"}), ${a.toFixed(3)})`;
  }
  const sw = c => `<i class="sw" style="background:var(--s${c})"></i>`;
  const diamond = label => `<span><svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true"><path d="M0,-5 L5,0 L0,5 L-5,0Z" fill="var(--ink)"/></svg>${label}</span>`;

  /* ---------- tooltip ---------- */
  let tip;
  function showTip(e, html) {
    tip.innerHTML = html; tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + w > innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > innerHeight - 8) y = e.clientY - h - 14;
    tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  /* ---------- diverging stacked rows: one row per year, positives right of 0, negatives left ---------- */
  function stackedRows(target, rows, opts) {
    const W = 900, L = opts.left || 120, Rm = 70, rowH = 42, T0 = 26, Bm = 30;
    const H = T0 + rows.length * rowH + Bm;
    let mn = 0, mx = 0;
    for (const r of rows) {
      const p = r.parts.filter(x => x.v > 0).reduce((s, x) => s + x.v, 0), n = r.parts.filter(x => x.v < 0).reduce((s, x) => s + x.v, 0);
      mx = Math.max(mx, p, r.net ?? 0); mn = Math.min(mn, n, r.net ?? 0);
    }
    const span = mx - mn || 0.01;
    const step = span > 1.6 ? 0.5 : span > 0.8 ? 0.25 : span > 0.3 ? 0.1 : span > 0.12 ? 0.05 : 0.02;
    mn = Math.floor(mn / step - 1e-9) * step; mx = Math.ceil(mx / step + 1e-9) * step;
    const X = v => L + (W - L - Rm) * (v - mn) / (mx - mn);
    let g = "";
    for (let v = mn; v <= mx + 1e-9; v += step) {
      const z = Math.abs(v) < 1e-9;
      g += `<line x1="${X(v)}" x2="${X(v)}" y1="${T0 - 6}" y2="${H - Bm}" stroke="var(${z ? "--axis" : "--rule"})" stroke-width="${z ? 1.5 : 1}"/>`;
      g += `<text x="${X(v)}" y="${H - 12}" text-anchor="middle">${z ? "0" : pt(v, step < 0.05 ? 1 : 0)}</text>`;
    }
    g += `<text x="${W - Rm}" y="${T0 - 12}" text-anchor="end">${opts.unit || "單位：年初淨值的 %（pt）"}</text>`;
    rows.forEach((r, i) => {
      const y0 = T0 + i * rowH + 8, bh = rowH - 16, cy = y0 + bh / 2;
      g += `<text class="lbl-2" x="${L - 12}" y="${cy + 4}" text-anchor="end">${r.label}</text>`;
      if (!r.parts.length) { g += `<text x="${X(0) + 8}" y="${cy + 4}">沒有拆解資料${r.net != null ? `（報酬 ${pct(r.net)}）` : ""}</text>`; return; }
      let pos = 0, neg = 0;
      for (const p of r.parts) {
        if (Math.abs(p.v) < 1e-5) continue;
        const a = p.v > 0 ? pos : neg + p.v, b = p.v > 0 ? pos + p.v : neg;
        if (p.v > 0) pos += p.v; else neg += p.v;
        const x1 = X(a), w = Math.max(X(b) - x1 - 2, 0.8);
        g += `<rect x="${x1 + 1}" y="${y0}" width="${w}" height="${bh}" rx="2" fill="var(--s${p.color})" data-tip="${encodeURIComponent(JSON.stringify({ t: r.label, n: p.name, v: p.v, net: r.net }))}"/>`;
      }
      if (r.net == null) return;
      const nx = X(r.net);
      g += `<path d="M${nx},${cy - 7} L${nx + 6},${cy} L${nx},${cy + 7} L${nx - 6},${cy} Z" fill="var(--ink)" stroke="var(--surface)" stroke-width="1.5"/>`;
      const lx = Math.max(X(pos), nx + 6) + 8, lab = opts.netFmt(r.net);
      g += lx > W - 50 ? `<text class="lbl-ink" x="${W - 2}" y="${cy + 4}" text-anchor="end">${lab}</text>` : `<text class="lbl-ink" x="${lx}" y="${cy + 4}">${lab}</text>`;
    });
    target.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${opts.aria || ""}">${g}</svg>`;
    target.querySelectorAll("rect[data-tip]").forEach(rc => {
      rc.addEventListener("mousemove", e => {
        const d = JSON.parse(decodeURIComponent(rc.dataset.tip));
        showTip(e, `<div class="t">${d.t}</div><div class="row"><span>${d.n}</span><span>${pt(d.v)} pt</span></div>` +
          (d.net != null ? `<div class="row"><span>${opts.netName}</span><span>${opts.netFmt(d.net)}</span></div>` : ""));
      });
      rc.addEventListener("mouseleave", hideTip);
    });
  }

  function render(C) {
    tip = el("pnl-tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; tip.id = "pnl-tip"; tip.hidden = true; document.body.appendChild(tip); }
    const Y = C.years, YL = y => (C.yearLabels || {})[y] || y, S = C.series;
    const has = (k, y) => S[k] != null && S[k].years[y] != null;
    const chain = (k, ys) => ys.every(y => has(k, y)) ? ys.reduce((v, y) => v * (1 + S[k].years[y].ret), 1) - 1 : null;
    const worst = k => Math.min(...Y.filter(y => has(k, y)).map(y => S[k].years[y].mdd));
    const chains = C.chains || [{ label: "串接", years: Y }];
    const tagOf = s => !s.tag || s.tag === "ctrl" ? "" :
      `<span class="tag ${s.tag.kind}">${{ pass: "✓", fail: "✗", list: "△" }[s.tag.kind] || ""} ${s.tag.label}</span>`;

    /* takeaways */
    if (el("pnl-takeaways") && C.takeaways)
      el("pnl-takeaways").innerHTML = C.takeaways.map(t => `<div class="tk"><div class="big">${t.big}</div><div class="lbl">${t.label}</div><p>${t.text}</p></div>`).join("");

    /* yearly tables */
    const tables = C.tables || [{ base: "abs", title: "絕對報酬" }];
    if (el("pnl-tables")) {
      el("pnl-tables").innerHTML = tables.map((t, i) => `<div class="sub"><h3>${t.title}</h3><div class="tbl-box"><table id="pnl-table-${i}"></table></div></div>`).join("");
      tables.forEach((t, i) => {
        const base = t.base, rel = base !== "abs";
        let h = `<thead><tr><th>策略</th>${Y.map(y => `<th>${YL(y)}</th>`).join("")}${chains.map(c => `<th>${c.label}</th>`).join("")}<th>最差回撤</th></tr></thead><tbody>`;
        for (const g of C.groups) {
          h += `<tr class="grp"><td colspan="${Y.length + chains.length + 2}">${g.label}</td></tr>`;
          for (const k of g.keys) {
            const s = S[k], self = rel && k === base;
            let cells = "";
            for (const y of Y) {
              if (!has(k, y) || (rel && !has(base, y))) { cells += `<td class="na">—</td>`; continue; }
              const r = s.years[y], v = rel ? r.ret - S[base].years[y].ret : r.ret;
              cells += `<td><div class="cell"><span class="r" style="${self ? "" : heat(v, rel ? 0.4 : 1.0)}">${self ? "基準" : rel ? pt(v) : pct(v)}</span><span class="m">${pct(r.mdd)}</span></div></td>`;
            }
            for (const c of chains) {
              const v = chain(k, c.years), b = rel ? chain(base, c.years) : 0;
              if (v == null || b == null) { cells += `<td class="na">—</td>`; continue; }
              const d = rel ? v - b : v;
              cells += `<td><div class="cell"><span class="r" style="${self ? "" : heat(d, rel ? 1.5 : 2.5)}">${self ? "基準" : rel ? pt(d, 0) : pct(d, 0)}</span></div></td>`;
            }
            cells += `<td><div class="cell"><span class="m" style="font-size:13px">${pct(worst(k))}</span></div></td>`;
            h += `<tr class="${s.tag === "ctrl" ? "ctrl" : ""}"><td class="name"><span class="n">${s.name}</span>${tagOf(s)}<span class="d">${s.desc || ""}</span></td>${cells}</tr>`;
          }
        }
        el(`pnl-table-${i}`).innerHTML = h + "</tbody>";
      });
    }

    /* cumulative NAV */
    if (el("pnl-cum") && C.cum) {
      const keys = C.cum.keys, W = 900, H = 340, L = 44, R0 = 190, T0 = 24, Bm = 34;
      const xs = ["起點", ...Y.map(y => (C.yearLabels || {})[y] ? YL(y) : `${y} 年底`)];
      const series = keys.map((k, i) => { let v = 1; const pts = [1]; for (const y of Y) { if (!has(k, y)) break; v *= 1 + S[k].years[y].ret; pts.push(v); } return { k, c: (i % 8) + 1, pts }; });
      const maxV = Math.ceil(Math.max(...series.flatMap(s => s.pts)) * 2) / 2;
      const X = i => L + i * (W - L - R0) / (xs.length - 1), Yp = v => T0 + (H - T0 - Bm) * (1 - v / maxV);
      let g = "";
      for (let v = 0; v <= maxV + 1e-9; v += 0.5)
        g += `<line x1="${L}" x2="${W - R0}" y1="${Yp(v)}" y2="${Yp(v)}" stroke="var(--rule)"/><text x="${L - 8}" y="${Yp(v) + 4}" text-anchor="end">${v.toFixed(1)}</text>`;
      g += `<line x1="${L}" x2="${W - R0}" y1="${Yp(1)}" y2="${Yp(1)}" stroke="var(--axis)" stroke-dasharray="3 3"/>`;
      xs.forEach((s, i) => g += `<text x="${X(i)}" y="${H - 10}" text-anchor="middle">${s}</text>`);
      const full = series.filter(s => s.pts.length === xs.length).map(s => ({ s, y: Yp(s.pts.at(-1)) })).sort((a, b) => a.y - b.y);
      for (let i = 1; i < full.length; i++) if (full[i].y - full[i - 1].y < 15) full[i].y = full[i - 1].y + 15;
      for (const s of series) {
        g += `<path d="${s.pts.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Yp(v).toFixed(1)}`).join("")}" fill="none" stroke="var(--s${s.c})" stroke-width="2" stroke-linejoin="round"/>`;
        s.pts.forEach((v, i) => g += `<circle cx="${X(i)}" cy="${Yp(v)}" r="4" fill="var(--s${s.c})" stroke="var(--surface)" stroke-width="2"/>`);
      }
      for (const e of full) g += `<text class="lbl-ink" x="${W - R0 + 12}" y="${e.y + 4}">${S[e.s.k].name}  ${e.s.pts.at(-1).toFixed(2)}</text>`;
      for (const s of series.filter(s => s.pts.length < xs.length && s.pts.length > 1)) {
        const i = s.pts.length - 1;
        g += `<text class="lbl-ink" x="${X(i) + 10}" y="${Yp(s.pts[i]) + 18}">${S[s.k].name}  ${s.pts[i].toFixed(2)}</text>`;
      }
      el("pnl-cum").innerHTML = `<div class="legend">${series.map(s => `<span><i class="line" style="background:var(--s${s.c})"></i>${S[s.k].name}</span>`).join("")}</div>` +
        `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="淨值走勢">${g}</svg></div>` +
        `<div class="tbl-box flat"><table><thead><tr><th>淨值（起點 = 1）</th>${xs.slice(1).map(s => `<th>${s}</th>`).join("")}</tr></thead><tbody>` +
        series.map(s => `<tr><td>${sw(s.c)}${S[s.k].name}</td>${xs.slice(1).map((_, i) => `<td class="num">${s.pts[i + 1] != null ? s.pts[i + 1].toFixed(2) : "—"}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
    }

    /* cards */
    const comp = C.components || {};
    const itemsOf = (keys, names) => keys.map(k => ({ k, name: (names || {})[k] || (comp[k] || {}).name || k, color: (comp[k] || {}).color || 7 }));
    function drawCard(container, id, title, sub, explain, items, value, net, netName, netFmt, extraRows) {
      const d = document.createElement("div");
      d.className = "card";
      d.innerHTML = `<h3 class="strat">${title}<small>${sub || ""}</small></h3><div class="legend" id="${id}-legend"></div><div class="chart" id="${id}-chart"></div>` +
        `<div class="tbl-box flat"><table id="${id}-table"></table></div>${explain ? `<div class="explain">${explain}</div>` : ""}`;
      container.appendChild(d);
      el(id + "-legend").innerHTML = items.map(i => `<span><i style="background:var(--s${i.color})"></i>${i.name}</span>`).join("") + diamond(netName);
      stackedRows(el(id + "-chart"), Y.map(y => ({ label: YL(y), net: net(y),
        parts: value(y, items[0].k) == null ? [] : items.map(i => ({ v: value(y, i.k) || 0, color: i.color, name: i.name })) })),
        { aria: title, netName, netFmt });
      let h = `<thead><tr><th>來源（pt）</th>${Y.map(y => `<th>${YL(y)}</th>`).join("")}</tr></thead><tbody>`;
      for (const i of items) h += `<tr><td>${sw(i.color)}${i.name}</td>${Y.map(y => { const v = value(y, i.k); return v == null ? `<td class="na">—</td>` : `<td class="num ${v >= 0 ? "pos" : "neg"}">${pt(v)}</td>`; }).join("")}</tr>`;
      el(id + "-table").innerHTML = h + extraRows + "</tbody>";
    }

    if (el("pnl-attr") && C.attrCards) for (const c of C.attrCards) {
      const s = S[c.key], items = itemsOf(c.components, c.names);
      const val = (y, k) => s.attr && s.attr[y] ? (s.attr[y][k] ?? 0) : null;
      const infoKeys = [...new Set(Y.flatMap(y => Object.keys((s.info || {})[y] || {})))];
      const extra = `<tr><td><b>當年報酬</b></td>${Y.map(y => `<td class="num"><b>${has(c.key, y) ? pct(s.years[y].ret) : "—"}</b></td>`).join("")}</tr>` +
        `<tr><td class="na">當年最大回撤</td>${Y.map(y => `<td class="num na">${has(c.key, y) ? pct(s.years[y].mdd) : "—"}</td>`).join("")}</tr>` +
        infoKeys.map(ik => `<tr><td class="na">${ik}</td>${Y.map(y => `<td class="num na">${((s.info || {})[y] || {})[ik] ?? "—"}</td>`).join("")}</tr>`).join("");
      drawCard(el("pnl-attr"), "attr-" + c.key, c.title || s.name, c.sub ?? s.desc, c.explain, items, val,
        y => has(c.key, y) ? s.years[y].ret : null, "當年實際報酬", v => pct(v), extra);
    }

    if (el("pnl-diff") && C.diffCards) for (const c of C.diffCards) {
      const a = S[c.key], b = S[c.ref], items = itemsOf(c.components, c.names);
      const val = (y, k) => a.attr && b.attr && a.attr[y] && b.attr[y] ? (a.attr[y][k] ?? 0) - (b.attr[y][k] ?? 0) : null;
      const net = y => has(c.key, y) && has(c.ref, y) ? a.years[y].ret - b.years[y].ret : null;
      const extra = `<tr><td><b>報酬的差</b></td>${Y.map(y => `<td class="num"><b>${pt(net(y))}</b></td>`).join("")}</tr>` +
        `<tr><td class="na">最大回撤的差（正 = 回撤較小）</td>${Y.map(y => `<td class="num na">${has(c.key, y) && has(c.ref, y) ? pt(a.years[y].mdd - b.years[y].mdd) : "—"}</td>`).join("")}</tr>`;
      drawCard(el("pnl-diff"), `diff-${c.key}-${c.ref}`, c.title || `${a.name} − ${b.name}`, c.sub ?? a.desc, c.explain, items, val,
        net, "報酬的差", v => pt(v) + " pt", extra);
    }
  }

  window.PNL = { render, stackedRows, pct, pt, heat };
})();
