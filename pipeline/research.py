"""個股簡介、盤後日報、預期落差：都由 Claude 上網查證後產生。"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from . import config
from .claude_cli import ClaudeError, ask_json, require
from .macro_bridge import snapshot_text
from .registry import get as get_reg, match
from .schema import SOURCE_RULE
from .store import TW, iso_now, load, log_event, now_tw, save, today
from .verify import _text, mentions

H = {"User-Agent": "Mozilla/5.0"}


# ---------- 個股簡介 ----------
WIKI_SPEC = """{
 "summary": "這家公司做什麼、在哪些題材裡扮演什麼角色（40 字內）",
 "products": ["主要產品或業務，3 到 6 項"],
 "revenue_mix": "營收結構（有出處才寫比例）",
 "revenue_mix_source_type": "official｜news_derived｜analyst_estimate｜llm_inference｜pending",
 "details": {"pure_level": 0到5, "barrier_level": 0到5, "pricing_power": "高｜中｜低", "ai_revenue_exposure": "AI 或主要題材相關營收占比，查不到寫「未揭露」",
             "commercialization_phase": "主要新業務的放量時程", "substitution_risk": "高｜中｜低", "pros": "投資亮點", "cons": "風險提醒", "catalyst": "近期催化／驗證事件"},
 "sources": [{"title": "", "url": "https://...", "published_at": "YYYY-MM-DD"}]
}"""


def wiki_one(code: str, name: str, themes_of: list) -> dict:
    prompt = f"""你是台股產業研究員。今天是 {today()}。請上網查證「{name}（{code}）」的最新公開資料（年報、法說會、月營收、新聞），寫成投資人看的公司簡介。
