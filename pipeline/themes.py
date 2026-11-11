"""題材：Claude 上網找出今天值得研究的題材（含退燒預警），再逐一研究成完整地圖，概念股逐檔比對官方代號表。

每個題材兩次 Claude 呼叫：
1. 研究（上網）：投資論點、為什麼是現在、TAM/CAGR（附出處與資料性質）、價值鏈、投資節奏、資金輪動、預警、總經敏感度。
2. 概念股（上網）：受惠位置、優先關注前三檔、跟風股、投資欄位與出處網址；代號名稱對不上官方表的退回重寫一次，還錯就剔除。
同一個標題永遠寫回同一個 ID（重新分析＝覆蓋），不再越堆越多。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import config
from .claude_cli import ClaudeError, ask_json, require
from .macro_bridge import snapshot_text
from .registry import get as get_reg, match
from .schema import SOURCE_RULE, STOCK_SPEC, THEME_SPEC, norm_theme
from .store import iso_now, load, log_event, save, theme_id, today

PATH = config.DATA / "themes.json"
ANALYST = ("你是台股的 buy-side 產業研究員，替投資人做「獲利雷達＋預警牆」。先講商業價值，不要先講技術教學："
           "這是什麼題材、為什麼是現在、市場多大、誰有定價權、誰賺最多（吃肉還是喝湯）、何時反映到營收；"
           "同時誠實指出跟風股、退燒與替代風險。用投資人看得懂的繁體中文，不要堆技術名詞。")


def discover(themes: dict, macro: dict) -> dict:
    """今天要研究哪些題材（新的或要更新的）、哪些題材在退燒。"""
    seeds = load(config.DATA / "seeds.json", {}) or {}
    recent = sorted(themes.values(), key=lambda t: t.get("updated_at", ""), reverse=True)[:120]
    existing = "\n".join(f"- {t['id']}｜{t['title']}｜{t.get('date', '')}｜熱度 {t.get('heat_score')}" for t in recent)
    seed_text = "\n".join(f"- {g['group']}：{'；'.join(g['themes'])}" for g in seeds.get("seed_groups", []))
    prompt = f"""{ANALYST}

今天是 {today()}（台灣時間）。請用網路搜尋近 7 天的國際與台灣財經新聞、法說會、產業報導，找出台股投資人「現在」最該研究的題材。

## 目前的總經環境（真實數據）
{snapshot_text(macro)}

## 參考的題材種子（可以不用）
{seed_text}

## 站上已有的題材（ID｜標題｜日期｜熱度）
{existing}

## 要做的事
1. 挑出 {config.THEMES_PER_RUN} 個最值得研究的題材，至少跨 3 個大類。跟站上已有題材是同一件事的，填它的 existing_id（代表要更新），不要另開新題材。
2. 列出站上已有、但近期明顯退燒或論點被打破的題材（最多 5 個），當作預警。
3. 每個選擇都要有近期、具體、附日期的新聞依據。

輸出：
{{"macro_brief": ["今天的總經與市場重點，3 點"],
 "selected": [{{"title": "題材名稱", "group": "大類", "why_now": "為什麼是現在（含日期）", "existing_id": "已有題材的 ID 或 null", "priority_score": 0到100, "evidence_urls": ["https://..."]}}],
 "cooling": [{{"existing_id": "ID", "reason": "退燒或論點被打破的原因", "evidence_url": "https://..."}}]}}"""
    d = ask_json("題材發掘", prompt, web=True, effort="high", validate=require("selected", lists=("selected",)))
    d["selected"] = [s for s in d.get("selected", []) if isinstance(s, dict) and s.get("title")][: config.THEMES_PER_RUN]
    save(config.DATA / "discovery.json", dict(d, updated_at=iso_now()))
    return d


def _research(seed: dict, old: dict | None) -> dict:
    prev = f"\n## 這個題材之前的版本（可能過時，要重新查證）\n標題：{old['title']}\n摘要：{old.get('summary', '')}\n" if old else ""
    prompt = f"""{ANALYST}

今天是 {today()}。請上網查證後，把下面這個題材研究成一張投資地圖。

## 題材
{seed['title']}（{seed.get('group', '')}）
為什麼是現在（初步線索）：{seed.get('why_now', '')}
{prev}
## 規則
- 重要事實與數字都要來自你這次搜尋到的報導或官方資料，放進 sources（至少 4 筆，要有網址與日期）。
- {SOURCE_RULE}
- structure_layers 3 到 6 層，標出每層的定價權與價值捕獲（吃肉還是喝湯）。
- timeline_phases 用投資節奏（概念期→驗證期→小量出貨期→放量期→財報貢獻期），標出目前在哪一段（is_current）。
- warnings 寫真正的預警（不是泛泛的風險），沒有就給空陣列。
- macro_sensitivity 列 2 到 4 個最相關的總經因子與方向。

