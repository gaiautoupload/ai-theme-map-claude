"""一次性：從舊站（gaiautoupload/ai-theme-map-site）匯入資料當起點，之後由 Claude 逐日重寫。

清理舊資料的已知問題：
- 主題重複累積：同標題只留最新一版（428 → 去重）。
- 補位概念股：舊產線用關鍵字補進來的「同主題供應鏈延伸受惠」股票全部拿掉。
- 亂數填的 TAM／CAGR：等於舊程式隨機池裡的數值就改成「待查」，不當成真資料。
- 籌碼資料庫的週末日期（上櫃 API 不認日期，週末存到前一交易日的資料）刪掉。
所有匯入的 AI 內容標 ai_engine=legacy-vllm，網站上會標示「舊模型」。

用法：python -m pipeline.legacy_import <舊站資料夾>
"""
from __future__ import annotations

import ast
import re
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

from . import config
from .schema import norm_theme
from .store import load, log_event, norm_title, save, theme_id

PADDING_ROLE = "同主題供應鏈延伸受惠"


def _pools(src: Path) -> tuple[set, set]:
    """讀出舊程式 patch_missing_tam_cagr.py 的隨機池（用來辨識假數字）。"""
    text = (src / "patch_missing_tam_cagr.py").read_text(encoding="utf-8") if (src / "patch_missing_tam_cagr.py").exists() else ""
    get = lambda name: set(ast.literal_eval(m.group(1))) if (m := re.search(name + r"\s*=\s*(\[.*?\])", text, re.S)) else set()
    return get("tam_pool"), get("cagr_pool")


def import_themes(src: Path) -> dict:
    raw = load(src / "maps_repo.json", {})
    tam_pool, cagr_pool = _pools(src)
    best: dict = {}
    for v in raw.values():
        if not isinstance(v, dict) or not isinstance(v.get("title"), str) or not isinstance(v.get("stocks"), list):
            continue
        key = norm_title(v["title"])
        stamp = v.get("updated_at") or v.get("date") or ""
        if key not in best or stamp > (best[key].get("updated_at") or best[key].get("date") or ""):
            best[key] = v
    out = {}
    for v in best.values():
        v = dict(v)
        v["stocks"] = [s for s in v.get("stocks", []) if s.get("role") != PADDING_ROLE and not str(s.get("desc", "")).startswith("依主題")]
        for k, pool in (("market_size_tam", tam_pool), ("market_cagr", cagr_pool)):
            if v.get(k) in pool or str(v.get(k, "")).startswith("待補"):
                v[k] = "待查"
                v[k + "_source"] = "舊資料無可信出處"
            else:
                v[k + "_source"] = v.pop(k + "_source_type", "") if v.get(k + "_source_type") not in ("待補", None) else ""
        t = norm_theme(v)
        for k in ("market_size_tam", "market_cagr"):  # 舊資料沒有可核對的出處：有數字的一律當 AI 推論
            if t[k + "_source_type"] != "pending":
                t[k + "_source_type"] = "llm_inference"
        t["id"] = theme_id(t["title"])
        t["ai_engine"] = config.LEGACY_ENGINE
        t["date"] = t.get("date") or str(t.get("updated_at", ""))[:10]
        out[t["id"]] = t
    return out


def import_wiki(src: Path) -> dict:
    out = {}
    for code, w in (load(src / "stocks_wiki.json", {}) or {}).items():
        w = dict(w)
        w["ai_engine"] = config.LEGACY_ENGINE
        w["products"] = list(dict.fromkeys(w.get("products") or []))[:6]  # 舊版用 set 打亂順序，去重保序
        out[str(code)] = w
    return out


def import_chips(src: Path) -> int:
    """複製籌碼資料庫，刪掉週末日期的假資料。"""
    db = config.DATA / "chips.db"
    shutil.copyfile(src / "institutional_chips.db", db)
    con = sqlite3.connect(db)
    dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM chips_history")]
    weekend = [d for d in dates if len(d) == 8 and date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() >= 5]
    with con:
        con.executemany("DELETE FROM chips_history WHERE date=?", [(d,) for d in weekend])
    con.execute("VACUUM")
    con.close()
    return len(weekend)


def main(src_dir: str) -> None:
    src = Path(src_dir)
    config.DATA.mkdir(parents=True, exist_ok=True)
    themes = import_themes(src)
    save(config.DATA / "themes.json", themes)
    wiki = import_wiki(src)
    save(config.DATA / "stocks_wiki.json", wiki)
    reports = [dict(r, ai_engine=config.LEGACY_ENGINE) for r in (load(src / "market_reports.json", []) or [])]
    save(config.DATA / "reports.json", reports)
    gap = [dict(g, ai_engine=config.LEGACY_ENGINE) for g in (load(src / "expectations_gap.json", []) or [])]
    save(config.DATA / "gap.json", gap)
    macro = load(src / "macro_ai_analysis.json", {}) or {}
    if macro:
        save(config.DATA / "macro.json", dict(macro, ai_engine=config.LEGACY_ENGINE))
    for name, dst in (("theme_seeds.json", "seeds.json"), ("ticker_registry_tw.json", "registry.json"),
                      ("institutional_chips_summary.json", "chips_summary.json")):
        if (src / name).exists():
            shutil.copyfile(src / name, config.DATA / dst)
    removed = import_chips(src)
    log_event("legacy_import", ok=True, themes=len(themes), wiki=len(wiki), reports=len(reports), gap=len(gap), weekend_dates_removed=removed)
    stocks = sum(len(t["stocks"]) for t in themes.values())
    print(f"主題 {len(themes)}（去重後），概念股列 {stocks}；個股 wiki {len(wiki)}；日報 {len(reports)}；預期落差 {len(gap)}；刪除週末籌碼日期 {removed} 天")


if __name__ == "__main__":
    main(sys.argv[1])
