"""上市櫃代號表（官方 OpenAPI）：AI 給的概念股一律要對得上這份表才收。抓不到就沿用上一份。"""
from __future__ import annotations

import requests

from . import config
from .store import iso_now, load, log_event, save

PATH = config.DATA / "registry.json"
TWSE = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"          # 上櫃公司基本資料（有產業別）
TPEX_QUOTES = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"  # 備援：只有代號與名稱
INDUSTRY = {
    "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織纖維", "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷",
    "09": "造紙", "10": "鋼鐵", "11": "橡膠", "12": "汽車", "14": "建材營造", "15": "航運", "16": "觀光餐旅",
    "17": "金融保險", "18": "貿易百貨", "19": "綜合", "20": "其他", "21": "化學", "22": "生技醫療", "23": "油電燃氣",
    "24": "半導體", "25": "電腦及週邊設備", "26": "光電", "27": "通信網路", "28": "電子零組件", "29": "電子通路",
    "30": "資訊服務", "31": "其他電子", "32": "文化創意", "33": "農業科技", "34": "電子商務", "35": "綠能環保",
    "36": "數位雲端", "37": "運動休閒", "38": "居家生活", "80": "管理股票", "91": "存託憑證",
}


def _get(url: str):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def _row(name: str, market: str, industry: str, full: str = "", en: str = "") -> dict:
    return {"name": name.strip(), "market": market, "industry": INDUSTRY.get(industry, industry or ""),
            "aliases": [a.strip() for a in (full, en) if a and a.strip() and a.strip() != name.strip()]}


def build() -> dict:
    old = load(PATH, {}) or {}
    out, notes = {}, []
    try:
        for x in _get(TWSE):
            code = str(x.get("公司代號", "")).strip()
            if code:
                out[code] = _row(x.get("公司簡稱", ""), "TWSE", str(x.get("產業別", "")).strip(), x.get("公司名稱", ""), x.get("英文簡稱", ""))
    except Exception as e:  # 沿用上一份的上市部分
        notes.append(f"上市代號表抓取失敗，沿用舊資料：{e}")
        out.update({k: v for k, v in old.items() if v.get("market") == "TWSE"})
    try:
        rows = _get(TPEX)
        for x in rows:
            code = str(x.get("SecuritiesCompanyCode") or x.get("公司代號") or "").strip()
            if code:
                out[code] = _row(x.get("CompanyAbbreviation") or x.get("公司簡稱") or "", "TPEX",
                                 str(x.get("SecuritiesIndustryCode") or x.get("產業別") or "").strip(), x.get("CompanyName") or x.get("公司名稱") or "")
        if not rows:
            raise ValueError("回傳空白")
    except Exception as e:
        try:
            for x in _get(TPEX_QUOTES):
                code = str(x.get("SecuritiesCompanyCode", "")).strip()
                if code:
                    out[code] = _row(x.get("CompanyName", ""), "TPEX", "")
            notes.append(f"上櫃基本資料失敗，改用行情表（沒有產業別）：{e}")
        except Exception as e2:
            notes.append(f"上櫃代號表抓取失敗，沿用舊資料：{e2}")
            out.update({k: v for k, v in old.items() if v.get("market") == "TPEX"})
    out = {k: v for k, v in out.items() if v["name"]}
    for k, v in out.items():
        v["etf"] = k.startswith("00")
    save(PATH, dict(sorted(out.items())))
    log_event("registry", ok=True, count=len(out), notes=notes)
    return out


def get() -> dict:
    return load(PATH, {}) or {}


def _plain(name: str) -> str:
    import re
    return re.sub(r"(股份有限公司|有限公司|控股|-KY|＊|\*|\s)", "", str(name or ""))


def match(code: str, name: str, reg: dict) -> dict | None:
    """代號存在、而且名稱對得上（簡稱、全名、英文名或互相包含）才算數；AI 記錯代號的會被擋掉。"""
    r = reg.get(str(code).strip())
    if not r:
        return None
    n = _plain(name)
    names = [_plain(r["name"]), *(_plain(a) for a in r.get("aliases", []))]
    if not n or any(n == x or (len(n) >= 2 and (n in x or x in n)) for x in names if x):
        return r
    return None


if __name__ == "__main__":
    print(len(build()), "檔", iso_now())