## 輸出格式
{THEME_SPEC}"""
    return ask_json(f"題材研究：{seed['title']}", prompt, web=True, effort="high",
                    validate=require("title", "thesis", "why_now", "summary", lists=("structure_layers", "timeline_phases", "sources")))


def _stocks(t: dict, reg: dict) -> list:
    layers = "\n".join(f"- {l.get('name')}：{l.get('summary', '')}（代表：{'、'.join(l.get('beneficiaries', []))}）" for l in t.get("structure_layers", []))
    base = f"""{ANALYST}

今天是 {today()}。題材「{t['title']}」的投資論點：{t.get('thesis', '')}
價值鏈：
{layers}

請上網查證，列出這個題材的台股概念股（上市或上櫃，6 到 15 檔），要包含：
- 最值得先看的前三檔（priority 1–3），理由要能讓投資人 10 秒看懂。
- 真正吃到價值的公司，也要誠實標出只是跟風的（follower=true）。
- tier=core 只給有報導或公告直接連到這個題材的公司，evidence_urls 放那些網址；推論的標 extended。
- {SOURCE_RULE}
- code 必須是正確的台股代號，name 用公司簡稱。

## 輸出格式
{STOCK_SPEC}"""

    def bad_codes(d):
        if not isinstance(d, dict) or not isinstance(d.get("stocks"), list) or not d["stocks"]:
            return "stocks 必須是非空陣列"
        wrong = [f"{s.get('code')} {s.get('name')}" for s in d["stocks"] if isinstance(s, dict) and not match(s.get("code", ""), s.get("name", ""), reg)]
        return f"這些代號和公司名稱對不上官方代號表，請更正代號或刪除：{'、'.join(wrong)}" if wrong else None

    try:
        d = ask_json(f"概念股：{t['title']}", base, web=True, effort="high", validate=bad_codes, retries=1)
    except ClaudeError:
        d = ask_json(f"概念股（容錯）：{t['title']}", base, web=True, effort="high", validate=require(lists=("stocks",)), retries=0)
    out = []
    for s in d.get("stocks", []):
        r = match(s.get("code", ""), s.get("name", ""), reg) if isinstance(s, dict) else None
        if r and not r.get("etf"):
            out.append(dict(s, code=str(s["code"]).strip(), name=r["name"], market=r["market"]))
    log_event("theme_stocks", title=t["title"], proposed=len(d.get("stocks", [])), kept=len(out))
    return out


def analyze(seed: dict, themes: dict, reg: dict) -> dict:
    old = themes.get(seed.get("existing_id") or "") or themes.get(theme_id(seed["title"]))
    raw = _research(seed, old)
    raw["stocks"] = _stocks(raw, reg)
    t = norm_theme(raw)
    t["id"] = old["id"] if old else theme_id(t["title"])
    t["group"] = t.get("group") or seed.get("group") or (old or {}).get("group") or "未分類"
    t.update({"ai_engine": config.ENGINE, "date": today(), "updated_at": iso_now(), "model": config.CLAUDE_MODEL})
    if old:
        t["first_seen"] = old.get("first_seen") or old.get("date")
    return t


def run(themes: dict, macro: dict) -> str:
    reg = get_reg()
    found = discover(themes, macro)
    seeds = list(found["selected"])
    # 另外重寫幾個還是舊模型的題材（從最近的開始）
    picked = {s.get("existing_id") for s in seeds}
    stale = sorted((t for t in themes.values() if t.get("ai_engine") != config.ENGINE and t["id"] not in picked),
                   key=lambda t: t.get("date", ""), reverse=True)[: config.REFRESH_THEMES_PER_RUN]
    seeds += [{"title": t["title"], "group": t.get("group", ""), "why_now": t.get("why_now", ""), "existing_id": t["id"]} for t in stale]

    done, failed = [], []
    with ThreadPoolExecutor(config.CLAUDE_WORKERS) as ex:
        futs = {ex.submit(analyze, s, themes, reg): s for s in seeds}
        for f, s in futs.items():
            try:
                t = f.result()
                themes = load(PATH, {}) or {}  # 每做完一個就寫回（中途失敗也保留已完成的）
                themes[t["id"]] = t
                save(PATH, themes)
                done.append(t["title"])
            except Exception as e:
                failed.append(f"{s['title']}（{str(e)[:120]}）")
                log_event("theme", ok=False, title=s["title"], error=str(e)[:300])
    # 退燒預警寫回題材
    themes = load(PATH, {}) or {}
    for c in found.get("cooling", []):
        t = themes.get(c.get("existing_id") or "")
        if t:
            t["cooling"] = {"date": today(), "reason": c.get("reason", ""), "evidence_url": c.get("evidence_url", "")}
    save(PATH, themes)
    note = f"完成 {len(done)} 個題材" + (f"；失敗 {len(failed)}：{'；'.join(failed)}" if failed else "")
    if failed and not done:
        raise ClaudeError(note)
    return note
