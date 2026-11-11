// 題材地圖：投資人的獲利雷達＋預警牆。從總經環境 → 題材 → 台股真正吃得到價值的公司。
// 無框架、無建置；資料是 site/data/ 的靜態 JSON，題材與個股全文點進去才載入。
const $ = (sel, el = document) => el.querySelector(sel);
const main = $('#main');
const cache = new Map();
let VERSION = '';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const has = v => Array.isArray(v) ? v.length > 0 : v != null && String(v).trim() !== '';
const fmt = (n, d = 2) => n == null || isNaN(n) ? '—' : Number(n).toLocaleString('zh-TW', { maximumFractionDigits: d });
const signed = n => n == null || isNaN(n) ? '—' : `${n > 0 ? '+' : ''}${fmt(n, 0)}`;
const ymd = s => { s = String(s || ''); return /^\d{8}$/.test(s) ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}` : s.slice(0, 10); };
const daysAgo = s => { const t = Date.parse(ymd(s)); return isNaN(t) ? 9999 : (Date.now() - t) / 864e5; };

async function getJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const p = fetch(`data/${path}${VERSION ? `?v=${encodeURIComponent(VERSION)}` : ''}`, { cache: VERSION ? 'default' : 'no-store' })
    .then(r => { if (!r.ok) throw new Error(`${path}：HTTP ${r.status}`); return r.json(); });
  cache.set(path, p);
  p.catch(() => cache.delete(path));
  return p;
}

/* ---------- 小元件 ---------- */
const ST = { official: '官方', news_derived: '新聞', analyst_estimate: '機構估計', llm_inference: 'AI 推論', pending: '待補' };
const st = t => t && ST[t] ? `<span class="st ${t}" title="資料性質">${ST[t]}</span>` : '';
const engineBadge = e => e === 'claude' ? '<span class="engine claude" title="由 Claude 上網查證後解析">Claude</span>'
  : e ? '<span class="engine legacy" title="舊版產線產生，尚未由 Claude 重寫">舊模型</span>' : '';
const heatBars = score => { const n = Math.round((Number(score) || 0) / 20); return `<span class="heat" title="熱度 ${esc(score)}"><i>${[1, 2, 3, 4, 5].map(i => `<b class="${i <= n ? 'on' : ''}"></b>`).join('')}</i><span class="num">${esc(score ?? '—')}</span></span>`; };
const dots = (v, max = 5) => v == null ? '<span class="muted">—</span>' : `<span class="dots" title="${esc(v)} / ${max}">${Array.from({ length: max }, (_, i) => `<b class="${i < Math.round(v) ? 'on' : ''}"></b>`).join('')}</span>`;
const pills = (arr, cls = '') => has(arr) ? `<div class="tags">${arr.map(x => `<span class="pill ${cls}">${esc(x)}</span>`).join('')}</div>` : '';
const list = arr => has(arr) ? `<ul class="clean">${arr.map(x => `<li>${esc(typeof x === 'string' ? x : x.event || x.signal || JSON.stringify(x))}</li>`).join('')}</ul>` : '<p class="muted">—</p>';
const stockChip = (code, name) => `<a class="chip" href="#/s/${esc(code)}"><span class="c">${esc(code)}</span>${esc(name)}</a>`;
const notice = engine => engine && engine !== 'claude' ? '<div class="notice">這份內容來自舊版產線（舊模型），尚未由 Claude 重新查證；市場規模、成長率等數字沒有可核對的出處，請當作參考線索。</div>' : '';
const MACRO = { tailwind: '總經順風', headwind: '總經逆風', mixed: '總經中性' };
const macroBadge = v => v ? `<span class="badge-macro ${v}">${MACRO[v]}</span>` : '';
const flowTxt = (f5, br) => f5 == null ? '' : `<span class="flowtxt ${f5 >= 0 ? 'up' : 'down'}" title="題材內個股近 5 日外資＋投信合計（張）${br ? `；${br[0]}/${br[1]} 檔買超` : ''}">法人5日 ${signed(f5)}</span>`;
const REGIME = { defensive: '防守', neutral: '中性', mixed: '分歧', supportive: '偏多', risk_on: '偏多', risk_off: '防守' };
const vcLevel = v => /高|high/i.test(v || '') ? 'high' : /低|low/i.test(v || '') ? 'low' : /中|mid|medium/i.test(v || '') ? 'mid' : '';
const VC = { high: '吃肉', mid: '分一杯羹', low: '喝湯' };

function spark(hist, w = 240, h = 34) {
  const v = (hist || []).map(x => x[1]).filter(x => x != null);
  if (v.length < 2) return '';
  const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
  const pts = v.map((y, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 3 - (y - lo) / r * (h - 6)).toFixed(1)}`).join(' ');
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
}
function gauge(score) {
  const s = Math.max(0, Math.min(100, Number(score) || 0)), a = Math.PI * (1 - s / 100);
  const x = 32 + 26 * Math.cos(a), y = 34 - 26 * Math.sin(a);
  return `<svg viewBox="0 0 64 40" aria-hidden="true"><path d="M6 34 A26 26 0 0 1 58 34" fill="none" stroke="var(--surface-2)" stroke-width="7" stroke-linecap="round"/>
    <path d="M6 34 A26 26 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="${s < 35 ? 'var(--down)' : s > 65 ? 'var(--up)' : 'var(--gold)'}" stroke-width="7" stroke-linecap="round"/></svg>`;
}
function lineChart(hist, h = 220) {
  const pts = (hist || []).filter(x => x[1] != null);
  if (pts.length < 2) return '<p class="muted">歷史資料不足</p>';
  const w = 900, pad = 30, X = i => pad + i / (pts.length - 1) * (w - pad * 2), Y = v => 10 + (100 - v) / 100 * (h - 40);
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('');
  const ticks = [0, 25, 50, 75, 100].map(v => `<line x1="${pad}" x2="${w - pad}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" stroke-dasharray="${v === 50 ? '0' : '3 4'}"/><text x="4" y="${Y(v) + 4}" font-size="11" fill="var(--muted)">${v}</text>`).join('');
  const labels = [0, Math.floor(pts.length / 2), pts.length - 1].map(i => `<text x="${X(i)}" y="${h - 6}" font-size="11" fill="var(--muted)" text-anchor="middle">${esc(pts[i][0])}</text>`).join('');
  const last = pts[pts.length - 1];
  return `<div class="chart"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="總金線歷史">${ticks}<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.4"/>
    <circle cx="${X(pts.length - 1)}" cy="${Y(last[1])}" r="5" fill="var(--gold)"/><text x="${X(pts.length - 1) - 8}" y="${Y(last[1]) - 10}" font-size="13" font-weight="700" fill="var(--ink)" text-anchor="end">${fmt(last[1], 1)}</text>${labels}</svg></div>`;
}

function radarCard(t) {
  return `<a class="rcard" href="#/t/${esc(t.id)}">
    <div class="top" style="display:flex;justify-content:space-between;gap:8px"><span class="eyebrow">${esc(t.group || '未分類')}</span><span>${engineBadge(t.engine)}</span></div>
    <h3>${esc(t.title)}</h3>
    <div class="liner">${esc(t.one_liner)}</div>
    <div class="mini-facts"><div><span class="k">市場規模${st(t.tam_st)}</span>${esc(t.tam || '—')}</div><div><span class="k">成長率${st(t.cagr_st)}</span>${esc(t.cagr || '—')}</div><div><span class="k">階段</span>${esc(t.stage || '—')}</div></div>
    ${has(t.priority) ? `<div class="prio"><span class="lbl">先看</span>${t.priority.map(s => `<span class="chip"><span class="c">${esc(s.code)}</span>${esc(s.name)}</span>`).join('')}</div>` : ''}
    ${t.why_now ? `<div class="small muted">為什麼是現在：${esc(t.why_now)}</div>` : ''}
    <div class="foot" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">${heatBars(t.heat_score)}${macroBadge(t.macro)}${flowTxt(t.flow5, t.breadth)}${t.warn ? `<span class="pill" style="background:var(--warn-soft);color:var(--warn)">預警 ${t.warn}</span>` : ''}<span class="small muted num">${esc(ymd(t.date))}</span></div>
  </a>`;
}

