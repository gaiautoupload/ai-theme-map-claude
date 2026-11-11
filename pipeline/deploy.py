"""發布：把 site/ 推到 GitHub，等 GitHub Pages 換上新版，再到公開網址確認；結果（成功或失敗）寫進網站總表與更新紀錄。

- 只提交 site/（data/ 是本機工作資料，不上傳）。
- GitHub 上若有本機沒有的提交就停下來，不強推、不覆蓋。
- 公開網址的 data/meta.json 的 built_at 要和本機這次發布的一致，才算部署完成；
  沒確認到就不更新總表的「最近部署／確認」。
"""
from __future__ import annotations

import subprocess
import time

import requests

from . import config
from .store import load, log_event, now_tw


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    name, email = config.GIT_AUTHOR
    return subprocess.run(["git", "-c", f"safe.directory={config.ROOT.as_posix()}", "-c", f"user.name={name}", "-c", f"user.email={email}",
                           "-C", str(config.ROOT), *args], check=check, text=True, encoding="utf-8", errors="replace", capture_output=True)


def _meta() -> dict:
    return load(config.SITE_DATA / "meta.json", {}) or {}


def data_date(meta: dict | None = None) -> str:
    latest = (meta or _meta()).get("latest", {})
    chips = str(latest.get("chips") or "")
    chips = f"{chips[:4]}-{chips[4:6]}-{chips[6:]}" if len(chips) == 8 else chips or "待補"
    return f"日報 {latest.get('report') or '待補'}；法人 {chips}；題材 {latest.get('theme') or '待補'}；總經 {latest.get('macro') or '待補'}"


def push_and_verify(wait_sec: int = 600) -> str:
    meta = _meta()
    built = meta.get("built_at")
    if not built:
        raise RuntimeError("site/data/meta.json 沒有 built_at，先跑 publish")
    br = config.GIT_BRANCH
    git("add", "-A", "--", "site")
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git("commit", "-m", f"資料更新 {meta.get('latest', {}).get('report') or built[:10]}（{built[11:16]}）")
    try:
        git("fetch", "origin", br)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"連不到 GitHub：{(e.stderr or '').strip()[:200]}") from None
    behind, ahead = map(int, git("rev-list", "--left-right", "--count", f"origin/{br}...{br}").stdout.split())
    if behind:
        raise RuntimeError(f"GitHub 上有 {behind} 個本機沒有的提交，需要人工處理（不強推）")
    if ahead:
        try:
            git("push", "origin", br)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"推送失敗：{(e.stderr or '').strip()[:200]}") from None
    commit = git("rev-parse", "--short", "HEAD").stdout.strip()
    url = config.PUBLIC_URL.rstrip("/") + "/data/meta.json"
    deadline, seen = time.time() + wait_sec, ""
    while time.time() < deadline:
        try:
            r = requests.get(url, params={"v": time.time_ns()}, timeout=15)
            seen = r.json().get("built_at", "") if r.ok else f"HTTP {r.status_code}"
            if seen == built:
                log_event("deploy", ok=True, commit=commit, built_at=built)
                return commit
        except (requests.RequestException, ValueError) as e:
            seen = type(e).__name__
        time.sleep(20)
    raise RuntimeError(f"已推送 {commit}，但公開網站 {wait_sec // 60} 分鐘內沒換上新版（看到 {seen}，應為 {built}）")


def record(ok: bool, event: str, note: str, commit: str = "", deployed: bool = False) -> None:
    """把這次結果寫進 WEBSITE_REGISTRY.md（最新狀態）與 WEBSITE_UPDATE_LOG.md（追加一列）。"""
    stamp = now_tw().strftime("%Y-%m-%d %H:%M")
    meta = _meta()
    date_txt = data_date(meta)
    c = meta.get("counts", {})
    reg = config.WORKSPACE / "WEBSITE_REGISTRY.md"
    lines = reg.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"| {config.SITE_NAME} |"):
            cols = line.split("|")
            if len(cols) != 10:
                raise RuntimeError("網站總表這一列的欄位數不對，請人工檢查")
            cols[6] = f" {date_txt} "
            if deployed:
                cols[7] = f" {stamp}（公開頁面已確認 {commit}） "
            status = "正常" if ok else "待檢查"
            cols[8] = (f" {status}（{note}）；Claude 已查證題材 {c.get('themes_claude', 0)}、個股 {c.get('wiki_claude', 0)}，"
                       f"其餘 {c.get('themes', 0) - c.get('themes_claude', 0)} 個舊題材逐日重寫中 ")
            lines[i] = "|".join(cols)
            break
    else:
        raise RuntimeError(f"網站總表找不到「{config.SITE_NAME}」")
    reg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report_day = meta.get("latest", {}).get("report") or "待補"
    entry = f"| {stamp} | {config.SITE_NAME} | {event} | {report_day} | {'完成' if ok else '失敗／待檢查'} | {commit or '未推送'} | {note} |"
    log = config.WORKSPACE / "WEBSITE_UPDATE_LOG.md"
    content = log.read_text(encoding="utf-8")
    marker = "\n## 事件用語"
    if marker not in content:
        raise RuntimeError("更新紀錄找不到插入位置（## 事件用語）")
    before, after = content.split(marker, 1)
    log.write_text(before.rstrip("\r\n") + f"\n{entry}\n\n## 事件用語" + after, encoding="utf-8")
