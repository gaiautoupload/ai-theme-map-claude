"""每日產線：一步失敗不影響其他步，但失敗一定記下來、網站「方法」頁看得到，最後以非 0 結束（排程看得出來）。

  python run_daily.py              # 全部
  python run_daily.py --no-ai      # 只更新官方資料（代號、法人、總經）並重新發布，不呼叫 Claude
  python run_daily.py --only=themes,report
  python run_daily.py --no-deploy  # 只更新本機，不推 GitHub
步驟：registry → macro → chips → themes → verify（概念股出處核對）→ wiki → gaps → report → flows（重算題材火勢）→ publish
      → deploy（推 GitHub、確認公開網站）→ 結果寫進 WEBSITE_REGISTRY.md／WEBSITE_UPDATE_LOG.md
"""
from __future__ import annotations

import sys
import time

from pipeline import chips, config, deploy, macro_bridge, publish, registry, research, themes, verify
from pipeline.store import iso_now, load, log_event, save


def main(args: list[str]) -> int:
    no_ai = "--no-ai" in args
    no_deploy = "--no-deploy" in args   # 只更新本機，不推 GitHub
    no_record = "--no-record" in args   # 測試用：不寫網站總表與更新紀錄
    only = next((a.split("=", 1)[1].split(",") for a in args if a.startswith("--only=")), None)
    run = {"started_at": iso_now(), "steps": []}
    ctx: dict = {}

    def step(name: str, fn, ai: bool = False):
        if (no_ai and ai) or (only and name not in only):
            return
        t0 = time.time()
        try:
            note = fn() or ""
            run["steps"].append({"name": name, "ok": True, "note": str(note)[:300], "sec": round(time.time() - t0)})
        except Exception as e:
            run["steps"].append({"name": name, "ok": False, "note": f"{type(e).__name__}: {str(e)[:280]}", "sec": round(time.time() - t0)})
        print(("✓" if run["steps"][-1]["ok"] else "✗"), name, run["steps"][-1]["note"], flush=True)

    step("registry", lambda: f"{len(registry.build())} 檔")
    step("macro", lambda: (ctx.__setitem__("macro", macro_bridge.build()), f"總金線 {ctx['macro'].get('line', {}).get('as_of')}")[1])
    ctx.setdefault("macro", load(config.DATA / "macro_board.json", {}) or {})
    step("chips", chips.run)
    step("themes", lambda: themes.run(load(config.DATA / "themes.json", {}) or {}, ctx["macro"]), ai=True)
    step("verify", verify.verify_themes)
    step("wiki", lambda: research.run_wiki(load(config.DATA / "themes.json", {}) or {}), ai=True)
    step("gaps", research.run_gaps, ai=True)
    step("gapcheck", verify.verify_gaps)
    step("report", lambda: research.run_report(ctx["macro"], load(config.DATA / "chips_summary.json", {}) or {}), ai=True)
    step("flows", lambda: (chips.build_summary(load(config.DATA / "themes.json", {}) or {}, registry.get()), "題材火勢已重算")[1])
    run["finished_at"] = iso_now()
    runs = (load(config.DATA / "runs.json", []) or [])[-59:] + [run]
    save(config.DATA / "runs.json", runs)
    step("publish", lambda: str(publish.build()["counts"]))
    deploy_on = not no_deploy and (not only or "deploy" in only)
    commit = ""
    if deploy_on and all(s["ok"] for s in run["steps"] if s["name"] == "publish"):
        step("deploy", deploy.push_and_verify)   # 成功時 note 就是 commit 代號
        commit = next((s["note"] for s in run["steps"] if s["name"] == "deploy" and s["ok"]), "")
    runs[-1] = run
    save(config.DATA / "runs.json", runs)
    ok = all(s["ok"] for s in run["steps"])
    log_event("run", ok=ok, steps=run["steps"])

    # 結果寫進網站總表與更新紀錄：成功、失敗都記；只有公開網站確認過才更新「最近部署／確認」
    failed = [f"{s['name']}：{s['note'][:80]}" for s in run["steps"] if not s["ok"]]
    if not no_record:
        names = "、".join(s["name"] for s in run["steps"])
        if commit:
            event, note = "排程產線／已推送／公開驗證", f"步驟 {names}" + (f"；失敗：{'；'.join(failed)}" if failed else "；全部成功")
        elif deploy_on:
            event, note = "排程產線／發布失敗", "；".join(failed) or "未推送"
        else:
            event, note = "本機資料更新（未推送）", f"步驟 {names}" + (f"；失敗：{'；'.join(failed)}" if failed else "")
        try:
            deploy.record(ok and (bool(commit) or not deploy_on), event, note, commit=commit, deployed=bool(commit))
        except Exception as e:
            print("✗ record", e, flush=True)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
