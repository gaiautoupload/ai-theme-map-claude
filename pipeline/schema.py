"""題材地圖的正式欄位（新舊資料都轉成這個格式），以及給 Claude 的輸出規格。

平台的精神：投資人的獲利雷達＋預警牆。10 秒內回答——這是什麼題材、為什麼現在、市場多大、
先看哪 3 檔、誰真的賺得到錢（吃肉還是喝湯）、何時反映到營收。數字不准假精準：每個重要欄位標資料性質。
"""
from __future__ import annotations

from typing import Any

SOURCE_TYPES = {"official": "官方", "news_derived": "新聞", "analyst_estimate": "研究機構估計", "llm_inference": "AI 推論", "pending": "待補"}
STAGES = ["概念期", "驗證期", "小量出貨期", "放量期", "財報貢獻期", "退燒期"]
# 總經敏感因子：key → 戰情室指標（direction 由 Claude 給：positive＝這個指標上升對題材有利）
MACRO_FACTORS = {
    "us_rates": ("DGS10", "美債 10 年殖利率"), "real_yield": ("DFII10", "美債 10 年實質殖利率"), "policy_rate": ("DFF", "聯邦資金利率"),
    "usd_twd": ("DEXTAUS", "美元兌台幣（上升＝台幣貶）"), "usd_broad": ("DTWEXBGS", "美元廣義指數"), "oil": ("DCOILBRENTEU", "Brent 油價"),
    "credit_spread": ("BAMLH0A0HYM2", "高收益債利差"), "volatility": ("VIXCLS", "VIX"), "us_tech": ("NASDAQCOM", "Nasdaq"),
    "us_equity": ("SP500", "S&P 500"), "inflation": ("CPILFESL", "美國核心 CPI"), "jobs": ("PAYEMS", "美國非農就業"),
    "industrial": ("INDPRO", "美國工業生產"), "financial_conditions": ("NFCI", "金融情勢指數（上升＝收緊）"),
}

LIST_FIELDS = ["theme_tags", "heat_drivers", "risks", "watch_signals", "related_themes", "key_bottleneck", "primary_value_capture"]
OBJ_LIST_FIELDS = ["tech_lessons", "concepts", "structure_layers", "timeline_phases", "capital_flow", "stocks", "sources",
                   "trigger_events", "warnings", "macro_sensitivity"]
STOCK_TEXT = ["sector", "role", "timeframe", "desc", "pros", "cons", "catalyst", "ai_revenue_exposure", "ai_revenue_exposure_source_type",
              "gross_margin_impact", "customer_concentration", "pricing_power", "substitution_risk", "capacity_share_hint",
              "switching_cost", "revenue_visibility", "follower_reason", "market"]


def as_list(x: Any) -> list:
    if isinstance(x, list):
        return [i for i in x if i not in (None, "", {})]
    if isinstance(x, str) and x.strip():
        return [x.strip()]
    return []