/* ---------- 頁面：今日（日報＋雷達＋預警牆） ---------- */
const factKpi = (k, v, cls = '') => `<div class="kpi"><div class="k">${k}</div><div class="v num ${cls}">${v}</div></div>`;
async function pageHome() {
  const [meta, themes, macro, reports, gaps, chips] = await Promise.all([getJSON('meta.json'), getJSON('themes.json'), getJSON('macro.json').catch(() => ({})),
    getJSON('reports.json'), getJSON('gap.json').catch(() => []), getJSON('chips.json').catch(() => ({}))]);
  const line = macro.line || {}, reg = macro.regime || {}, r = reports[0], f = r?.facts || {};
  // 雷達只放 Claude 查證過的題材；舊模型題材留在題材庫、標示清楚
  const verified = themes.filter(t => t.engine === 'claude' && !t.cooling);
  const score = t => t.heat_score + (t.macro === 'tailwind' ? 10 : t.macro === 'headwind' ? -10 : 0) + (t.flow5 > 0 ? 5 : t.flow5 < 0 ? -5 : 0);
  const radar = [...verified].sort((a, b) => score(b) - score(a)).slice(0, 6);
  const alerts = [];
  (r?.warnings || []).forEach(w => alerts.push({ lv: '', k: `今日預警 · ${r.date}`, b: w, d: '', href: '#/' }));
  if (reg.regime === 'defensive') alerts.push({ lv: '', k: '總經環境', b: `跨市場環境：${REGIME[reg.regime]}`, d: reg.new_entry_guidance, href: '#/macro' });
  themes.filter(t => t.cooling).slice(0, 4).forEach(t => alerts.push({ lv: '', k: '題材退燒', b: t.title, d: t.cooling, href: `#/t/${t.id}` }));
  verified.filter(t => t.macro === 'headwind' && t.flow5 < 0).slice(0, 3)
    .forEach(t => alerts.push({ lv: 'mid', k: '總經逆風＋法人賣超', b: t.title, d: `題材股近 5 日外資＋投信 ${signed(t.flow5)} 張`, href: `#/t/${t.id}` }));
  gaps.filter(g => g.ai_engine === 'claude' && g.impact_direction === 'bearish').sort((a, b) => String(b.last_update).localeCompare(String(a.last_update))).slice(0, 3)
    .forEach(g => alerts.push({ lv: 'mid', k: `利空落差 · ${g.last_update}`, b: g.target, d: g.gap_space, href: '#/gaps' }));
  const sells = (chips.top_foreign_sells || []).slice(0, 5);
  const flowing = themes.filter(t => t.flow5 != null && t.engine === 'claude').sort((a, b) => b.flow5 - a.flow5);
  const maxF = Math.max(1, ...flowing.map(t => Math.abs(t.flow5)));
  const events = (macro.calendar || []).filter(e => e.importance === 'major').slice(0, 4);
  const c = meta.counts || {};
  const wave = r?.abc_wave_analysis || {}, fu = r?.fundamentals || {};
  const pct = v => `${v > 0 ? '+' : ''}${fmt(v, 2)}%`;
  const e8 = v => `${v > 0 ? '+' : ''}${fmt(v, 1)} 億`;
  return `
  <a class="macro-strip" href="#/macro" style="text-decoration:none">
    <div class="gauge">${gauge(line.score)}<div><div class="small muted">總金線 ${esc(line.as_of || '')}</div><div class="score">${fmt(line.score, 1)}</div></div></div>
    <div><div><b>${esc(line.label || '—')}</b> · 方向 ${esc({ rising: '往上', falling: '往下', flat: '持平' }[line.line_direction] || line.line_direction || '—')} · 5 日 ${line.change_5 != null ? (line.change_5 > 0 ? '+' : '') + fmt(line.change_5, 1) : '—'}
      ${reg.regime ? ` · 環境 <span class="regime ${esc(reg.regime)}">${esc(REGIME[reg.regime] || reg.regime)}</span>` : ''}</div>
      <div class="small muted" style="margin-top:4px">${esc(reg.new_entry_guidance || '')}</div></div>
    <div class="small muted">${events.map(e => `${esc(e.date.slice(5))} ${esc(e.title)}`).join('<br>')}</div>
  </a>
  ${r ? `<section class="panel">
    <div class="eyebrow">${esc(r.date)} 盤後日報 ${engineBadge(r.ai_engine)} <span class="st official">台股數字已核對證交所</span></div>
    <h1 style="margin:8px 0 12px;font-size:clamp(22px,3vw,32px)">${esc(r.title)}</h1>
    <div class="kpis">${factKpi('加權指數', fmt(f.close), f.change >= 0 ? 'up' : 'down')}
      ${f.change != null ? factKpi('漲跌', `${f.change > 0 ? '+' : ''}${fmt(f.change, 2)}（${pct(f.change_pct)}）`, f.change >= 0 ? 'up' : 'down') : ''}
      ${f.turnover_e8 != null ? factKpi('成交金額', `${fmt(f.turnover_e8, 0)} 億`) : ''}
      ${f.foreign_net_e8 != null ? factKpi('外資', e8(f.foreign_net_e8), f.foreign_net_e8 >= 0 ? 'up' : 'down') : ''}
      ${f.inst_net_e8 != null ? factKpi('三大法人', e8(f.inst_net_e8), f.inst_net_e8 >= 0 ? 'up' : 'down') : ''}</div>
    <p class="small muted" style="margin-top:6px">關鍵數字直接取自${esc(f.source || '證交所')}${st('official')}，不經 AI 改寫。</p>
    <p class="lede" style="margin-top:10px">${esc(r.taiex_summary)}</p>
    ${r.operation_advice ? `<p class="quote">${esc(r.operation_advice)}</p><p class="small muted">研究參考，不構成投資建議。</p>` : ''}
  </section>` : `<section class="panel"><div class="eyebrow">盤後日報</div><h2 style="margin-top:6px">今天的日報還在產生</h2><p class="muted">日報由 Claude 依證交所官方數據撰寫，每個台股數字都會自動核對，通過才會發布。</p></section>`}
  <section class="section wall">
    <div class="wall-col"><div class="section-head"><h2><span class="dot" style="background:var(--up)"></span>獲利雷達</h2><a href="#/themes?sort=heat">全部題材 →</a></div>
      <p class="small muted" style="margin-top:-8px">只放 Claude 查證過的題材：熱度高、總經順風、法人有買的優先。每張卡 10 秒看完。</p>
      <div class="grid">${radar.map(radarCard).join('') || '<p class="muted">Claude 正在重寫題材，完成後會出現在這裡。</p>'}</div>
      ${verified.length < 6 ? `<p class="small muted" style="margin-top:8px">目前 Claude 已查證 ${c.themes_claude ?? 0} / ${c.themes ?? 0} 個題材，其餘每天逐步重寫。</p>` : ''}</div>
    <div class="wall-col"><div class="section-head"><h2><span class="dot" style="background:var(--warn)"></span>預警牆</h2></div>
      <div class="grid">${alerts.map(a => `<a class="alert ${a.lv}" href="${a.href}" style="text-decoration:none"><span class="k">${esc(a.k)}</span><b>${esc(a.b)}</b>${a.d ? `<span class="small">${esc(a.d)}</span>` : ''}</a>`).join('') || '<p class="muted">目前沒有預警</p>'}
      ${sells.length ? `<div class="alert mid"><span class="k">外資賣超最多 · ${esc(ymd(chips.date))}</span><div class="tags" style="margin-top:6px">${sells.map(s => stockChip(s.symbol, s.name)).join('')}</div></div>` : ''}</div></div>
  </section>
  ${r && has(r.thematic_categories) ? `<section class="section"><div class="section-head"><h2>今天的主流題材</h2></div><div class="grid g2">${r.thematic_categories.map(t => `<div class="panel"><h3>${esc(t.category_name)}</h3><p class="small">${esc(t.highlight)}</p><div class="list">${(t.stocks || []).map(s => `<div>${stockChip(s.code, s.name)} <span class="small muted">${esc(s.role)}</span></div>`).join('')}</div></div>`).join('')}</div></section>` : ''}
  ${r ? `<section class="section grid g2">
    ${has(r.macro_view) ? `<div class="panel"><div class="section-head"><h2>總經觀點</h2><a href="#/macro">總經數據 →</a></div><p>${esc(r.macro_view)}</p></div>` : ''}
    ${has(r.global_status) ? `<div class="panel"><h2>國際市場</h2><div class="list" style="margin-top:8px">${r.global_status.map(g => `<div><b>${esc(g.name)}</b> <span class="pill">${esc(g.peak)}</span><div class="small">${esc(g.desc)}</div></div>`).join('')}</div></div>` : ''}
    ${has(wave.intro) || has(wave.analysis) ? `<div class="panel"><h2>技術面</h2><p style="margin-top:8px">${esc(wave.intro)}</p>${Array.isArray(wave.analysis) ? list(wave.analysis) : `<p>${esc(wave.analysis)}</p>`}</div>` : ''}
    ${has(fu.summary) ? `<div class="panel"><h2>基本面</h2>${['gdp_growth', 'earnings_growth', 'ai_industry'].filter(k => has(fu[k])).map(k => `<p class="small"><b>${{ gdp_growth: '經濟成長', earnings_growth: '企業獲利', ai_industry: 'AI 產業' }[k]}：</b>${esc(fu[k])}</p>`).join('')}<p>${esc(fu.summary)}</p></div>` : ''}
  </section>` : ''}
  ${flowing.length ? `<section class="section"><div class="section-head"><h2>法人資金正在流向的題材</h2><a href="#/flows">籌碼 →</a></div>
    <p class="small muted">題材內個股近 5 個交易日外資＋投信買賣超合計（張），證交所／櫃買中心官方資料。</p>
    <div class="panel bars">${[...flowing.slice(0, 7), ...(flowing.length > 10 ? flowing.slice(-3).reverse() : [])].map(t => `<div class="bar-row" style="grid-template-columns:minmax(120px,260px) 1fr auto"><a href="#/t/${esc(t.id)}" class="small" style="text-decoration:none">${esc(t.title)}</a><span class="track"><i class="${t.flow5 < 0 ? 'neg' : ''}" style="width:${Math.abs(t.flow5) / maxF * 100}%"></i></span><span class="num small">${signed(t.flow5)}</span></div>`).join('')}</div></section>` : ''}
  ${r && has(r.sources) ? `<section class="section"><h2>日報出處</h2><div class="sources" style="margin-top:10px">${r.sources.map(s => `<div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a> <span class="small muted">${esc(s.published_at || '')}</span></div>`).join('')}</div></section>` : ''}
  <p class="small muted" style="margin-top:24px"><a href="#/reports">歷史日報 →</a></p>`;
}

