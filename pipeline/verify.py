"""概念股與連動股票的核對：Claude 說的關聯，系統要自己去出處網頁看過才算數。

- 題材概念股：逐一打開 evidence_urls，網頁內文要出現公司簡稱、全名或代號才算「出處已核對」。
  核心（core）只給出處已核對的股票；沒核對到的降為延伸，標「出處待核對」，不刪除。
- 預期落差：連動股票必須在那則新聞內文裡被提到，沒提到的移除。
- 代號與名稱一律以官方代號表為準（registry.match）。
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import requests

from . import config
from .registry import get as get_reg, match
from .store import iso_now, load, log_event, save

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
     "Accept-Language": "zh-TW,zh;q=0.9"}
CACHE = config.CACHE / "page_text.json"


def _text(url: str, cache: dict) -> str:
    if url in cache:
        return cache[url]
    try:
        r = requests.get(url, headers=H, timeout=12)
        r.encoding = r.apparent_encoding or r.encoding
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S | re.I) if r.ok else ""
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"\s+", " ", t)[:400_000]
    except Exception:
        t = ""
    cache[url] = t
    return t


def _names(code: str, name: str, reg: dict) -> list[str]:
    r = reg.get(code, {})
    out = {code, name, r.get("name", ""), *r.get("aliases", [])}
    return [n for n in out if n and len(n) >= 2]


def mentions(text: str, code: str, name: str, reg: dict) -> bool:
    if not text:
        return False
    # 名稱（簡稱、全名、英文名）出現才算；代號只認「(2383)」「2383.TW」「2383-TW」這種明確寫法，避免數字巧合
    return any(n in text for n in _names(code, name, reg) if n != code) or bool(re.search(rf"[（(]\s*{re.escape(code)}\s*[)）]|{re.escape(code)}[.-]TW", text))


def verify_themes(only_ids: set | None = None) -> str:
    themes, reg = load(config.DATA / "themes.json", {}) or {}, get_reg()
    cache = load(CACHE, {}) or {}
    jobs = []
    for tid, t in themes.items():
        if t.get("ai_engine") != config.ENGINE or (only_ids and tid not in only_ids):
            continue
        for s in t.get("stocks", []):
            jobs += [u for u in s.get("evidence_urls", [])[:4] if u not in cache]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda u: _text(u, cache), dict.fromkeys(jobs)))
    checked = verified = downgraded = removed = 0
    for tid, t in themes.items():
        if t.get("ai_engine") != config.ENGINE or (only_ids and tid not in only_ids):
            continue
        # 出處除了提到公司，也要提到這個題材（任一標籤或標題關鍵詞），才算「關聯已核對」
        terms = [w for w in {*t.get("theme_tags", []), *re.split(r"[\s：:、，,（）()／/與和的及]+", t.get("title", ""))} if len(w) >= 2]
        keep = []
        for s in t.get("stocks", []):
            r = match(s["code"], s["name"], reg)
            if not r:  # 代號名稱對不上官方表：移除
                removed += 1
                continue
            s["name"], s["market"] = r["name"], r["market"]
            ok_urls = [u for u in s.get("evidence_urls", [])[:4]
                       if mentions(cache.get(u, ""), s["code"], s["name"], reg) and any(w in cache.get(u, "") for w in terms)]
            s["evidence_verified"] = ok_urls
            s["evidence"] = "direct" if ok_urls else "inferred"
            checked += 1
            verified += bool(ok_urls)
            if s.get("tier") == "core" and not ok_urls:
                s["tier"], s["evidence_note"] = "extended", "Claude 標為核心，但出處網頁沒有同時提到這家公司與題材（或網站擋住讀取），先列為延伸"
                downgraded += 1
            if s.get("priority") and not ok_urls:  # 「先看」只給出處已核對的股票
                s["priority_unverified"], s["priority"] = s["priority"], None
            keep.append(s)
        t["stocks"], t["verified_at"] = keep, iso_now()
    save(config.DATA / "themes.json", themes)
    save(CACHE, {k: v for k, v in list(cache.items())[-3000:]}, compact=True)
    note = f"核對 {checked} 檔概念股：出處確認 {verified}、核心降為延伸 {downgraded}、代號不符移除 {removed}"
    log_event("verify_themes", ok=True, note=note)
    return note


def verify_gaps() -> str:
    """預期落差的連動股票：只留新聞內文有提到的（Claude 新產生的才檢查，舊資料另外標示）。"""
    gaps, reg = load(config.DATA / "gap.json", []) or [], get_reg()
    cache = load(CACHE, {}) or {}
    removed = kept = 0
    for g in gaps:
        if g.get("ai_engine") != config.ENGINE or g.get("stocks_verified") or not g.get("source_url"):
            continue
        text = _text(g["source_url"], cache)
        out = []
        for x in g.get("concept_stocks", []):
            p = str(x).split(" ", 1)
            if len(p) == 2 and match(p[0], p[1], reg) and mentions(text, p[0], p[1], reg):
                out.append(f"{p[0]} {reg[p[0]]['name']}")
            else:
                removed += 1
        kept += len(out)
        g["concept_stocks"], g["stocks_verified"] = out, bool(text)
    save(config.DATA / "gap.json", gaps)
    save(CACHE, {k: v for k, v in list(cache.items())[-3000:]}, compact=True)
    return f"預期落差連動股：保留 {kept}、移除 {removed}（新聞內文沒提到或代號不符）"