這家公司在本站被列入的題材：{'、'.join(themes_of) or '（無）'}。
{SOURCE_RULE}
輸出格式：
{WIKI_SPEC}"""
    d = ask_json(f"個股：{code} {name}", prompt, web=True, effort="medium", validate=require("summary", lists=("products",)))
    d["products"] = [str(p) for p in d.get("products", [])][:6]
    return d


def run_wiki(themes: dict) -> str:
    reg, wiki = get_reg(), load(config.DATA / "stocks_wiki.json", {}) or {}
    in_themes: dict = {}
    claude_codes = set()
    for t in themes.values():
        for s in t.get("stocks", []):
            in_themes.setdefault(s["code"], []).append(t["title"])
            if t.get("ai_engine") == config.ENGINE:
                claude_codes.add(s["code"])
    # 優先：Claude 題材裡的股票 → 出現在越多題材的 → 其他；已經是 Claude 寫的、30 天內的跳過
    fresh = lambda c: wiki.get(c, {}).get("ai_engine") == config.ENGINE and wiki[c].get("updated_at", "") >= (now_tw() - timedelta(days=30)).strftime("%Y-%m-%d")
    todo = sorted((c for c in in_themes if c in reg and not reg[c].get("etf") and not fresh(c)),
                  key=lambda c: (c not in claude_codes, -len(in_themes[c]), c))[: config.WIKI_PER_RUN]
    ok, bad = 0, []

    def job(c):
        return c, wiki_one(c, reg[c]["name"], in_themes.get(c, [])[:8])

    with ThreadPoolExecutor(config.CLAUDE_WORKERS) as ex:
        for fut in [ex.submit(job, c) for c in todo]:
            try:
                c, d = fut.result()
            except Exception as e:
                bad.append(str(e)[:80])
                continue
            r = reg[c]
            wiki = load(config.DATA / "stocks_wiki.json", {}) or {}
            wiki[c] = {"code": c, "name": r["name"], "market": r["market"], "industry": r.get("industry", ""), "themes": in_themes.get(c, [])[:20],
                       **d, "ai_engine": config.ENGINE, "updated_at": today(), "model": config.CLAUDE_MODEL}
            save(config.DATA / "stocks_wiki.json", wiki)
            ok += 1
    if todo and not ok:
        raise ClaudeError(f"個股簡介全部失敗：{bad[:2]}")
    return f"重寫 {ok}/{len(todo)} 檔個股簡介" + (f"，失敗 {len(bad)}" if bad else "")


# ---------- 盤後日報 ----------
def _official_day(day: str) -> dict:
    """證交所當天的正式數字：FMTQIK（指數、漲跌、成交金額）、BFI82U（外資、三大法人金額）。抓不到的欄位就不給。"""
    d8, out = day.replace("-", ""), {}
    roc = f"{int(d8[:4]) - 1911}/{d8[4:6]}/{d8[6:]}"
    num = lambda x: float(str(x).replace(",", ""))
    try:
        u = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={d8}&response=json"
        for r in requests.get(u, headers=H, timeout=30).json().get("data", []):
            if r[0] == roc:
                out.update(close=num(r[4]), change=num(r[5]), turnover=num(r[2]), url_fmtqik=u)
    except Exception as e:
        log_event("official", ok=False, step="FMTQIK", error=str(e)[:200])
    try:
        u = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate={d8}&type=day"
        rows = {r[0]: num(r[3]) for r in requests.get(u, headers=H, timeout=30).json().get("data", [])}
        if "合計" in rows:
            out.update(foreign=rows.get("外資及陸資(不含外資自營商)", 0) + rows.get("外資自營商", 0), total=rows["合計"], url_bfi=u)
    except Exception as e:
        log_event("official", ok=False, step="BFI82U", error=str(e)[:200])
    return out


NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*")
ymd8 = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and len(str(s)) == 8 and str(s).isdigit() else str(s or "")[:10]


def _nums(text: str) -> list[float]:
    out = []
    for tok in NUM.findall(str(text or "")):
        try:
            out.append(abs(float(tok.replace(",", ""))))
        except ValueError:
            pass
    return out


def _report_check(facts: dict, hist: list, macro: dict, chips: dict):
    """自動核對日報的台股數字：收盤與漲跌必須照官方寫；大於 100 的數字必須來自官方數據、近期收盤或 500 點整數關卡。"""
    allowed = {abs(v) for v in (facts["close"], facts["change"], facts["change_pct"], facts["turnover_e8"], facts["foreign_net_e8"], facts["inst_net_e8"]) if v is not None}
    allowed |= {round(v, 2) for _, v in hist} | {round(v) for _, v in hist}
    for lst in ("top_foreign_buys", "top_trust_buys", "top_foreign_sells"):
        for r in chips.get(lst, [])[:8]:
            allowed |= {abs(r.get("foreign_net") or 0), abs(r.get("trust_net") or 0)} | ({float(r["symbol"])} if str(r.get("symbol", "")).isdigit() else set())
    macro_txt = snapshot_text(macro)
    reg, page_cache = get_reg(), {}
    themes = load(config.DATA / "themes.json", {}) or {}
    linked = {r["symbol"] for lst in ("top_foreign_buys", "top_trust_buys", "top_foreign_sells", "cohort_buys", "foreign_surges", "trust_surges")
              for r in chips.get(lst, [])} if ymd8(chips.get("date")) == facts["date"] else set()
    linked |= {s["code"] for t in themes.values() if t.get("ai_engine") == config.ENGINE for s in t.get("stocks", [])}
    allowed_macro = set(_nums(macro_txt))

    def ok_num(x: float) -> bool:
        if x < 100 or 2000 <= x <= 2100:  # 小數字（百分比、天數）與年份不檢查
            return True
        return any(abs(x - a) <= max(0.06, a * 0.0005) for a in allowed) or (x >= 10000 and x % 500 == 0)

    def check(d):
        miss = require("title", "taiex_summary", "macro_view", "operation_advice")(d)
        if miss:
            return miss
        head = f"{d['title']} {d['taiex_summary']}"
        if f"{facts['close']:,.2f}" not in head and f"{facts['close']:.2f}" not in head:
            return f"標題或大盤摘要必須寫出正確的收盤 {facts['close']:,.2f}"
        if facts["change"] is not None:
            if f"{abs(facts['change']):,.2f}" not in head and f"{abs(facts['change']):.2f}" not in head:
                return f"漲跌點數必須是 {facts['change']:+,.2f}"
            word = "漲" if facts["change"] > 0 else "跌"
            if word not in d["title"]:
                return f"今天是{'上漲' if word == '漲' else '下跌'}，標題要寫對方向"
        wave = d.get("abc_wave_analysis") or {}
        texts = [head, d.get("operation_advice", ""), " ".join(d.get("warnings") or []), str(wave.get("intro", "")),
                 " ".join(wave.get("analysis") if isinstance(wave.get("analysis"), list) else [str(wave.get("analysis", ""))])]
        bad = sorted({x for t in texts for x in _nums(t) if not ok_num(x)})
        if bad:
            return f"出現官方數據以外的台股數字：{'、'.join(f'{b:,.2f}'.rstrip('0').rstrip('.') for b in bad[:6])}。只能用提供的官方數據、近期收盤或 500 點整數關卡"
        # 主流題材的個股：代號名稱要對得上官方表，而且要有連動依據（今天的法人名單、站上已查證題材，或出處網頁有提到）
        wrong = []
        for c in d.get("thematic_categories") or []:
            for s in c.get("stocks") or []:
                code, name = str(s.get("code", "")).strip(), str(s.get("name", "")).strip()
                if not match(code, name, reg):
                    wrong.append(f"{code} {name}（代號和名稱對不上官方代號表）")
                elif code not in linked and not (s.get("evidence_url") and mentions(_text(s["evidence_url"], page_cache), code, name, reg)):
                    wrong.append(f"{code} {name}（沒有連動依據：不在今天法人名單或站上題材，出處網頁也沒提到它）")
        if wrong:
            return "主流題材的個股有問題，請更正或刪除：" + "；".join(wrong[:8])
        mbad = sorted({x for x in _nums(d["macro_view"]) if x >= 100 and not (2000 <= x <= 2100) and not any(abs(x - a) <= max(0.06, a * 0.001) for a in allowed_macro | allowed)})
        if mbad:
            return f"總經觀點出現戰情室數據以外的數字：{'、'.join(str(b) for b in mbad[:6])}，請只用提供的總經數據"
        return None
    return check

REPORT_SPEC = """{
 "title": "今天盤勢一句話（含指數漲跌點數）",
 "taiex_summary": "大盤摘要：漲跌、成交量、法人、主流族群（數字用上面提供的官方數據）",
 "global_status": [{"name": "市場或指數", "peak": "狀態四字內", "desc": "一句說明"}],
 "macro_view": "總經觀點 200 到 300 字：根據上面的真實總經數據，說明目前環境對台股與題材的意義，並提醒要注意的數據公布",
 "abc_wave_analysis": {"intro": "技術面一句話", "analysis": ["支撐、壓力與觀察點，3 點"]},
 "fundamentals": {"gdp_growth": "", "earnings_growth": "", "ai_industry": "", "summary": ""},
 "operation_advice": "操作觀點（研究參考，不構成投資建議；要呼應總金線與環境判定）",
 "warnings": ["今天的預警訊號，例如族群過熱、外資連續賣超、總經數據風險"],
 "thematic_categories": [{"category_name": "今天的主流題材", "highlight": "為什麼（要有今天的依據）", "stocks": [{"code": "台股代號", "name": "公司簡稱", "role": "在這個題材的角色", "evidence_url": "今天提到這家公司與這個題材的報導網址（若它在上面的法人買賣超名單或站上題材裡可留空）"}]}],
 "sources": [{"title": "", "url": "https://...", "published_at": "YYYY-MM-DD"}]
}"""


def run_report(macro: dict, chips: dict) -> str:
    ind = (macro or {}).get("indicators", {})
    tx, tv, fn, inst = (ind.get(k, {}) for k in ("TW_TAIEX", "TW_TURNOVER", "TW_FOREIGN_NET", "TW_INST_NET"))
    hist = tx.get("history") or []
    if not hist:
        raise ClaudeError("沒有加權指數資料，不產生日報")
    day, close = hist[-1]
    prev = hist[-2][1] if len(hist) > 1 else None
    same_day = lambda x: x.get("date") == day and x.get("value") is not None
    off = _official_day(day)  # 直接向證交所抓當天的正式數字（戰情室的快照可能早於收盤結算）
    if off.get("close"):
        close, prev = off["close"], off["close"] - off["change"]
        tv = {"date": day, "value": off["turnover"], "source_url": off["url_fmtqik"]}
        if off.get("foreign") is not None:
            fn = {"date": day, "value": off["foreign"], "source_url": off["url_bfi"]}
            inst = {"date": day, "value": off["total"]}
        tx = dict(tx, source_url=off["url_fmtqik"])
    # 官方數字：網站上的關鍵數字直接用這些，不用 Claude 寫的文字
    facts = {"date": day, "close": round(close, 2), "change": round(close - prev, 2) if prev else None,
             "change_pct": round((close / prev - 1) * 100, 2) if prev else None,
             "turnover_e8": round(tv["value"] / 1e8) if same_day(tv) else None,
             "foreign_net_e8": round(fn["value"] / 1e8, 1) if same_day(fn) else None,
             "inst_net_e8": round(inst["value"] / 1e8, 1) if same_day(inst) else None,
             "chips_date": ymd8(chips.get("date")), "source": "證交所（加權指數、成交金額、三大法人金額）",
             "source_urls": [u for u in (tx.get("source_url"), fn.get("source_url")) if u]}
    chg = f"{facts['change']:+,.2f} 點（{facts['change_pct']:+.2f}%）" if prev else "（無前一日資料）"
    top = lambda key, lst: "、".join(f"{r['name']}({r['symbol']}) {r[key]:+,}" for r in chips.get(lst, [])[:8])
    recent = "、".join(f"{d_}：{v:,.2f}" for d_, v in hist[-20:])
    lines = [f"- 加權指數收盤 {close:,.2f}，{chg}"]
    if facts["turnover_e8"] is not None:
        lines.append(f"- 集中市場成交金額 {facts['turnover_e8']:,} 億元")
    if facts["foreign_net_e8"] is not None:
        lines.append(f"- 外資及陸資淨買賣 {facts['foreign_net_e8']:+,.1f} 億元" + (f"；三大法人合計 {facts['inst_net_e8']:+,.1f} 億元" if facts["inst_net_e8"] is not None else ""))
    if facts["chips_date"] == day:
        lines += [f"- 外資買超前幾名（張）：{top('foreign_net', 'top_foreign_buys')}", f"- 投信買超前幾名（張）：{top('trust_net', 'top_trust_buys')}",
                  f"- 外資賣超前幾名（張）：{top('foreign_net', 'top_foreign_sells')}"]
    prompt = f"""你是台股盤後分析師。今天是 {today()}。請寫 {day} 的盤後日報。這份日報每個數字都必須正確：
