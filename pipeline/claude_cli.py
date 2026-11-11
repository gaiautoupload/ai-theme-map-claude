"""AI 解析：呼叫這台電腦已登入的 Claude Code（claude -p），回傳 JSON。

- 不需要 API 金鑰，用使用者的 Claude 訂閱額度。
- 在空的暫存資料夾裡執行，只開放 WebSearch／WebFetch（需要上網時），不能讀寫本機檔案、不能跑指令。
- 提示從 stdin 送進去（Windows 命令列長度有上限）。
- 回應解析不了或欄位不對就把錯誤告訴 Claude 重試；最後還是失敗就丟 ClaudeError，讓上層記錄失敗（不吞掉）。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Optional

from . import config
from .store import log_event

JSON_RULE = "\n\n## 輸出格式\n只輸出一個 JSON 物件，不要加任何說明文字或 Markdown 圍欄。所有文字用繁體中文。"
BLOCKED_TOOLS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "NotebookEdit", "Task", "Agent", "TodoWrite"]


class ClaudeError(RuntimeError):
    pass


def _bin() -> str:
    return config.CLAUDE_CMD or shutil.which("claude") or "claude"


def extract_json(text: str) -> Any:
    """從回應文字取出 JSON：先試整段，再試 ``` 圍欄，最後找第一個完整的 {...}（會跳過字串裡的括號）。"""
    t = (text or "").strip()
    for cand in (t, *(m.group(1) for m in re.finditer(r"```(?:json)?\s*(.*?)```", t, re.S))):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = t.find("{", start + 1)
    raise ValueError("回應裡找不到完整的 JSON 物件")


def _run_once(prompt: str, web: bool, effort: str, model: str, max_turns: int) -> dict:
    cmd = [_bin(), "-p", "--model", model, "--effort", effort, "--output-format", "json", "--max-turns", str(max_turns)]
    # 這兩個參數後面接的是清單，放最後（提示走 stdin）
    if web:
        cmd += ["--allowedTools", "WebSearch", "WebFetch"]
    cmd += ["--disallowedTools", *BLOCKED_TOOLS, *([] if web else ["WebSearch", "WebFetch"])]
    with tempfile.TemporaryDirectory(prefix="thememap-claude-") as cwd:
        p = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, cwd=cwd,
                           timeout=config.CLAUDE_TIMEOUT_SEC)
    out = p.stdout.decode("utf-8", "replace")
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        err = p.stderr.decode("utf-8", "replace")[-500:]
        raise ClaudeError(f"Claude Code 沒有回傳 JSON（exit {p.returncode}）：{err or out[-300:]}")
    if d.get("is_error"):
        raise ClaudeError(f"Claude Code 回報錯誤：{d.get('subtype')} {str(d.get('result'))[:300]}")
    return d


def ask_json(purpose: str, prompt: str, *, web: bool = False, effort: str = "medium", model: Optional[str] = None,
             validate: Optional[Callable[[Any], Optional[str]]] = None, retries: int = 1, max_turns: int = 0) -> Any:
    """送出提示、取回 JSON。validate 回傳錯誤訊息字串表示不合格（會帶著錯誤重試），回傳 None 表示通過。"""
    model = model or config.CLAUDE_MODEL
    max_turns = max_turns or (30 if web else 3)
    full, last_err = prompt + JSON_RULE, ""
    for attempt in range(retries + 1):
        t0 = time.time()
        ask = full if not last_err else f"{full}\n\n## 上一次的輸出有問題\n{last_err}\n請修正後重新輸出完整 JSON。"
        try:
            d = _run_once(ask, web, effort, model, max_turns)
            data = extract_json(d.get("result", ""))
            problem = validate(data) if validate else None
            if problem:
                raise ValueError(problem)
            log_event("claude", purpose=purpose, ok=True, attempt=attempt, sec=round(time.time() - t0),
                      turns=d.get("num_turns"), cost_usd=d.get("total_cost_usd"))
            return data
        except subprocess.TimeoutExpired:
            last_err = f"超過 {config.CLAUDE_TIMEOUT_SEC} 秒沒有完成"
        except (ClaudeError, ValueError) as e:
            last_err = str(e)[:600]
        log_event("claude", purpose=purpose, ok=False, attempt=attempt, sec=round(time.time() - t0), error=last_err)
    raise ClaudeError(f"{purpose}：{last_err}")


def require(*keys: str, lists: tuple = ()) -> Callable[[Any], Optional[str]]:
    """常用驗證：必要欄位存在，指定欄位是非空陣列。"""
    def check(d: Any) -> Optional[str]:
        if not isinstance(d, dict):
            return "最外層必須是 JSON 物件"
        miss = [k for k in keys if d.get(k) in (None, "", [], {})]
        bad = [k for k in lists if not isinstance(d.get(k), list) or not d.get(k)]
        if miss or bad:
            return f"缺少或空白的欄位：{'、'.join(miss + bad)}"
        return None
    return check
