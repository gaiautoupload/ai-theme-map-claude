"""法人買賣超（證交所 T86、櫃買中心三大法人）：存進 data/chips.db，算出當日摘要與每個題材的資金火勢。

修正舊產線的問題：
- 只在證交所確認有資料的交易日寫入；櫃買 API 回傳的日期跟要的日期不同就不寫（舊版會把週五資料存成週末）。
- 上櫃股數用 Capitals／1000（舊版除以 10000，持股比例放大 10 倍）。
- 族群分類改用官方產業別，不用寫死的對照表。
單位一律是「張」。
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import timedelta

import requests

from . import config
from .store import load, log_event, now_tw, save

DB = config.DATA / "chips.db"
H = {"User-Agent": "Mozilla/5.0"}


def _con():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS chips_history (date TEXT, symbol TEXT, name TEXT, foreign_net INTEGER, trust_net INTEGER,"
                " dealer_net INTEGER, total_net INTEGER, PRIMARY KEY (date, symbol))")
    return con


def _int(x) -> int:
    try:
        return int(float(str(x).replace(",", "").strip() or 0))
    except ValueError:
        return 0


def fetch_day(day: str) -> list[tuple]:
    """抓某個交易日（YYYYMMDD）的上市＋上櫃法人買賣超；證交所說沒資料就回傳空清單（非交易日或還沒公布）。"""
    t = requests.get(f"https://www.twse.com.tw/rwd/zh/fund/T86?date={day}&selectType=ALLBUT0999&response=json", headers=H, timeout=30).json()
    if t.get("stat") != "OK" or not t.get("data") or str(t.get("date")) != day:
        return []
    f = t["fields"]
    ix = lambda name: f.index(name)
    rows = []
    for r in t["data"]:
        code = str(r[0]).strip()
        foreign = _int(r[ix("外陸資買賣超股數(不含外資自營商)")]) + _int(r[ix("外資自營商買賣超股數")])
        trust, dealer, total = _int(r[ix("投信買賣超股數")]), _int(r[ix("自營商買賣超股數")]), _int(r[ix("三大法人買賣超股數")])
        rows.append((day, code, str(r[1]).strip(), foreign // 1000, trust // 1000, dealer // 1000, total // 1000))
    try:
        tp = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading", headers=H, timeout=30).json()
        roc = f"{int(day[:4]) - 1911}{day[4:]}"
        for x in tp:
            if str(x.get("Date")) != roc:
                continue  # 櫃買只給最新一天；日期不符就不寫，避免錯植
            g = lambda name: next((x[k] for k in x if k.replace(" ", "") == name), 0)  # 欄位名稱的空白不一致，去掉空白後完全比對
            foreign = _int(g("ForeignInvestorsincludeMainlandAreaInvestors(ForeignDealersexcluded)-Difference")) + _int(g("ForeignDealers-Difference"))
            trust = _int(g("SecuritiesInvestmentTrustCompanies-Difference"))
            dealer = _int(g("Dealers-Difference"))
            total = _int(g("TotalDifference")) or foreign + trust + dealer
            rows.append((day, str(x.get("SecuritiesCompanyCode", "")).strip(), str(x.get("CompanyName", "")).strip(),
                         foreign // 1000, trust // 1000, dealer // 1000, total // 1000))
    except Exception as e:
        log_event("chips", ok=False, step="tpex", error=str(e)[:200])
    return rows


def refresh_shares() -> dict:
    """流通股數（張）：上市取已發行普通股數，上櫃取 Capitals（股數）。每週更新一次。"""
    path = config.DATA / "shares.json"
    old = load(path, {}) or {}
    if old.get("_at", "") >= (now_tw() - timedelta(days=7)).strftime("%Y-%m-%d") and len(old) > 1000:
        return old
    out = {"_at": now_tw().strftime("%Y-%m-%d")}
    try:
        for x in requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers=H, timeout=30).json():
            n = _int(x.get("已發行普通股數或TDR原股發行股數"))
            if n:
                out[str(x["公司代號"]).strip()] = n // 1000
        for x in requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=H, timeout=30).json():
            n = _int(x.get("Capitals"))
            if n:
                out[str(x["SecuritiesCompanyCode"]).strip()] = n // 1000
    except Exception as e:
        log_event("chips", ok=False, step="shares", error=str(e)[:200])
        return old
    save(path, out)
    return out


def update(max_back: int = 6) -> str | None:
    """寫入最近幾天還沒進資料庫的交易日；回傳最新有資料的日期。"""
    con = _con()
    have = {r[0] for r in con.execute("SELECT DISTINCT date FROM chips_history")}
    latest = None
    for i in range(max_back, -1, -1):
        d = now_tw() - timedelta(days=i)
        day = d.strftime("%Y%m%d")
        if d.weekday() >= 5:
            continue
        if day in have:
            latest = day
            continue
        try:
            rows = fetch_day(day)
        except Exception as e:
            log_event("chips", ok=False, day=day, error=str(e)[:200])
            continue
        if rows:
            with con:
                con.executemany("INSERT OR REPLACE INTO chips_history VALUES (?,?,?,?,?,?,?)", rows)
            latest = day
            log_event("chips", ok=True, day=day, rows=len(rows))
    con.close()
    return latest or max(have, default=None)


def build_summary(themes: dict, reg: dict) -> dict:
    """當日摘要（外資、投信、同步買超、爆量、產業族群）＋每個題材的資金火勢＋題材股的 20 日序列。"""
    con = _con()
    dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM chips_history ORDER BY date DESC LIMIT 20")][::-1]
    if not dates:
        return {}
    day = dates[-1]
    shares = refresh_shares()
    rows = {r[0]: r for r in con.execute("SELECT symbol,name,foreign_net,trust_net,dealer_net,total_net FROM chips_history WHERE date=?", (day,))}
    hist = defaultdict(dict)
    for d, s, fn, tn in con.execute(f"SELECT date,symbol,foreign_net,trust_net FROM chips_history WHERE date IN ({','.join('?' * len(dates))})", dates):
        hist[s][d] = (fn, tn)
    con.close()

    def row(s):
        _, name, fn, tn, dn, tot = rows[s]
        sh = shares.get(s) or 0
        return {"symbol": s, "name": name, "foreign_net": fn, "trust_net": tn, "total_net": tot,
                "foreign_ratio": round(fn / sh * 100, 3) if sh else None, "trust_ratio": round(tn / sh * 100, 3) if sh else None}

    stocks = [s for s in rows if len(s) == 4 and not s.startswith("00")]
    prev5 = dates[-6:-1]

    def surge(s, i):
        past = [hist[s][d][i] for d in prev5 if d in hist[s] and hist[s][d][i] > 0]
        now = rows[s][2 + i]
        return now > 100 and (now > 1.5 * (sum(past) / len(past)) if past else now > 500)

    top = lambda key, L, n=30: sorted((row(s) for s in L), key=lambda r: r[key], reverse=True)[:n]
    cohort = [s for s in stocks if rows[s][2] > 0 and rows[s][3] > 0]
    groups = defaultdict(list)
    for s in cohort:
        groups[reg.get(s, {}).get("industry") or "其他"].append(row(s))
    cohort_themes = sorted(({"theme_name": g, "total_net_buy": sum(r["total_net"] for r in L), "count": len(L),
                             "stocks": sorted(L, key=lambda r: r["total_net"], reverse=True)} for g, L in groups.items()),
                           key=lambda x: x["total_net_buy"], reverse=True)[:10]

    # 題材資金火勢：題材內個股外資＋投信合計（1 日、5 日）與買超家數
    flows = {}
    for tid, t in themes.items():
        codes = list(dict.fromkeys(s["code"] for s in t.get("stocks", [])))
        if not codes:
            continue
        f1 = sum(sum(hist[c].get(day, (0, 0))) for c in codes)
        last5 = dates[-5:]
        per = {c: sum(sum(hist[c].get(d, (0, 0))) for d in last5) for c in codes}
        flows[tid] = {"f1": f1, "f5": sum(per.values()), "buy": sum(v > 0 for v in per.values()), "n": len(codes),
                      "lead": sorted(([c, v] for c, v in per.items() if v), key=lambda x: -abs(x[1]))[:5]}
    theme_codes = {s["code"] for t in themes.values() for s in t.get("stocks", [])}
    series = {"dates": dates, "series": {c: [list(hist[c].get(d, (0, 0))) for d in dates] for c in sorted(theme_codes) if c in hist}}

    summary = {
        "date": day, "update_time": now_tw().strftime("%Y-%m-%d %H:%M"), "unit": "張",
        "top_foreign_buys": top("foreign_net", stocks), "top_trust_buys": top("trust_net", stocks),
        "top_foreign_sells": sorted((row(s) for s in stocks), key=lambda r: r["foreign_net"])[:30],
        "cohort_buys": top("total_net", cohort, 50), "cohort_themes": cohort_themes,
        "foreign_surges": top("foreign_net", [s for s in stocks if surge(s, 0)]), "trust_surges": top("trust_net", [s for s in stocks if surge(s, 1)]),
        "ratio_note": "持股比例＝當日買賣超張數 ÷ 流通張數 × 100%",
    }
    save(config.DATA / "chips_summary.json", summary)
    save(config.DATA / "theme_flows.json", {"date": day, "dates5": dates[-5:], "flows": flows})
    save(config.DATA / "chips_series.json", series, compact=True)
    log_event("chips_summary", ok=True, date=day, themes=len(flows))
    return summary


def run() -> str:
    from .registry import get as get_reg
    day = update()
    build_summary(load(config.DATA / "themes.json", {}) or {}, get_reg())
    return f"法人資料最新 {day}"


if __name__ == "__main__":
    print(run())