/* ---------- 頁面：題材庫 ---------- */
async function pageThemes(params) {
  const themes = await getJSON('themes.json');
  const groups = [...new Set(themes.map(t => t.group))].sort();
  const stages = [...new Set(themes.map(t => t.stage).filter(Boolean))];
  const st0 = { q: params.get('q') || '', g: '', s: '', e: '', m: '', sort: params.get('sort') || 'new', n: 48 };
  const html = `
  <h1>題材庫</h1>
  <p class="lede">每個題材都回答六件事：這是什麼、為什麼是現在、市場多大、先看哪三檔、誰真的賺到錢、何時反映到營收。</p>
  <div class="filters">
    <input type="search" id="f-q" placeholder="搜尋題材、標籤或公司" value="${esc(st0.q)}">
    <select id="f-g"><option value="">全部分類</option>${groups.map(g => `<option>${esc(g)}</option>`).join('')}</select>
    <select id="f-s"><option value="">全部階段</option>${stages.map(g => `<option>${esc(g)}</option>`).join('')}</select>
    <select id="f-m"><option value="">總經不限</option><option value="tailwind">總經順風</option><option value="headwind">總經逆風</option></select>
    <select id="f-e"><option value="">全部來源</option><option value="claude">Claude 解析</option><option value="legacy">舊模型</option></select>
    <select id="f-sort"><option value="new">最新</option><option value="heat" ${st0.sort === 'heat' ? 'selected' : ''}>熱度</option><option value="flow">法人買超</option></select>
    <span class="count" id="f-count"></span>
  </div>
  <div class="grid g3" id="t-grid"></div>
  <p style="text-align:center;margin-top:20px"><button class="btn" id="more" hidden>載入更多</button></p>`;
  const draw = () => {
    const q = st0.q.trim().toLowerCase();
    let L = themes.filter(t => (!st0.g || t.group === st0.g) && (!st0.s || t.stage === st0.s) && (!st0.m || t.macro === st0.m)
      && (!st0.e || (st0.e === 'claude' ? t.engine === 'claude' : t.engine !== 'claude'))
      && (!q || `${t.title} ${t.tags.join(' ')} ${t.one_liner} ${(t.priority || []).map(s => s.name + s.code).join(' ')}`.toLowerCase().includes(q)));
    if (st0.sort === 'heat') L.sort((a, b) => b.heat_score - a.heat_score);
    if (st0.sort === 'flow') L.sort((a, b) => (b.flow5 ?? -1e12) - (a.flow5 ?? -1e12));
    $('#t-grid').innerHTML = L.slice(0, st0.n).map(radarCard).join('') || '<div class="empty-state">找不到符合的題材</div>';
    $('#f-count').textContent = `${L.length} 個題材`;
    $('#more').hidden = L.length <= st0.n;
  };
  return { html, mount() {
    const on = (id, k, ev = 'change') => $(id).addEventListener(ev, e => { st0[k] = e.target.value; st0.n = 48; draw(); });
    on('#f-q', 'q', 'input'); on('#f-g', 'g'); on('#f-s', 's'); on('#f-m', 'm'); on('#f-e', 'e'); on('#f-sort', 'sort');
    $('#more').addEventListener('click', () => { st0.n += 48; draw(); });
    draw();
  } };
}

