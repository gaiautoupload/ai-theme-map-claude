"""讀寫 JSON（原子寫入，避免寫到一半當機留下壞檔）、時間、主題 ID。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config

TW = timezone(timedelta(hours=config.TZ_OFFSET_HOURS))


def now_tw() -> datetime:
    return datetime.now(TW)


def iso_now() -> str:
    return now_tw().isoformat(timespec="seconds")


def today() -> str:
    return now_tw().strftime("%Y-%m-%d")


def load(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(path: Path, data: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def norm_title(title: str) -> str:
    """去掉空白與標點的標題，用來判斷是不是同一個主題。"""
    return re.sub(r"[\s\W_]+", "", str(title or "")).lower()


def theme_id(title: str) -> str:
    """同一個標題永遠得到同一個 ID：重新分析時覆蓋舊的，不會越堆越多。"""
    return "t" + hashlib.sha1(norm_title(title).encode("utf-8")).hexdigest()[:10]


def log_event(kind: str, **fields: Any) -> None:
    """一行一筆的執行紀錄（data/logs/events.jsonl），成功失敗都記。"""
    config.LOGS.mkdir(parents=True, exist_ok=True)
    row = {"at": iso_now(), "kind": kind, **fields}
    with open(config.LOGS / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
