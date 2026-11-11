"""設定：路徑、Claude 呼叫參數、每次執行的分析額度。都可以用環境變數覆寫。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"          # 工作資料（正式來源）：主題、個股 wiki、日報、籌碼資料庫
SITE = ROOT / "site"          # 發布用靜態網站（GitHub Pages 的內容）
SITE_DATA = SITE / "data"
LOGS = DATA / "logs"
CACHE = DATA / "cache"

env = os.environ.get

# Claude：用這台電腦已登入的 Claude Code（claude -p），不需要 API 金鑰
CLAUDE_CMD = env("THEMEMAP_CLAUDE_CMD", "")                  # 空白＝自動找 PATH 裡的 claude
CLAUDE_MODEL = env("THEMEMAP_CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_TIMEOUT_SEC = int(env("THEMEMAP_CLAUDE_TIMEOUT_SEC", "1200"))
CLAUDE_WORKERS = int(env("THEMEMAP_CLAUDE_WORKERS", "3"))     # 同時幾個分析

# 每天的分析額度（控制訂閱用量）
THEMES_PER_RUN = int(env("THEMEMAP_THEMES_PER_RUN", "5"))     # 新發掘的主題最多做幾個
REFRESH_THEMES_PER_RUN = int(env("THEMEMAP_REFRESH_THEMES_PER_RUN", "2"))  # 舊主題（非 Claude 產生或最久沒更新）重寫幾個
WIKI_PER_RUN = int(env("THEMEMAP_WIKI_PER_RUN", "30"))        # 個股 wiki 每天重寫幾檔
GAP_ARTICLES_PER_RUN = int(env("THEMEMAP_GAP_ARTICLES_PER_RUN", "15"))  # 預期落差每天最多解析幾篇新聞

# 發布：推到 GitHub main，由 GitHub Actions 把 site/ 發布成 Pages；推完到公開網址確認，再寫進網站總表
SITE_NAME = "題材地圖｜投資人獲利雷達與預警牆（Claude 版）"   # 必須和 WEBSITE_REGISTRY.md 的列名一致
PUBLIC_URL = env("THEMEMAP_PUBLIC_URL", "https://gaiautoupload.github.io/ai-theme-map-claude/")
GIT_BRANCH = env("THEMEMAP_GIT_BRANCH", "main")
GIT_AUTHOR = ("gaiautoupload", "gaiautoupload@users.noreply.github.com")
WORKSPACE = Path(env("THEMEMAP_WORKSPACE", str(ROOT.parent)))  # WEBSITE_REGISTRY.md、WEBSITE_UPDATE_LOG.md 所在

TZ_OFFSET_HOURS = 8
ENGINE = "claude"             # 新產生的 AI 內容都標 ai_engine=claude
LEGACY_ENGINE = "legacy-vllm"  # 從舊站匯入、還沒被 Claude 重寫的內容