/* ---------- 頁面：單一題材 ---------- */
// 證據欄：系統打開出處網頁、確認有提到公司與題材的，才標「出處已核對」
const evidenceCell = s => has(s.evidence_verified) ? `<div class="sub"><span class="st official">出處已核對</span><br>${s.evidence_verified.slice(0, 2).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">出處${i + 1}</a>`).join(' ')}</div>`
  : has(s.evidence_urls) ? `<div class="sub"><span class="st pending">出處待核對</span><br>${s.evidence_urls.slice(0, 2).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">連結${i + 1}</a>`).join(' ')}${s.evidence_note ? `<br>${esc(s.evidence_note)}` : ''}</div>` : '<div class="sub">產業鏈推論</div>';
const CMP_ROWS = [['受惠位置', 'role'], ['放量時程', 'timeframe'], ['題材純度', 'pure_level', 'dots'], ['技術壁壘', 'barrier_level', 'dots'], ['吃肉程度', 'value_capture_score', 'dots'],
  ['營收含金量', 'ai_revenue_exposure'], ['毛利率彈性', 'gross_margin_impact'], ['定價權', 'pricing_power'], ['客戶黏著', 'switching_cost'], ['替代風險', 'substitution_risk'],
  ['營收能見度', 'revenue_visibility'], ['客戶集中度', 'customer_concentration'], ['投資亮點', 'pros'], ['風險提醒', 'cons'], ['股價催化／驗證事件', 'catalyst']];

async function pageTheme(id) {
  const t = await getJSON(`themes/${id}.json`);
  const S = [];
  const sec = (key, title, body, sub = '') => { if (body) S.push({ key, title, html: `<section id="s-${key}"><h2>${title}${sub ? `<small>${sub}</small>` : ''}</h2>${body}</section>` }); };
  const names = Object.fromEntries((t.stocks || []).map(s => [s.code, s.name]));
  // 先看三檔：Claude 排的優先股（出處已核對）優先，不足三檔用核心、吃肉程度高、非跟風的補
  const prio = (() => { const p = t.stocks.filter(s => s.priority).sort((a, b) => a.priority - b.priority);
    const rest = t.stocks.filter(s => !s.priority && !s.follower && s.tier === 'core').sort((a, b) => (b.value_capture_score || 0) - (a.value_capture_score || 0));
    return [...p, ...rest].slice(0, 3); })();

  if (has(t.stocks)) sec('stocks', '概念股篩選', `
    <div class="filters" style="margin:0 0 12px"><div class="seg" id="tier-seg"><button class="on" data-v="">全部</button><button data-v="core">核心</button><button data-v="extended">延伸</button><button data-v="follower">跟風</button></div>
      <select id="st-sort"><option value="">預設排序</option><option value="value_capture_score">吃肉程度</option><option value="pure_level">題材純度</option><option value="barrier_level">技術壁壘</option></select>
      <span class="small muted">勾選兩檔做 PK 比較</span></div>
    <div class="table-wrap"><table><thead><tr><th></th><th>股票</th><th>受惠位置、理由與放量時程</th><th>評分</th><th>證據</th></tr></thead><tbody id="st-body"></tbody></table></div>
    <div id="cmp"></div>
    <p class="small muted" style="margin-top:8px">核心＝系統已打開出處網頁、確認同時提到這家公司與這個題材；延伸＝依產業鏈推論或出處待核對；跟風＝相關營收很小、主要靠題材想像。代號與名稱都已比對證交所／櫃買中心官方代號表。純度、壁壘、吃肉 0–5。</p>`, `${t.stocks.length} 檔`);
  const fl = t.flow;
  sec('flow', '資金火勢', `${fl ? `<div class="kpis"><div class="kpi"><div class="k">近 5 日外資＋投信（張）</div><div class="v num ${fl.f5 >= 0 ? 'up' : 'down'}">${signed(fl.f5)}</div></div>
      <div class="kpi"><div class="k">最近一日（張）</div><div class="v num ${fl.f1 >= 0 ? 'up' : 'down'}">${signed(fl.f1)}</div></div><div class="kpi"><div class="k">近 5 日買超家數</div><div class="v num">${fl.buy} / ${fl.n}</div></div></div>
      <p class="small muted" style="margin-top:8px">${esc(ymd(t.flow_dates?.[0]))} 至 ${esc(ymd(t.flow_dates?.[t.flow_dates.length - 1]))}，證交所／櫃買中心官方資料${st('official')}。主要貢獻：${(fl.lead || []).map(([c, v]) => `${esc(names[c] || c)} ${signed(v)}`).join('、')}</p>`
      : '<p class="muted">這個題材的個股還沒有法人資料。</p>'}
    ${has(t.capital_flow) ? `<h3 style="margin:16px 0 10px">資金輪動推演 ${st('llm_inference')}</h3><div class="flow">${t.capital_flow.map(f => `<div class="step"><div><div class="small muted mono">${esc(f.timeframe)}</div><h3>${esc(f.phase)}</h3><p>${esc(f.focus)}</p><p class="small muted">${esc(f.logic)}</p>${pills(f.beneficiary_groups)}</div></div>`).join('')}</div>` : ''}`);
  if (has(t.structure_layers)) sec('chain', '價值鏈：誰賺得最多', `<div class="chain">${t.structure_layers.map((l, i) => { const vc = vcLevel(l.value_capture || l.pricing_power); return `<div class="layer vc-${vc || 'mid'}"><div class="rail"><span class="dot">${i + 1}</span><span class="stem"></span></div><div class="body">
      <h3>${esc(l.name)} ${vc ? `<span class="vc ${vc}">${VC[vc]}</span>` : ''}</h3>${l.position ? `<div class="pos">${esc(l.position)}</div>` : ''}<p>${esc(l.summary)}</p>${has(l.key_points) ? list(l.key_points) : ''}
      <div class="kv">${(l.beneficiaries || []).map(b => `<span class="chip">${esc(b)}</span>`).join('')}${l.pricing_power ? `<span class="pill gold">定價權 ${esc(l.pricing_power)}</span>` : ''}${l.entry_barrier ? `<span class="pill">門檻：${esc(l.entry_barrier)}</span>` : ''}</div>
      ${l.value_capture || l.margin_profile ? `<p class="small muted" style="margin-top:6px">${l.value_capture ? `價值捕獲：${esc(l.value_capture)}` : ''}${l.margin_profile ? `　毛利：${esc(l.margin_profile)}` : ''}${l.leader_type ? `　贏家類型：${esc(l.leader_type)}` : ''}</p>` : ''}</div></div>`; }).join('')}</div>`, '金色＝吃肉、藍色＝分一杯羹、灰色＝喝湯');
  if (has(t.timeline_phases)) sec('timeline', '投資節奏', `<div class="timeline">${t.timeline_phases.map(p => `<div class="phase ${p.is_current ? 'current' : ''}"><div class="tf">${esc(p.timeframe)}</div><h3>${esc(p.phase)}</h3>
      ${p.investment_phase ? `<div class="small" style="color:var(--gold);font-weight:700">${esc(p.investment_phase)}</div>` : ''}<p>${esc(p.summary)}</p>
      ${p.revenue_meaning ? `<p class="small">營收意義：${esc(p.revenue_meaning)}</p>` : ''}${p.watch_metric ? `<p class="small muted">觀察：${esc(p.watch_metric)}</p>` : ''}${has(p.winners) ? pills(p.winners) : ''}</div>`).join('')}</div>`, t.investment_phase ? esc(t.investment_phase) : '');
  const mf = t.macro_fit;
  if (mf && has(mf.rows)) sec('macro', '總經順逆風', `<div class="panel">${mf.rows.map(r => `<div class="mrow"><b>${esc(r.label)}</b><span class="small">${esc(r.why)}<span class="muted">（這個指標${r.direction === 'positive' ? '上升' : '下降'}對題材有利）</span></span>
      <span style="text-align:right"><span class="trend ${esc(r.trend)}">${esc(r.text)}</span><br><span class="badge-macro ${r.effect === 'neutral' ? 'mixed' : r.effect}">${{ tailwind: '順風', headwind: '逆風', neutral: '中性' }[r.effect]}</span> <span class="small muted">${esc(r.date)}</span></span></div>`).join('')}</div>
      <p class="small muted" style="margin-top:8px">敏感方向由 Claude 判斷${st('llm_inference')}；指標目前方向來自興櫃總經戰情室的官方數據${st('official')}。<a href="#/macro">看總經 →</a></p>`, macroBadge(mf.verdict));
  if (has(t.warnings) || has(t.risks) || has(t.watch_signals) || has(t.key_bottleneck)) sec('warn', '預警與驗證節點', `
      ${has(t.warnings) ? `<div class="grid" style="margin-bottom:14px">${t.warnings.map(w => `<div class="alert ${/高/.test(w.level) ? '' : 'mid'}"><span class="k">預警 · ${esc(w.level || '')}</span><b>${esc(w.signal)}</b><span class="small">${esc(w.detail)}</span></div>`).join('')}</div>` : ''}
      <div class="cols2"><div class="panel"><h3>主要風險</h3>${list(t.risks)}${has(t.key_bottleneck) ? `<h3 style="margin-top:12px">關鍵瓶頸</h3>${list(t.key_bottleneck)}` : ''}</div>
      <div class="panel"><h3>接下來要看的驗證節點</h3>${list(t.watch_signals)}${has(t.primary_value_capture) ? `<h3 style="margin-top:12px">價值被誰拿走</h3>${list(t.primary_value_capture)}` : ''}</div></div>`);
  if (has(t.tech_lessons) || has(t.concepts)) sec('logic', '產業投資邏輯', [...(t.tech_lessons || []), ...(t.concepts || [])].map((l, i) => `<details class="lesson" ${i === 0 ? 'open' : ''}><summary><span>${esc(l.title)}${l.subtitle ? ` <span class="small muted" style="font-weight:400">${esc(l.subtitle)}</span>` : ''}</span></summary><div class="in"><dl>
      ${l.problem ? `<dt>要解決的問題</dt><dd>${esc(l.problem)}</dd>` : ''}${l.mechanism ? `<dt>機制</dt><dd>${esc(l.mechanism)}</dd>` : ''}${l.why_now ? `<dt>為什麼是現在</dt><dd>${esc(l.why_now)}</dd>` : ''}${l.desc ? `<dt>說明</dt><dd>${esc(l.desc)}</dd>` : ''}</dl></div></details>`).join(''));
  if (has(t.sources) || has(t.trigger_events)) sec('sources', '觸發事件與出處', `${has(t.trigger_events) ? `<div class="list panel" style="margin-bottom:14px">${t.trigger_events.map(e => `<div><span class="small muted num">${esc(e.date || '')}</span> ${e.source_url ? `<a href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.event)}</a>` : esc(e.event)}</div>`).join('')}</div>` : ''}
      <div class="sources">${(t.sources || []).map(s => `<div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a> <span class="small muted">${esc(s.source_name)} ${esc(s.published_at)}</span></div>`).join('')}</div>`, has(t.sources) ? `${t.sources.length} 筆` : '');

  const html = `
  <div class="crumbs"><a href="#/themes">題材庫</a> / ${esc(t.group || '未分類')}</div>
  <div class="hero2">
    <div>
      <div class="t-meta">${engineBadge(t.ai_engine)}${heatBars(t.heat_score)}${t.heat ? `<span class="pill gold">${esc(t.heat)}</span>` : ''}${macroBadge(mf?.verdict)}${fl ? flowTxt(fl.f5, [fl.buy, fl.n]) : ''}<span class="small muted">更新 ${esc(String(t.updated_at || t.date).slice(0, 16).replace('T', ' '))}</span></div>
      <h1 style="margin:10px 0">${esc(t.title)}</h1>
      ${has(t.one_liner) ? `<p class="lede" style="font-weight:700;color:var(--ink)">${esc(t.one_liner)}</p>` : ''}
      ${prio.length ? `<div class="top3">${prio.map((s, i) => `<a href="#/s/${esc(s.code)}"><span class="n">先看 #${i + 1} · ${esc(s.code)}</span><b>${esc(s.name)}</b><span class="r clamp2">${esc(s.role)}</span></a>`).join('')}</div>` : ''}
      <div class="qa"><div><span class="k">這是什麼</span><p class="clamp" data-clamp>${esc(t.summary)}</p></div>
        ${has(t.why_now) ? `<div><span class="k">為什麼是現在</span><p class="clamp" data-clamp>${esc(t.why_now)}</p></div>` : ''}
        ${has(t.thesis) ? `<div><span class="k">投資論點</span><p class="clamp" data-clamp>${esc(t.thesis)}</p></div>` : ''}</div>
      ${t.cooling ? `<div class="banner cool"><b>退燒預警（${esc(t.cooling.date)}）</b>：${esc(t.cooling.reason)}</div>` : ''}
      ${notice(t.ai_engine)}
    </div>
    <div class="side">
      <div class="fact"><div class="k">市場有多大（TAM）${st(t.market_size_tam_source_type)}</div><div class="v">${esc(t.market_size_tam || '—')}</div>${t.market_size_tam_source ? `<div class="src">${esc(t.market_size_tam_source)}</div>` : ''}</div>
      <div class="fact"><div class="k">年複合成長（CAGR）${st(t.market_cagr_source_type)}</div><div class="v">${esc(t.market_cagr || '—')}</div>${t.market_cagr_source ? `<div class="src">${esc(t.market_cagr_source)}</div>` : ''}</div>
      <div class="fact"><div class="k">題材階段 · 受惠期間</div><div class="v">${esc(t.theme_stage || '—')}${t.period ? ` · ${esc(t.period)}` : ''}</div>${t.investment_phase ? `<div class="src">${esc(t.investment_phase)}</div>` : ''}</div>
      ${has(t.key_bottleneck) ? `<div class="fact"><div class="k">核心瓶頸</div><div class="small">${esc(t.key_bottleneck.join('；'))}</div></div>` : ''}
      ${has(t.primary_value_capture) ? `<div class="fact"><div class="k">最大價值捕捉點</div><div class="small">${esc(t.primary_value_capture.join('；'))}</div></div>` : ''}
      <div class="fact"><div class="k">證據信心</div><div class="v">${esc(t.evidence_confidence || '—')}</div></div>
    </div>
  </div>
  <div class="t-body">
    <nav class="toc" aria-label="本頁段落">${S.map(s => `<a href="#/t/${esc(id)}" data-jump="s-${s.key}">${s.title}</a>`).join('')}</nav>
    <div>${S.map(s => s.html).join('')}</div>
  </div>`;

  return { html, mount() {
    main.querySelectorAll('[data-clamp]').forEach(p => { if (p.scrollHeight > p.clientHeight + 4) { const b = document.createElement('button'); b.className = 'more-btn'; b.textContent = '展開'; b.onclick = () => { const open = p.classList.toggle('open'); b.textContent = open ? '收合' : '展開'; }; p.after(b); } });
    if (!has(t.stocks)) return;
    const state = { tier: '', sort: '', pick: [] };
    const draw = () => {
      let L = t.stocks.filter(s => !state.tier || (state.tier === 'follower' ? s.follower : s.tier === state.tier && !s.follower));
      L = state.sort ? [...L].sort((a, b) => (b[state.sort] || 0) - (a[state.sort] || 0))
        : [...L].sort((a, b) => (a.priority || 9) - (b.priority || 9) || (a.follower ? 1 : 0) - (b.follower ? 1 : 0) || (a.tier === 'core' ? 0 : 1) - (b.tier === 'core' ? 0 : 1) || (b.value_capture_score || 0) - (a.value_capture_score || 0));
      $('#st-body').innerHTML = L.map(s => `<tr class="${s.follower ? 'follower' : ''}"><td><input type="checkbox" data-c="${esc(s.code)}" ${state.pick.includes(s.code) ? 'checked' : ''} aria-label="比較 ${esc(s.name)}"></td>
        <td>${stockChip(s.code, s.name)}${s.priority ? `<div class="sub" style="color:var(--accent);font-weight:700">先看 #${s.priority}</div>` : ''}<div class="sub">${esc(s.sector)}</div></td>
        <td style="min-width:260px"><b>${esc(s.role)}</b><div class="sub">${esc(s.desc)}</div>${s.follower ? `<div class="sub" style="color:var(--warn)">跟風：${esc(s.follower_reason || '相關營收有限')}</div>` : ''}${s.timeframe ? `<div class="sub"><b>放量：</b>${esc(s.timeframe)}</div>` : ''}${s.catalyst ? `<div class="sub"><b>催化：</b>${esc(s.catalyst)}</div>` : ''}</td>
        <td class="scores"><div><span>純度</span>${dots(s.pure_level)}</div><div><span>壁壘</span>${dots(s.barrier_level)}</div><div><span>吃肉</span>${dots(s.value_capture_score)}</div></td>
        <td>${s.tier === 'core' ? '<span class="pill accent">核心</span>' : '<span class="pill">延伸</span>'}${evidenceCell(s)}</td></tr>`).join('');
      const P = state.pick.map(c => t.stocks.find(s => s.code === c)).filter(Boolean);
      $('#cmp').innerHTML = P.length === 2 ? `<div class="cmp"><div class="section-head"><h3>PK：${esc(P[0].name)} vs ${esc(P[1].name)}</h3><button class="btn" id="cmp-x">關閉</button></div><div class="table-wrap"><table><tbody>
        ${CMP_ROWS.map(([k, f, how]) => `<tr><td>${k}</td>${P.map(s => `<td>${how === 'dots' ? dots(s[f]) : esc(s[f] || '—')}${f === 'ai_revenue_exposure' ? st(s.ai_revenue_exposure_source_type) : ''}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>` : '';
      $('#cmp-x')?.addEventListener('click', () => { state.pick = []; draw(); });
    };
    $('#tier-seg').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; state.tier = b.dataset.v; [...$('#tier-seg').children].forEach(x => x.classList.toggle('on', x === b)); draw(); });
    $('#st-sort').addEventListener('change', e => { state.sort = e.target.value; draw(); });
    $('#st-body').addEventListener('change', e => { const c = e.target.dataset.c; if (!c) return; state.pick = e.target.checked ? [...state.pick, c].slice(-2) : state.pick.filter(x => x !== c); draw(); });
    draw();
  } };
}

/* ---------- 頁面：總經 ---------- */
const GROUPS = [['market', '市場與利率、油價、匯率'], ['credit_liquidity', '信用與流動性'], ['policy', '貨幣政策'], ['inflation', '通膨'], ['growth_jobs', '成長與就業'], ['taiwan', '台灣市場']];
async function pageMacro() {
  const m = await getJSON('macro.json');
  const line = m.line || {}, reg = m.regime || {};
  if (!line.as_of) return '<div class="empty-state">總經資料暫時讀不到</div>';
  const ind = Object.values(m.indicators || {});
  const val = v => v.value == null ? '—' : Math.abs(v.value) >= 1e8 ? `${fmt(v.value / 1e8, 1)} 億` : fmt(v.value);
  const view = m.ai_view || {};
  return `<h1>總經環境</h1><p class="lede">先看市場環境，再決定題材要積極還是保守。資料來自興櫃總經戰情室（FRED、證交所、BLS、FOMC 官方資料），每天更新。</p>
  <div class="grid g2" style="margin-top:18px">
    <div class="panel"><div class="eyebrow">總金線 · ${esc(line.as_of)}</div>
      <div class="gauge" style="margin:8px 0">${gauge(line.score)}<div><div class="score">${fmt(line.score, 1)}</div><div class="small muted">${esc(line.label)} · 方向 ${esc({ rising: '往上', falling: '往下', flat: '持平' }[line.line_direction] || line.line_direction)} · 1 日 ${fmt(line.change_1, 1)} · 5 日 ${fmt(line.change_5, 1)}</div></div></div>
      <p class="small muted">0–100 的風險環境分數，不是上漲機率。</p>
      <div class="bars" style="margin-top:10px">${Object.entries(line.components || {}).map(([k, c]) => `<div><div class="bar-row" style="grid-template-columns:90px 1fr auto"><span class="small">${{ credit: '信用', equity: '股市', taiwan_fx: '台幣', volatility: '波動' }[k] || esc(k)}</span><span class="track"><i style="width:${c.score || 0}%;background:var(--accent)"></i></span><span class="num small">${fmt(c.score, 0)}</span></div><div class="small muted">${esc(c.description)}</div></div>`).join('')}</div></div>
    <div class="panel"><div class="eyebrow">跨市場環境判定</div><p style="margin:8px 0"><span class="regime ${esc(reg.regime)}">${esc(REGIME[reg.regime] || reg.regime || '—')}</span> <span class="small muted">涵蓋 ${reg.coverage?.usable ?? '—'}/${reg.coverage?.expected ?? '—'} 項</span></p>
      <p><b>新增曝險：</b>${esc(reg.new_entry_guidance || '—')}</p><p class="small"><b>既有持股：</b>${esc(reg.holding_guidance || '—')}</p>
      <div class="list">${Object.entries(reg.signals || {}).map(([k, s]) => `<div><b>${{ equities: '股市', rates: '利率', fx: '匯率', oil: '油價', hong_kong: '香港資金' }[k] || esc(k)}</b> <span class="pill">${esc({ pressure: '承壓', mixed: '分歧', unknown: '資料不足', shock_review: '急變待查', supportive: '支撐', stable: '穩定', easing: '寬鬆', tightening: '收緊' }[s.state] || s.state)}</span><div class="small muted">${esc(s.reason)}</div></div>`).join('')}</div></div>
  </div>
  <section class="section"><h2>總金線走勢</h2><div class="panel" style="margin-top:12px">${lineChart(line.history)}<p class="small muted">${(line.limitations || []).map(esc).join('<br>')}</p></div></section>
  ${GROUPS.map(([g, title]) => { const L = ind.filter(v => v.group === g); return L.length ? `<section class="section"><h2>${title}</h2><div class="ind-grid" style="margin-top:12px">${L.map(v => `<div class="ind"><div class="k">${esc(v.label)}</div><div class="v">${val(v)}</div>
    <span class="trend ${esc(v.trend)} small">${esc(v.trend_text || '')}</span>${spark(v.history)}<div class="d">資料日 ${esc(v.date || '—')} ${v.source_url ? `· <a href="${esc(v.source_url)}" target="_blank" rel="noopener">出處</a>` : ''}</div>${v.meaning ? `<div class="d">${esc(v.meaning)}</div>` : ''}</div>`).join('')}</div></section>` : ''; }).join('')}
  ${has(m.calendar) ? `<section class="section"><h2>未來 30 天的總經事件</h2><div class="list panel" style="margin-top:12px">${m.calendar.map(e => `<div><span class="num small muted">${esc((e.start_at || e.date || '').slice(0, 16).replace('T', ' '))}</span> <b>${esc(e.title)}</b> ${e.importance === 'major' ? '<span class="pill gold">重要</span>' : ''} <span class="small muted">${esc(e.period || '')}</span></div>`).join('')}</div></section>` : ''}
  ${has(view.analysis) ? `<section class="section"><h2>總經觀點 ${engineBadge(view.ai_engine)}</h2><div class="panel" style="margin-top:12px"><p class="small muted">${esc(view.date)}</p><p>${esc(view.analysis)}</p></div></section>` : ''}`;
}

/* ---------- 頁面：個股 ---------- */
async function pageStocks(params) {
  const idx = await getJSON('stocks.json');
  const all = Object.entries(idx).map(([code, s]) => ({ code, ...s }));
  const st0 = { q: params.get('q') || '', m: '', n: 80 };
  const html = `<h1>個股</h1><p class="lede">搜尋任何上市櫃公司；預設依「出現在幾個題材」排序，越多代表越多題材都繞不開它。</p>
  <div class="filters"><input type="search" id="s-q" placeholder="代號或公司名稱" value="${esc(st0.q)}">
    <select id="s-m"><option value="">上市＋上櫃</option><option value="TWSE">上市</option><option value="TPEX">上櫃</option></select><span class="count" id="s-count"></span></div>
  <div class="table-wrap"><table><thead><tr><th>股票</th><th>產業</th><th class="r">題材數</th><th>公司簡介</th></tr></thead><tbody id="s-body"></tbody></table></div>
  <p style="text-align:center;margin-top:20px"><button class="btn" id="s-more" hidden>載入更多</button></p>`;
  const draw = () => {
    const q = st0.q.trim().toLowerCase();
    const L = all.filter(s => (!st0.m || s.m === st0.m) && (!q || s.code.startsWith(q) || s.n.toLowerCase().includes(q))).sort((a, b) => b.t - a.t || a.code.localeCompare(b.code));
    $('#s-body').innerHTML = L.slice(0, st0.n).map(s => `<tr><td>${stockChip(s.code, s.n)}</td><td>${esc(s.i || '—')}</td><td class="r num">${s.t || ''}</td><td>${s.w ? engineBadge(s.e) : '<span class="small muted">未建檔</span>'}</td></tr>`).join('');
    $('#s-count').textContent = `${L.length} 檔`;
    $('#s-more').hidden = L.length <= st0.n;
  };
  return { html, mount() {
    $('#s-q').addEventListener('input', e => { st0.q = e.target.value; st0.n = 80; draw(); });
    $('#s-m').addEventListener('change', e => { st0.m = e.target.value; draw(); });
    $('#s-more').addEventListener('click', () => { st0.n += 80; draw(); });
    draw();
  } };
}

async function pageStock(code) {
  const [idx, links, themes, series, gaps] = await Promise.all([getJSON('stocks.json'), getJSON('stock_links.json').catch(() => ({})), getJSON('themes.json'),
    getJSON('chips_series.json').catch(() => ({})), getJSON('gap.json').catch(() => [])]);
  const s = idx[code];
  if (!s) return `<div class="empty-state">找不到代號 ${esc(code)}</div>`;
  const shard = s.w ? await getJSON(`stocks/${code.slice(0, 2)}.json`).catch(() => ({})) : {};
  const w = shard[code] || {}, d = w.details || {};
  const byId = Object.fromEntries(themes.map(t => [t.id, t]));
  const my = (links[code] || []).map(([tid, role, tier, prio]) => ({ t: byId[tid], role, tier, prio })).filter(x => x.t).sort((a, b) => (a.prio || 9) - (b.prio || 9) || (a.tier === 'core' ? 0 : 1) - (b.tier === 'core' ? 0 : 1));
  const ser = series.series?.[code] || [], dates = series.dates || [];
  const maxAbs = Math.max(1, ...ser.map(r => Math.abs((r[0] || 0) + (r[1] || 0))));
  const myGaps = gaps.filter(g => (g.concept_stocks || []).some(x => String(x).startsWith(code)));
  const kpi = (k, v) => has(v) ? `<div class="kpi"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>` : '';
  return `
  <div class="crumbs"><a href="#/stocks">個股</a> / ${esc(s.i || '')}</div>
  <div class="s-head"><h1>${esc(s.n)}</h1><span class="code">${esc(code)}</span><span class="pill">${s.m === 'TWSE' ? '上市' : s.m === 'TPEX' ? '上櫃' : esc(s.m)}</span>${s.i ? `<span class="pill">${esc(s.i)}</span>` : ''}${engineBadge(w.ai_engine)}</div>
  ${has(w.summary) ? `<p class="lede" style="margin-top:12px">${esc(w.summary)}</p>` : '<p class="muted">這檔還沒有公司簡介。</p>'}
  ${has(w.products) ? `<div class="tags" style="margin:10px 0 4px">${w.products.map(p => `<span class="chip">${esc(p)}</span>`).join('')}</div>` : ''}
  ${has(w.revenue_mix) ? `<p class="small">營收結構：${esc(w.revenue_mix)}${st(w.revenue_mix_source_type)}</p>` : ''}
  ${notice(w.ai_engine)}
  <div class="kpis" style="margin-top:16px">${kpi('題材純度', d.pure_level ?? d.pureLevel)}${kpi('技術壁壘', d.barrier_level ?? d.barrierLevel)}${kpi('定價權', d.pricing_power)}${kpi('題材營收含金量', d.ai_revenue_exposure)}${kpi('放量時程', d.commercialization_phase)}${kpi('替代風險', d.substitution_risk)}</div>
  ${has(d.pros) || has(d.cons) || has(d.catalyst) ? `<div class="cols2" style="margin-top:16px"><div class="panel"><h3>投資亮點</h3><p>${esc(d.pros || '—')}</p><h3>股價催化／驗證事件</h3><p>${esc(d.catalyst || '—')}</p></div><div class="panel"><h3>風險提醒</h3><p>${esc(d.cons || '—')}</p></div></div>` : ''}
  <section class="section"><div class="section-head"><h2>在這些題材裡的位置</h2><span class="small muted">${my.length} 個題材</span></div>
    ${my.length ? `<div class="list panel">${my.map(x => `<div><a href="#/t/${esc(x.t.id)}"><b>${esc(x.t.title)}</b></a> ${x.prio ? `<span class="pill accent">先看 #${x.prio}</span>` : ''}${x.tier === 'core' ? '<span class="pill accent">核心</span>' : '<span class="pill">延伸</span>'} ${macroBadge(x.t.macro)} ${engineBadge(x.t.engine)}<div class="small muted">${esc(x.role)}</div></div>`).join('')}</div>` : '<p class="muted">目前沒有題材收錄這檔。</p>'}</section>
  <section class="section"><div class="section-head"><h2>法人近 ${dates.length} 個交易日</h2><span class="small muted">外資＋投信買賣超（張），官方資料</span></div>
    ${ser.length ? `<div class="panel"><div class="spark" style="--n:${ser.length}">${ser.map((r, i) => { const v = (r[0] || 0) + (r[1] || 0); const h = Math.abs(v) / maxAbs * 44; return `<i title="${esc(ymd(dates[i]))}：外資 ${signed(r[0])}、投信 ${signed(r[1])}" style="grid-row:1;grid-column:${i + 1};height:${Math.max(2, h)}px;background:var(${v >= 0 ? '--up' : '--down'});align-self:${v >= 0 ? 'end' : 'start'};margin-${v >= 0 ? 'bottom' : 'top'}:45px"></i>`; }).join('')}<span class="spark-axis"></span></div>
      <p class="small muted">${esc(ymd(dates[0]))} 至 ${esc(ymd(dates[dates.length - 1]))}；最近一日外資 ${signed(ser[ser.length - 1][0])}、投信 ${signed(ser[ser.length - 1][1])}</p></div>` : '<p class="muted">只有收錄在題材裡的股票會整理法人序列。</p>'}</section>
  ${myGaps.length ? `<section class="section"><div class="section-head"><h2>相關預期落差</h2></div><div class="grid">${myGaps.slice(0, 6).map(gapCard).join('')}</div></section>` : ''}
  ${has(w.sources) ? `<section class="section"><h2>出處</h2><div class="sources" style="margin-top:10px">${w.sources.map(x => `<div><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.url)}</a> <span class="small muted">${esc(x.published_at || '')}</span></div>`).join('')}</div></section>` : ''}
  <p class="small muted" style="margin-top:28px">外部看盤：<a href="https://tw.stock.yahoo.com/quote/${esc(code)}" target="_blank" rel="noopener">Yahoo 股市</a> · <a href="https://www.tradingview.com/chart/?symbol=${s.m === 'TPEX' ? 'TPEX' : 'TWSE'}%3A${esc(code)}" target="_blank" rel="noopener">TradingView</a></p>`;
}

/* ---------- 頁面：籌碼 ---------- */
async function pageFlows() {
  const [c, themes] = await Promise.all([getJSON('chips.json'), getJSON('themes.json')]);
  const table = (title, rows, note = '') => has(rows) ? `<div class="panel"><h3>${title}</h3>${note ? `<p class="small muted">${note}</p>` : ''}<div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>股票</th><th class="r">外資</th><th class="r">投信</th><th class="r">合計</th><th class="r">占股本</th></tr></thead><tbody>
    ${rows.slice(0, 15).map(r => `<tr><td>${stockChip(r.symbol, r.name)}</td><td class="r num ${r.foreign_net >= 0 ? 'up' : 'down'}">${signed(r.foreign_net)}</td><td class="r num ${r.trust_net >= 0 ? 'up' : 'down'}">${signed(r.trust_net)}</td><td class="r num">${signed(r.total_net)}</td><td class="r num small">${r.foreign_ratio != null ? fmt(r.foreign_ratio, 3) + '%' : '—'}</td></tr>`).join('')}</tbody></table></div></div>` : '';
  const flowing = themes.filter(t => t.flow5 != null && daysAgo(t.date) < 120).sort((a, b) => b.flow5 - a.flow5);
  return `<h1>法人籌碼</h1><p class="lede">${esc(ymd(c.date))} 三大法人買賣超（單位：張），證交所、櫃買中心官方資料。占股本＝當日買賣超 ÷ 流通張數。</p>
  <section class="section"><h2>題材資金排行（近 5 日外資＋投信）</h2><div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>題材</th><th class="r">5 日合計</th><th class="r">買超家數</th><th>總經</th></tr></thead><tbody>
    ${[...flowing.slice(0, 12), ...flowing.slice(-6).reverse()].map(t => `<tr><td><a href="#/t/${esc(t.id)}">${esc(t.title)}</a></td><td class="r num ${t.flow5 >= 0 ? 'up' : 'down'}">${signed(t.flow5)}</td><td class="r num">${t.breadth ? `${t.breadth[0]}/${t.breadth[1]}` : ''}</td><td>${macroBadge(t.macro)}</td></tr>`).join('')}</tbody></table></div></section>
  <div class="grid g2 section">
    ${has(c.cohort_themes) ? `<div class="panel"><h3>外資投信同步買超的產業</h3><div class="list">${c.cohort_themes.slice(0, 8).map(g => `<div><b>${esc(g.theme_name)}</b> <span class="small muted">${g.count} 檔 · ${fmt(g.total_net_buy, 0)} 張</span><div class="tags" style="margin-top:4px">${(g.stocks || []).slice(0, 6).map(s => stockChip(s.symbol, s.name)).join('')}</div></div>`).join('')}</div></div>` : ''}
    ${table('外資買超', c.top_foreign_buys)}${table('外資賣超', c.top_foreign_sells)}${table('投信買超', c.top_trust_buys)}
    ${table('外資爆量', c.foreign_surges, '買超超過前五日平均 1.5 倍')}${table('投信爆量', c.trust_surges, '買超超過前五日平均 1.5 倍')}
  </div>`;
}

/* ---------- 頁面：預期落差 ---------- */
const gapCard = g => `<div class="panel gap">
  <div class="small muted">${esc(g.last_update)} · ${esc(g.category)} ${g.impact_direction === 'bearish' ? '<span class="pill down">利空</span>' : g.impact_direction === 'neutral' ? '<span class="pill">中性</span>' : '<span class="pill up">利多</span>'} ${g.dream_rating ? `<span class="pill gold">${esc(g.dream_rating)}</span>` : ''} ${engineBadge(g.ai_engine)}</div>
  <h3>${esc(g.target)}</h3>
  <div class="trio"><div><span class="k">市場原本預期</span>${esc(g.market_expect)}</div><div><span class="k">實際數據</span>${esc(g.real_data)}</div><div><span class="k">落差代表什麼</span>${esc(g.gap_space)}</div></div>
  ${has(g.concept_stocks) ? `<div class="tags">${g.concept_stocks.map(x => { const [c, ...n] = String(x).split(' '); return /^\d{4}/.test(c) ? stockChip(c, n.join(' ')) : `<span class="chip">${esc(x)}</span>`; }).join('')}</div>` : ''}
  ${g.source ? `<div class="small muted">出處：${g.source_url ? `<a href="${esc(g.source_url)}" target="_blank" rel="noopener">${esc(g.source)}</a>` : esc(g.source)}</div>` : ''}
</div>`;

async function pageGaps() {
  const gaps = (await getJSON('gap.json')).slice().sort((a, b) => String(b.last_update).localeCompare(String(a.last_update)));
  const cats = [...new Set(gaps.map(g => g.category).filter(Boolean))].sort();
  const st0 = { q: '', c: '', d: '', n: 30 };
  const html = `<h1>預期落差</h1><p class="lede">「市場原本預期」和「實際數據」之間的落差：落差越大，股價越可能重新評價——往上是機會，往下是預警。</p>
  <div class="filters"><input type="search" id="g-q" placeholder="搜尋標的或公司"><select id="g-c"><option value="">全部類別</option>${cats.map(c => `<option>${esc(c)}</option>`).join('')}</select>
  <select id="g-d"><option value="">利多＋利空</option><option value="bullish">利多</option><option value="bearish">利空</option></select><span class="count" id="g-count"></span></div>
  <div class="grid" id="g-list"></div><p style="text-align:center;margin-top:20px"><button class="btn" id="g-more" hidden>載入更多</button></p>`;
  const draw = () => {
    const q = st0.q.trim().toLowerCase();
    const L = gaps.filter(g => (!st0.c || g.category === st0.c) && (!st0.d || g.impact_direction === st0.d) && (!q || `${g.target} ${g.market_expect} ${g.real_data} ${(g.concept_stocks || []).join(' ')}`.toLowerCase().includes(q)));
    $('#g-list').innerHTML = L.slice(0, st0.n).map(gapCard).join('') || '<div class="empty-state">沒有符合的項目</div>';
    $('#g-count').textContent = `${L.length} 則`;
    $('#g-more').hidden = L.length <= st0.n;
  };
  return { html, mount() {
    $('#g-q').addEventListener('input', e => { st0.q = e.target.value; st0.n = 30; draw(); });
    $('#g-c').addEventListener('change', e => { st0.c = e.target.value; draw(); });
    $('#g-d').addEventListener('change', e => { st0.d = e.target.value; draw(); });
    $('#g-more').addEventListener('click', () => { st0.n += 30; draw(); });
    draw();
  } };
}

/* ---------- 頁面：日報 ---------- */
async function pageReports() {
  const reports = await getJSON('reports.json');
  return `<h1>日報</h1><p class="lede">每日盤後：大盤、國際市場、總經觀點、預警與主流題材。</p>
  <div class="list panel" style="margin-top:16px">${reports.map(r => `<div><span class="small muted num">${esc(r.date)}</span> ${engineBadge(r.ai_engine)}<div><a href="#/r/${esc(r.id || r.date)}"><b>${esc(r.title)}</b></a></div></div>`).join('')}</div>`;
}

async function pageReport(id) {
  const reports = await getJSON('reports.json');
  const r = reports.find(x => (x.id || x.date) === id);
  if (!r) return '<div class="empty-state">找不到這份日報</div>';
  const wave = r.abc_wave_analysis || {};
  const waveBody = Array.isArray(wave.analysis) ? list(wave.analysis) : has(wave.analysis) ? `<div class="md">${String(wave.analysis).split(/\n+/).map(l => `<p>${esc(l.replace(/^[#*\-\s]+/, ''))}</p>`).join('')}</div>` : '';
  const f = r.fundamentals || {};
  return `<div class="crumbs"><a href="#/reports">日報</a> / ${esc(r.date)}</div>
  <div class="t-meta">${engineBadge(r.ai_engine)}<span class="small muted">${esc(r.date)}</span></div>
  <h1 style="margin:8px 0 12px">${esc(r.title)}</h1>${notice(r.ai_engine)}
  <p class="lede">${esc(r.taiex_summary)}</p>
  ${has(r.warnings) ? `<section class="section"><h2>今日預警</h2><div class="grid" style="margin-top:12px">${r.warnings.map(w => `<div class="alert mid"><b>${esc(w)}</b></div>`).join('')}</div></section>` : ''}
  ${has(r.macro_view) ? `<section class="section"><h2>總經觀點</h2><p style="margin-top:10px">${esc(r.macro_view)}</p><a class="small" href="#/macro">看總經數據 →</a></section>` : ''}
  ${has(r.global_status) ? `<section class="section"><h2>國際市場</h2><div class="grid g3" style="margin-top:12px">${r.global_status.map(g => `<div class="panel"><b>${esc(g.name)}</b> <span class="pill">${esc(g.peak)}</span><p class="small" style="margin-top:6px">${esc(g.desc)}</p></div>`).join('')}</div></section>` : ''}
  ${waveBody ? `<section class="section"><h2>技術面</h2><p>${esc(wave.intro)}</p>${waveBody}</section>` : ''}
  ${has(f.summary) ? `<section class="section"><h2>基本面</h2><div class="kpis" style="margin-top:12px">${['gdp_growth', 'earnings_growth', 'ai_industry'].filter(k => has(f[k])).map(k => `<div class="kpi"><div class="k">${{ gdp_growth: '經濟成長', earnings_growth: '企業獲利', ai_industry: 'AI 產業' }[k]}</div><div class="small">${esc(f[k])}</div></div>`).join('')}</div><p style="margin-top:12px">${esc(f.summary)}</p></section>` : ''}
  ${has(r.operation_advice) ? `<section class="section"><h2>操作觀點</h2><p class="quote">${esc(r.operation_advice)}</p><p class="small muted">研究參考，不構成投資建議。</p></section>` : ''}
  ${has(r.thematic_categories) ? `<section class="section"><h2>今日題材</h2><div class="grid g2" style="margin-top:12px">${r.thematic_categories.map(c => `<div class="panel"><h3>${esc(c.category_name)}</h3><p class="small">${esc(c.highlight)}</p><div class="list">${(c.stocks || []).map(s => `<div>${stockChip(s.code, s.name)} <span class="small muted">${esc(s.role)}</span></div>`).join('')}</div></div>`).join('')}</div></section>` : ''}
  ${has(r.sources) ? `<section class="section"><h2>出處</h2><div class="sources" style="margin-top:10px">${r.sources.map(s => `<div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a> <span class="small muted">${esc(s.published_at || '')}</span></div>`).join('')}</div></section>` : ''}`;
}

/* ---------- 頁面：方法 ---------- */
async function pageAbout() {
  const meta = await getJSON('meta.json');
  const run = meta.last_run;
  return `<h1>資料來源與方法</h1>
  <p class="lede">這個平台是投資人的獲利雷達與預警牆：從總經環境、全球題材，追到台股真正吃得到價值的公司。原則是事實優先、不假精準——每個重要數字都標出資料性質。</p>
  <div class="grid g2" style="margin-top:20px">
    <div class="panel"><h3>每日產線</h3><ol class="clean">
      <li>官方代號表（證交所、櫃買中心 OpenAPI）</li><li>總金線與總經指標：興櫃總經戰情室（FRED、證交所、BLS、FOMC）</li>
      <li>法人買賣超：證交所 T86、櫃買中心三大法人，算出每個題材的資金火勢</li><li>Claude 上網搜尋近期新聞，挑出值得研究的題材與退燒預警</li>
      <li>Claude 研究每個題材：論點、市場規模（要附出處）、價值鏈、投資節奏、總經敏感度</li><li>Claude 列出概念股（含先看三檔與跟風股），系統逐檔比對官方代號表，對不上的剔除</li>
      <li>個股簡介、預期落差（鉅亨網新聞）、盤後日報都由 Claude 查證後撰寫</li></ol></div>
    <div class="panel"><h3>標示</h3><p>${engineBadge('claude')} 由 Claude 上網查證後解析。${engineBadge('legacy')} 舊版產線產生、尚未重寫。</p>
      <p>資料性質：${Object.keys(ST).map(st).join(' ')}</p>
      <p class="small">總經順風／逆風＝Claude 判斷題材對哪些總經指標敏感 × 指標目前的實際方向。核心概念股要有直接出處；跟風股是相關營收很小、主要靠想像的公司。</p>
      <h3 style="margin-top:12px">最近一次執行</h3>${run ? `<p class="small">${esc(run.started_at)} → ${esc(run.finished_at || '進行中')}</p><ul class="clean">${(run.steps || []).map(s => `<li>${s.ok ? '✓' : '✗'} ${esc(s.name)}${s.note ? `：${esc(s.note)}` : ''}</li>`).join('')}</ul>` : '<p class="muted">尚未執行</p>'}</div>
  </div><p class="small muted" style="margin-top:20px">本站內容為研究整理，不構成任何投資建議。</p>`;
}

/* ---------- 全站搜尋 ---------- */
async function setupSearch() {
  const input = $('#q'), box = $('#q-results');
  let sel = -1;
  const close = () => { box.hidden = true; sel = -1; };
  input.addEventListener('input', async () => {
    const q = input.value.trim().toLowerCase();
    if (!q) return close();
    const [themes, idx] = await Promise.all([getJSON('themes.json'), getJSON('stocks.json')]);
    const T = themes.filter(t => `${t.title} ${t.tags.join(' ')}`.toLowerCase().includes(q)).slice(0, 5).map(t => ({ k: '題材', href: `#/t/${t.id}`, label: t.title }));
    const S = Object.entries(idx).filter(([c, s]) => c.startsWith(q) || s.n.toLowerCase().includes(q)).sort((a, b) => b[1].t - a[1].t).slice(0, 6).map(([c, s]) => ({ k: c, href: `#/s/${c}`, label: s.n }));
    const items = [...S, ...T];
    box.innerHTML = items.map(x => `<a href="${esc(x.href)}"><span class="k mono">${esc(x.k)}</span><span>${esc(x.label)}</span></a>`).join('') || '<div class="empty">找不到</div>';
    box.hidden = false; sel = -1;
  });
  input.addEventListener('keydown', e => {
    const as = [...box.querySelectorAll('a')];
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && as.length) { e.preventDefault(); sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + as.length) % as.length; as.forEach((a, i) => a.classList.toggle('sel', i === sel)); }
    else if (e.key === 'Enter' && as.length) { location.hash = (as[sel] || as[0]).getAttribute('href'); input.value = ''; close(); input.blur(); }
    else if (e.key === 'Escape') close();
  });
  box.addEventListener('click', () => { input.value = ''; close(); });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) close(); });
}

