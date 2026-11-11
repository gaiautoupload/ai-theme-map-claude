"""總經：直接讀「興櫃總經戰情室」（emerging_intelligence）已產出的總金線與總經指標（只讀，不重抓、不改它的資料）。

產出 data/macro_board.json：
- line：總金線（0–100 風險環境分數、方向、四個組成、歷史）
- regime：跨市場環境判定（防守／中性…）與新增曝險建議
- indicators：利率、油價、匯率、信用利差、VIX、通膨、就業、台灣市場，附資料日期與出處
- calendar：未來 30 天的重要總經事件
- factors：每個總經因子現在是上升、下降還是持平（題材的總經敏感度用這個算順風／逆風）
本機路徑、雜湊這類欄位不帶出去。
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from . import config
from .schema import MACRO_FACTORS
from .store import load, log_event, now_tw, save

SRC = Path(os.environ.get("THEMEMAP_MACRO_DIR", str(config.ROOT.parent / "emerging_intelligence" / "data")))
RATE_UNITS = ("percent", "percentage_points")
FLAT = {"rate_bp": 5.0, "pct": 1.0}


def _hist(rows, n=120):
    return [[r["date"], r["value"]] for r in (rows or []) if r.get("value") is not None][-n:]


def _trend(ind: dict) -> tuple[str, str]:
    """依資料頻率看近期方向：日資料比 20 筆前、週資料 4 筆、月資料 3 筆；物價看年增率是否上升。"""
    h = ind.get("history") or []
    if len(h) < 4:
        return "unknown", "資料不足"
    freq, unit, key = ind.get("frequency", "daily"), str(ind.get("unit", "")), ind["key"]
    back = {"daily": 20, "weekly": 4, "monthly": 3}.get(freq, 20)
    if key in ("CPILFESL", "CPIAUCSL", "PCEPI", "PCEPILFE") and len(h) >= 16:
        yoy = lambda i: (h[i][1] / h[i - 12][1] - 1) * 100
        d = yoy(-1) - yoy(-4)
        return ("up" if d > 0.1 else "down" if d < -0.1 else "flat"), f"年增率 {yoy(-1):.2f}%（3 個月前 {yoy(-4):.2f}%）"
    old, new = h[-1 - min(back, len(h) - 1)][1], h[-1][1]
    label = {"daily": f"近 {back} 個交易日", "weekly": f"近 {back} 週", "monthly": f"近 {back} 個月"}.get(freq, "")
    if any(u in unit for u in RATE_UNITS) or key in ("NFCI",):
        d = (new - old) * (100 if key != "NFCI" else 1)
        flat = FLAT["rate_bp"] if key != "NFCI" else 0.05
        txt = f"{label} {d:+.0f}bp" if key != "NFCI" else f"{label} {d:+.2f}"
        return ("up" if d > flat else "down" if d < -flat else "flat"), txt
    if not old:
        return "unknown", "資料不足"
    d = (new / old - 1) * 100
    flat = 5.0 if key == "VIXCLS" else FLAT["pct"] if freq == "daily" else 0.1
    return ("up" if d > flat else "down" if d < -flat else "flat"), f"{label} {d:+.2f}%"


def build() -> dict:
    line, ctx = load(SRC / "macro_line" / "latest.json", {}) or {}, load(SRC / "macro" / "latest.json", {}) or {}
    ext, tw = load(SRC / "macro_extended" / "latest.json", {}) or {}, load(SRC / "macro_taiwan" / "latest.json", {}) or {}
    cal, src = load(SRC / "macro_calendar" / "latest.json", {}) or {}, load(SRC / "macro" / "source_latest.json", {}) or {}
    if not line and not ctx:
        log_event("macro", ok=False, error=f"讀不到總經資料：{SRC}")
        return {}
    series = src.get("series", {}) or {}
    ind = {}
    for k, v in (ctx.get("indicators") or {}).items():
        ind[k] = {"key": k, "label": v.get("label"), "group": "market", "frequency": "daily", "unit": v.get("unit"), "value": v.get("value"),
                  "date": v.get("observation_date"), "status": v.get("status"), "source_url": v.get("source_url"),
                  "history": _hist((series.get(k) or {}).get("observations"))}
    for k, v in (ext.get("indicators") or {}).items():
        ind[k] = {"key": k, "label": v.get("label"), "group": v.get("group"), "frequency": v.get("frequency"), "unit": v.get("unit"),
                  "value": v.get("value"), "date": v.get("observation_date"), "status": v.get("status"), "source_url": v.get("documentation_url") or v.get("source_url"),
                  "meaning": v.get("meaning") or v.get("interpretation"), "yoy_pct": v.get("yoy_pct"), "history": _hist(v.get("history"), 60)}
    for k, v in (tw.get("indicators") or {}).items():
        ind[k] = {"key": k, "label": v.get("label"), "group": "taiwan", "frequency": "daily", "unit": v.get("unit"), "value": v.get("value"),
                  "date": v.get("observation_date"), "status": v.get("status"), "source_url": v.get("source_url"),
                  "meaning": v.get("interpretation"), "history": _hist(v.get("history"), 60)}
    for v in ind.values():
        v["trend"], v["trend_text"] = _trend(v)

    factors = {}
    for f, (k, label) in MACRO_FACTORS.items():
        if k in ind:
            factors[f] = {"indicator": k, "label": label, "trend": ind[k]["trend"], "text": ind[k]["trend_text"], "date": ind[k]["date"]}

    until = (now_tw() + timedelta(days=30)).strftime("%Y-%m-%d")
    today = now_tw().strftime("%Y-%m-%d")
    board = {
        "available_at": max(str(x.get("available_at") or x.get("generated_at") or "") for x in (line, ctx, ext, tw, cal)),
        "source": "興櫃總經戰情室（FRED、證交所、BLS、FOMC 官方資料）",
        "line": {k: line.get(k) for k in ("as_of", "score", "previous_score", "label", "signal", "line_direction", "change_1", "change_5", "status")}
                | {"components": {k: {"score": c.get("score"), "weight": c.get("weight"), "description": c.get("description")} for k, c in (line.get("components") or {}).items()},
                   "history": [[h["date"], h.get("score"), h.get("label")] for h in line.get("history", []) if h.get("score") is not None],
                   "limitations": (line.get("limitations") or [])[:4]},
        "regime": {"regime": ctx.get("regime"), "status": ctx.get("status"), "coverage": ctx.get("coverage"),
                   "new_entry_guidance": ctx.get("new_entry_guidance"), "holding_guidance": ctx.get("holding_guidance"),
                   "signals": ctx.get("signals"), "yield_curve_10y_2y_bp": ctx.get("yield_curve_10y_2y_bp"), "decision_at": ctx.get("decision_at")},
        "indicators": ind,
        "calendar": [{k: e.get(k) for k in ("date", "title", "period", "importance", "category", "start_at", "source_url")}
                     for e in cal.get("events", []) if today <= str(e.get("date", "")) <= until],
        "factors": factors,
    }
    save(config.DATA / "macro_board.json", board)
    log_event("macro", ok=True, line=board["line"].get("as_of"), regime=board["regime"].get("regime"), indicators=len(ind))
    return board


def macro_fit(theme: dict, factors: dict) -> dict:
    """題材的總經順逆風：Claude 標的敏感方向 × 指標目前的方向。"""
    rows, tail, head = [], 0, 0
    for m in theme.get("macro_sensitivity", []):
        f = factors.get(m.get("factor"))
        if not f:
            continue
        sign = 1 if m.get("direction") == "positive" else -1
        t = {"up": 1, "down": -1}.get(f["trend"], 0)
        effect = "tailwind" if sign * t > 0 else "headwind" if sign * t < 0 else "neutral"
        tail += effect == "tailwind"
        head += effect == "headwind"
        rows.append({"factor": m["factor"], "label": f["label"], "direction": m.get("direction"), "why": m.get("why", ""),
                     "trend": f["trend"], "text": f["text"], "date": f["date"], "effect": effect})
    verdict = "tailwind" if tail > head else "headwind" if head > tail else "mixed" if rows else ""
    return {"verdict": verdict, "tail": tail, "head": head, "rows": rows}


def snapshot_text(board: dict) -> str:
    """給 Claude 的總經摘要（真實數據，附日期），避免它自己編總經數字。"""
    if not board:
        return "（總經資料暫時讀不到）"
    l, r = board.get("line", {}), board.get("regime", {})
    zh = {"defensive": "防守", "neutral": "中性", "mixed": "分歧", "supportive": "偏多", "risk_on": "偏多", "risk_off": "防守", "pressure": "承壓",
          "unknown": "資料不足", "shock_review": "急變待查", "rising": "往上", "falling": "往下", "flat": "持平", "stable": "穩定",
          "equities": "股市", "rates": "利率", "fx": "匯率", "oil": "油價", "hong_kong": "香港資金"}
    t = lambda x: zh.get(str(x), x)
    lines = [f"總金線 {l.get('as_of')}：{l.get('score') and round(l['score'], 1)} 分（0–100 風險環境，非上漲機率），{l.get('label')}，方向{t(l.get('line_direction'))}",
             f"跨市場環境：{t(r.get('regime'))}；新增曝險建議：{r.get('new_entry_guidance')}"]
    for k, s in (r.get("signals") or {}).items():
        lines.append(f"- {t(k)}：{t(s.get('state'))}；{s.get('reason')}")
    for v in board.get("indicators", {}).values():
        if v.get("value") is not None:
            lines.append(f"- {v['label']}：{v['value']}（{v.get('date')}，{v.get('trend_text')}）")
    return "\n".join(lines)


if __name__ == "__main__":
    b = build()
    print(b.get("line", {}).get("as_of"), b.get("regime", {}).get("regime"), len(b.get("indicators", {})), "項指標")
    for k, f in b.get("factors", {}).items():
        print(k, f["trend"], f["text"], f["date"])
