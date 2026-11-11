"""把 data/ 的正式資料整理成網站讀的小檔（site/data/）。

舊站一次載入 14 MB；這裡拆成：
- themes.json：題材卡片（10 秒要看到的欄位＋總經順逆風＋法人火勢），themes/<id>.json：單一題材全文（含總經與火勢明細）。
- stocks.json：個股索引；stocks/<代號前兩碼>.json：個股簡介分片；stock_links.json：個股出現在哪些題材、什麼角色。
- macro.json：總金線與總經指標；chips.json、chips_series.json：法人；reports.json、gap.json；meta.json：資料日期與執行狀態。
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import timedelta

from . import config
from .macro_bridge import macro_fit
from .store import iso_now, load, now_tw, save

D, S = config.DATA, config.SITE_DATA


def _short(text: str, n: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _priority(t: dict) -> list:
    ss = t.get("stocks", [])
    ranked = sorted((s for s in ss if s.get("priority")), key=lambda s: s["priority"])
    rest = sorted((s for s in ss if not s.get("priority") and not s.get("follower") and s.get("tier") == "core"),
                  key=lambda s: (-(s.get("value_capture_score") or 0), -(s.get("pure_level") or 0)))
    return [{"code": s["code"], "name": s["name"], "role": _short(s.get("role"), 24)} for s in (ranked + rest)[:3]]


def build() -> dict:
    themes = load(D / "themes.json", {}) or {}
    wiki = load(D / "stocks_wiki.json", {}) or {}
    reg = load(D / "registry.json", {}) or {}
    board = load(D / "macro_board.json", {}) or {}
    flows = load(D / "theme_flows.json", {}) or {}
    for sub in ("themes", "stocks"):
        if (S / sub).exists():
            shutil.rmtree(S / sub)

    cards, links = [], defaultdict(list)
    for tid, t in themes.items():
        fit = macro_fit(t, board.get("factors", {}))
        flow = (flows.get("flows") or {}).get(tid)
        save(S / "themes" / f"{tid}.json", dict(t, macro_fit=fit, flow=flow, flow_dates=flows.get("dates5")), compact=True)
        cards.append({
            "id": tid, "title": t["title"], "group": t.get("group") or "未分類", "date": t.get("date", ""), "updated_at": t.get("updated_at", ""),
            "engine": t.get("ai_engine", ""), "heat": t.get("heat", ""), "heat_score": t.get("heat_score", 0), "stage": t.get("theme_stage", ""),
            "one_liner": _short(t.get("one_liner") or t.get("summary"), 70), "why_now": _short(t.get("why_now"), 90),
            "tags": t.get("theme_tags", [])[:5], "tam": t.get("market_size_tam", ""), "tam_st": t.get("market_size_tam_source_type", ""),
            "cagr": t.get("market_cagr", ""), "cagr_st": t.get("market_cagr_source_type", ""),
            "n_stocks": len(t["stocks"]), "priority": _priority(t), "macro": fit["verdict"],
            "flow5": flow["f5"] if flow else None, "breadth": [flow["buy"], flow["n"]] if flow else None,
            "warn": len(t.get("warnings", [])), "cooling": t.get("cooling", {}).get("reason", ""),
        })
        for s in t["stocks"]:
            links[s["code"]].append([tid, _short(s.get("role"), 40), s.get("tier"), s.get("priority")])
    cards.sort(key=lambda c: (c["updated_at"] or c["date"]), reverse=True)
    save(S / "themes.json", cards, compact=True)
    save(S / "stock_links.json", links, compact=True)

    index, shards = {}, defaultdict(dict)
    for code in sorted(set(reg) | set(wiki)):
        r, w = reg.get(code, {}), wiki.get(code, {})
        name = r.get("name") or w.get("name")
        if not name:
            continue
        index[code] = {"n": name, "m": r.get("market") or w.get("market", ""), "i": r.get("industry") or w.get("industry", ""),
                       "t": len(links.get(code, [])), "w": 1 if w else 0, "e": w.get("ai_engine", "")}
        if w:
            shards[code[:2]][code] = w
    save(S / "stocks.json", index, compact=True)
    for p, rows in shards.items():
        save(S / "stocks" / f"{p}.json", rows, compact=True)

    # 日報只發布 Claude 依官方數據產生、通過數字核對的；舊模型日報數字有誤，不再對外顯示
    reports = sorted((r for r in (load(D / "reports.json", []) or []) if r.get("ai_engine") == config.ENGINE and r.get("facts")),
                     key=lambda r: r.get("date", ""), reverse=True)[:60]
    save(S / "reports.json", reports, compact=True)
    cut = (now_tw() - timedelta(days=90)).strftime("%Y-%m-%d")
    gap = [g for g in (load(D / "gap.json", []) or []) if str(g.get("last_update", ""))[:10] >= cut]
    save(S / "gap.json", gap, compact=True)
    chips = load(D / "chips_summary.json", {}) or {}
    save(S / "chips.json", chips, compact=True)
    save(S / "chips_series.json", load(D / "chips_series.json", {}) or {}, compact=True)
    view = load(D / "macro.json", {}) or {}
    save(S / "macro.json", dict(board, ai_view=view if view.get("ai_engine") == config.ENGINE else {}), compact=True)

    runs = load(D / "runs.json", []) or []
    meta = {
        "built_at": iso_now(),
        "counts": {"themes": len(cards), "themes_claude": sum(c["engine"] == config.ENGINE for c in cards),
                   "wiki": len(wiki), "wiki_claude": sum(w.get("ai_engine") == config.ENGINE for w in wiki.values()),
                   "reports": len(reports), "gap": len(gap)},
        "latest": {"theme": max((c["date"] for c in cards), default=""), "report": reports[0].get("date", "") if reports else "",
                   "chips": chips.get("date", ""), "macro": board.get("line", {}).get("as_of", "")},
        "last_run": runs[-1] if runs else None,
    }
    save(S / "meta.json", meta)
    return meta


if __name__ == "__main__":
    m = build()
    print(m["counts"], m["latest"])