/* ---------- 路由 ---------- */
const ROUTES = [
  [/^\/?$/, () => pageHome(), 'home'], [/^\/themes$/, (m, p) => pageThemes(p), 'themes'], [/^\/t\/([\w-]+)$/, m => pageTheme(m[1]), 'themes'],
  [/^\/macro$/, () => pageMacro(), 'macro'], [/^\/stocks$/, (m, p) => pageStocks(p), 'stocks'], [/^\/s\/(\w+)$/, m => pageStock(m[1]), 'stocks'],
  [/^\/flows$/, () => pageFlows(), 'flows'], [/^\/gaps$/, () => pageGaps(), 'gaps'], [/^\/reports$/, () => pageReports(), 'reports'],
  [/^\/r\/([\w-]+)$/, m => pageReport(m[1]), 'reports'], [/^\/about$/, () => pageAbout(), ''],
];
let lastPath = '';
async function route() {
  const raw = decodeURIComponent(location.hash.replace(/^#/, '') || '/');
  const [path, qs] = raw.split('?');
  for (const [re, fn, nav] of ROUTES) {
    const m = path.match(re);
    if (!m) continue;
    document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === nav));
    if (path !== lastPath) main.innerHTML = '<div class="loading">載入中…</div>';
    try {
      const out = await fn(m, new URLSearchParams(qs || ''));
      main.innerHTML = typeof out === 'string' ? out : out.html;
      if (out && out.mount) out.mount();
      const h1 = $('h1', main);
      document.title = h1 && path && path !== '/' ? `${h1.textContent}｜題材地圖` : '題材地圖｜投資人的獲利雷達與預警牆';
      if (path !== lastPath) window.scrollTo(0, 0);
      lastPath = path;
    } catch (e) {
      main.innerHTML = `<div class="empty-state">載入失敗：${esc(e.message)}</div>`;
    }
    return;
  }
  main.innerHTML = '<div class="empty-state">找不到這個頁面。<a href="#/">回首頁</a></div>';
}

document.addEventListener('click', e => {
  const a = e.target.closest('[data-jump]');
  if (!a) return;
  e.preventDefault();
  document.getElementById(a.dataset.jump)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

$('#theme-toggle').addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('thememap-theme', document.documentElement.dataset.theme); } catch (e) {}
});

(async () => {
  try {
    const meta = await getJSON('meta.json');
    VERSION = meta.built_at || '';
    $('#built-at').textContent = `資料更新於 ${String(meta.built_at || '').slice(0, 16).replace('T', ' ')}`;
  } catch (e) { /* meta 讀不到時照樣用 no-store 讀其他檔 */ }
  cache.clear();
  setupSearch();
  window.addEventListener('hashchange', route);
  route();
})();