def num(x: Any, lo: float, hi: float, default=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def source_type(x: Any) -> str:
    x = str(x or "").strip()
    if x in SOURCE_TYPES:
        return x
    return {"公司報告": "official", "官方": "official", "新聞": "news_derived", "待補": "pending", "": "pending"}.get(x, "llm_inference")


def norm_stock(s: dict) -> dict:
    """概念股欄位（舊資料的駝峰命名一併轉換）。"""
    g = lambda *ks: next((s[k] for k in ks if s.get(k) not in (None, "")), None)
    out = {k: str(g(k) or "").strip() for k in STOCK_TEXT}
    out.update({
        "code": str(g("code", "id", "ticker") or "").strip(),
        "name": str(g("name") or "").strip(),
        "timeframe": str(g("timeframe", "commercialization_phase") or "").strip(),
        "desc": str(g("desc", "reason", "linkage") or "").strip(),
        "pure_level": num(g("pure_level", "pureLevel"), 0, 5),
        "barrier_level": num(g("barrier_level", "barrierLevel"), 0, 5),
        "value_capture_score": num(g("value_capture_score"), 0, 5),
        "sole_supplier": bool(g("sole_supplier")) if g("sole_supplier") is not None else None,
        "priority": int(g("priority")) if str(g("priority") or "").isdigit() and 1 <= int(g("priority")) <= 3 else None,
        "follower": bool(g("follower")),
        "tier": "core" if g("tier", "stock_tier") in ("core", "Tier 1") else "extended",
        "evidence": "direct" if g("evidence", "evidence_type") == "direct" else "inferred",
        "evidence_urls": [u for u in as_list(g("evidence_urls")) if isinstance(u, str) and u.startswith("http")],
    })
    out["ai_revenue_exposure_source_type"] = source_type(out["ai_revenue_exposure_source_type"]) if out["ai_revenue_exposure"] else "pending"
    return out


def norm_source(x: Any) -> dict | None:
    if not isinstance(x, dict):
        return None
    url = x.get("url") or ""
    if not str(url).startswith("http"):
        return None
    return {"title": x.get("title") or x.get("label") or url, "url": url,
            "source_name": x.get("source_name") or "", "published_at": x.get("published_at") or ""}


def norm_theme(t: dict) -> dict:
    out = dict(t)
    for k in LIST_FIELDS:
        out[k] = [str(i) for i in as_list(t.get(k))]
    for k in OBJ_LIST_FIELDS:
        out[k] = [i for i in as_list(t.get(k)) if isinstance(i, dict) or (k == "trigger_events" and isinstance(i, str))]
    out["trigger_events"] = [e if isinstance(e, dict) else {"event": e} for e in out["trigger_events"]]
    out["stocks"] = [s for s in (norm_stock(s) for s in out["stocks"]) if s["code"] and s["name"]]
    out["sources"] = [s for s in (norm_source(x) for x in out["sources"]) if s]
    out["macro_sensitivity"] = [m for m in out["macro_sensitivity"] if m.get("factor") in MACRO_FACTORS]
    out["heat_score"] = int(num(t.get("heat_score"), 0, 100, 50))
    out["summary"] = t.get("summary") or t.get("desc") or ""
    out["one_liner"] = t.get("one_liner") or out.get("thesis") or out["summary"]
    for k in ("market_size_tam", "market_cagr"):
        out[k + "_source_type"] = source_type(t.get(k + "_source_type")) if out.get(k) not in (None, "", "待查", "未有可信估計") else "pending"
    for k in ("desc", "representative_stocks", "content_quality_note", "evidence_summary", "icon", "color",
              "topic_definition", "plain_language_intro", "evolution_points", "theme_name", "who_makes_money"):
        out.pop(k, None)
    return out


SOURCE_RULE = """資料性質（source_type）只能是：official（政府、交易所、公司公告或財報）、news_derived（新聞報導）、
analyst_estimate（研究機構或券商估計，要寫機構名稱）、llm_inference（你自己的推論）、pending（查不到）。
市場規模、成長率、營收占比、市占這類數字：沒有可信出處就填「未有可信估計」並標 pending，絕對不要編造精確數字。"""

THEME_SPEC = """{
 "title": "題材名稱（30 字內）",
 "group": "大類：AI 與半導體、通訊與太空、能源與基建、國防與地緣、生技醫療、汽車與機器人、消費與內需、金融與政策、原物料與航運 擇一",
 "one_liner": "一句話投資論點（卡片與標題下方用，30 字內）",
 "summary": "這是什麼題材，白話 80 字內",
 "thesis": "投資論點：價值會流向哪裡、誰吃肉誰喝湯（150 字內）",
 "why_now": "為什麼是現在：一兩句、含關鍵日期（120 字內；事件細節放 trigger_events）",
 "heat": "火熱｜升溫｜持平｜降溫",
 "heat_score": 0到100的整數（近期新聞密度、資金關注、催化劑強度）,
 "theme_stage": "概念期｜驗證期｜小量出貨期｜放量期｜財報貢獻期｜退燒期",
 "investment_phase": "目前在本夢比還是本益比階段，一句話",
 "period": "主要受惠期間，例如 2026-2028",
 "market_size_tam": "市場規模（含年份、幣別，30 字內），或「未有可信估計」；說明放 _source",
 "market_size_tam_source_type": "見資料性質規則",
 "market_size_tam_source": "出處（機構＋年份）",
 "market_cagr": "年複合成長率，或「未有可信估計」",
 "market_cagr_source_type": "見資料性質規則",
 "market_cagr_source": "出處",
 "market_narrative": "市場目前怎麼看這個題材",
 "evidence_confidence": "高｜中｜低",
 "key_bottleneck": ["關鍵瓶頸，每點 40 字內"],
 "primary_value_capture": ["價值主要被哪一層、哪類公司拿走，每點 40 字內"],
 "theme_tags": ["3到6個標籤"],
 "trigger_events": [{"date": "YYYY-MM-DD", "event": "觸發事件", "source_url": "https://..."}],
 "heat_drivers": ["熱度驅動因子"],
 "warnings": [{"signal": "預警訊號（例如題材退燒、估值過熱、替代技術、客戶砍單）", "level": "高｜中｜低", "detail": "說明與要看的數據"}],
 "risks": ["主要風險"],
 "watch_signals": ["接下來要觀察的訊號或數據（驗證節點）"],
 "related_themes": ["相關題材"],
 "macro_sensitivity": [{"factor": "us_rates｜real_yield｜policy_rate｜usd_twd｜usd_broad｜oil｜credit_spread｜volatility｜us_tech｜us_equity｜inflation｜jobs｜industrial｜financial_conditions 擇一", "direction": "positive（這個指標上升對題材有利）或 negative", "why": "傳導邏輯一句話"}],
 "structure_layers": [{"name": "價值鏈層級", "position": "在鏈上的位置", "summary": "", "key_points": [""], "beneficiaries": ["代表公司（台股寫簡稱）"], "pricing_power": "高｜中｜低", "margin_profile": "毛利結構", "value_capture": "高｜中｜低（吃肉還是喝湯）", "entry_barrier": "進入門檻", "leader_type": "什麼樣的公司會贏"}],
 "timeline_phases": [{"phase": "概念期｜驗證期｜小量出貨期｜放量期｜財報貢獻期", "timeframe": "例如 2026H1", "summary": "", "investment_phase": "本夢比／本益比的位置", "revenue_meaning": "對營收的意義", "watch_metric": "這階段要看的指標", "expected_market_focus": "市場會關注什麼", "winners": [""], "is_current": true或false}],
 "capital_flow": [{"phase": "", "timeframe": "", "focus": "資金先流向哪裡", "logic": "為什麼", "beneficiary_groups": [""]}],
 "tech_lessons": [{"title": "產業投資邏輯", "subtitle": "", "problem": "要解決的問題", "mechanism": "技術或商業機制", "why_now": "", "desc": "白話說明"}],
 "sources": [{"title": "文章標題", "url": "https://...", "source_name": "媒體或機構", "published_at": "YYYY-MM-DD"}]
}"""

STOCK_SPEC = """{
 "stocks": [{
  "code": "台股代號", "name": "公司簡稱", "sector": "細分產業",
  "priority": 1到3（最值得先看的前三檔才填，其餘填 null）,
  "role": "受惠位置／供應鏈角色",
  "tier": "core（有報導或公告直接連到這個題材）或 extended（依產業鏈推論）",
  "follower": true或false（只是跟風：相關營收很小、靠題材想像）, "follower_reason": "跟風的原因，非跟風留空",
  "timeframe": "營收放量時程，例如 2026H1 驗證／2026H2 放量",
  "pure_level": 0到5（題材純度）, "barrier_level": 0到5（技術或客戶壁壘）, "value_capture_score": 0到5（吃肉程度）,
  "desc": "為什麼受惠，60 字內",
  "pros": "投資亮點", "cons": "風險提醒", "catalyst": "股價催化／驗證事件",
  "ai_revenue_exposure": "題材相關營收占比（有出處才寫數字，否則「未揭露」）", "ai_revenue_exposure_source_type": "見資料性質規則",
  "gross_margin_impact": "毛利率彈性", "customer_concentration": "客戶集中度", "sole_supplier": true或false,
  "pricing_power": "高｜中｜低", "substitution_risk": "高｜中｜低", "switching_cost": "高｜中｜低",
  "revenue_visibility": "高｜中｜低", "capacity_share_hint": "產能或市占線索（沒出處就寫定性描述）",
  "evidence_urls": ["提到這家公司與這個題材關聯的報導或公告網址"]
 }]
}"""