- 台股的數字（指數、漲跌、成交金額、法人金額、個股買賣超張數）只能用下面的官方數據，沒列的台股數字一律不要寫。
- 支撐、壓力只能用下面近期的實際收盤價或整數關卡（500 點的倍數），不要自己估算其他價位。
- 國際市場、新聞、法說會等其他資訊要上網查證，放進 sources（含網址與日期）；查不到就不要寫。
- 讀者是在「今天」看這份日報：寫進日報的重大事件，要查到今天為止的最新進展（公司正式公告、監管文件優先）。
  {day} 收盤後才發生的事要寫明時間先後（例如「台股收盤後，○○公告…」），不要寫成「結果尚未確認」而實際上已有公告。
- 總經的數字只能用下面戰情室的數據。

## 官方數據（證交所，{day}）
{chr(10).join(lines)}
- 近期加權指數收盤：{recent}

## 總經（興櫃總經戰情室的真實數據）
{snapshot_text(macro)}

## 輸出格式
{REPORT_SPEC}"""
    d = ask_json(f"日報 {day}", prompt, web=True, effort="high", retries=2, validate=_report_check(facts, hist, macro, chips))
    d.update({"id": f"report-{day.replace('-', '')}", "date": day, "ai_engine": config.ENGINE, "generated_at": iso_now(),
              "facts": facts, "fact_check": "台股數字已與證交所官方數據自動比對"})
    reports = [r for r in (load(config.DATA / "reports.json", []) or []) if r.get("date") != day]
    save(config.DATA / "reports.json", sorted([d, *reports], key=lambda r: r.get("date", ""), reverse=True))
    save(config.DATA / "macro.json", {"date": day, "analysis": d["macro_view"], "ai_engine": config.ENGINE})
    return f"日報 {day} 完成"


# ---------- 預期落差 ----------
GAP_KEYWORDS = ["優於預期", "不如預期", "上修", "下修", "財測", "法說會", "營收創新高", "漲價", "缺貨", "砍單", "訂單能見度"]


def _cnyes(q: str) -> list:
    r = requests.get("https://api.cnyes.com/media/api/v1/search", params={"q": q, "limit": 20}, headers=H, timeout=20).json()
    return ((r.get("items") or {}).get("data") or []) if isinstance(r, dict) else []


def _article(news_id) -> str:
    html = requests.get(f"https://news.cnyes.com/news/id/{news_id}", headers=H, timeout=20).text
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S)
    return re.sub(r"<[^>]+>|&nbsp;", "", "\n".join(paras))[:3500]


def run_gaps() -> str:
    seen_path = config.CACHE / "gap_seen.json"
    seen = set(load(seen_path, []) or [])
    cut = (now_tw() - timedelta(days=3)).timestamp()
    cands = {}
    for k in GAP_KEYWORDS:
        try:
            for it in _cnyes(k):
                nid = str(it.get("newsId") or "")
                if nid and nid not in seen and (it.get("publishAt") or 0) >= cut:
                    cands[nid] = {"id": nid, "title": re.sub(r"<[^>]+>", "", it.get("title", "")), "date": datetime.fromtimestamp(it["publishAt"], TW).strftime("%Y-%m-%d")}
        except Exception as e:
            log_event("gap_search", ok=False, q=k, error=str(e)[:120])
    if not cands:
        return "沒有新的候選新聞"
    pick = ask_json("預期落差篩選", f"""以下是今天的財經新聞標題。挑出明確牽涉「市場預期 vs 實際數據」落差、而且跟台股公司有關的（最多 {config.GAP_ARTICLES_PER_RUN} 則）。
{chr(10).join(f"{c['id']}｜{c['title']}" for c in cands.values())}
輸出：{{"ids": ["新聞 ID"]}}""", effort="low", validate=require(lists=()))
    ids = [str(i) for i in pick.get("ids", []) if str(i) in cands][: config.GAP_ARTICLES_PER_RUN]
    seen |= set(cands)
    save(seen_path, sorted(seen)[-5000:])
    if not ids:
        return "今天沒有符合的預期落差新聞"
    texts, article_text = [], {}
    for i in ids:
        try:
            article_text[i] = _article(i)
            texts.append(f"### {i}｜{cands[i]['date']}｜{cands[i]['title']}\n{article_text[i]}")
        except Exception:
            pass
    reg = get_reg()
    d = ask_json("預期落差摘要", f"""你是台股研究員。以下是鉅亨網新聞全文。每則若真的有「市場預期」與「實際數據」的落差，整理成一筆；沒有就略過。
concept_stocks 只放文中提到的台股，格式「代號 簡稱」。數字要照原文，不要自己估。
{chr(10).join(texts)}
輸出：{{"items": [{{"news_id": "", "category": "產業類別", "target": "標的（公司或產品）", "market_expect": "市場原本預期", "real_data": "實際數據", "gap_space": "落差代表的意義與空間",
 "concept_stocks": ["2330 台積電"], "dream_rating": "利多估值重估｜利多追價效應｜利多出盡｜利空估值修正｜利空重擊", "impact_direction": "bullish｜bearish｜neutral"}}]}}""",
                 effort="medium", validate=require(lists=()))
    gaps = load(config.DATA / "gap.json", []) or []
    added = 0
    for it in d.get("items", []):
        nid = str(it.get("news_id", ""))
        if nid not in cands:
            continue
        body = article_text.get(nid, "")  # 連動股票必須在這則新聞內文裡被提到，代號名稱也要對得上官方表
        it["concept_stocks"] = [f"{p[0]} {reg[p[0]]['name']}" for p in (str(x).split(" ", 1) for x in it.get("concept_stocks", []))
                                if len(p) == 2 and match(p[0], p[1], reg) and mentions(body, p[0], p[1], reg)]
        it["stocks_verified"] = bool(body)
        it.update({"source": cands[nid]["title"], "source_url": f"https://news.cnyes.com/news/id/{nid}", "last_update": cands[nid]["date"],
                   "ai_engine": config.ENGINE})
        gaps.insert(0, it)
        added += 1
    save(config.DATA / "gap.json", gaps)
    return f"新增 {added} 則預期落差"
