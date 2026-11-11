# 題材地圖｜投資人的獲利雷達與預警牆

從總經環境、全球題材，追到台股真正吃得到價值的公司。每個題材 10 秒內回答：這是什麼、為什麼是現在、市場多大、先看哪三檔、誰真的賺到錢（吃肉還是喝湯）、何時反映到營收；同時誠實標出跟風股、退燒與逆風。

復刻自舊站 `gaiautoupload/ai-theme-map-site`，前端重新設計，AI 解析改用 Claude，並接上「興櫃總經戰情室」的總金線與總經指標。

## 原則
- **事實優先、不假精準**：市場規模、成長率、營收占比沒有可信出處就標「待補」。每個重要數字標資料性質：官方、新聞、機構估計、AI 推論、待補。
- **概念股要對得上官方代號表**：Claude 列的代號與名稱逐檔比對證交所／櫃買中心，對不上的退回重寫，還錯就剔除。
- **量化用真實資料**：法人火勢來自證交所 T86、櫃買中心三大法人；總經來自戰情室（FRED、證交所、BLS、FOMC）。
- **失敗要看得到**：每一步的成功失敗都記在 `data/runs.json`，網站「資料來源與方法」頁會顯示最近一次執行結果。

## 結構
```
pipeline/       產線
  claude_cli.py   呼叫已登入的 Claude Code（claude -p），只開放 WebSearch／WebFetch，回傳 JSON
  registry.py     官方代號表
  macro_bridge.py 讀戰情室的總金線與總經指標（只讀），算總經因子方向
  chips.py        法人買賣超、題材資金火勢
  themes.py       Claude 發掘題材（含退燒預警）＋研究題材＋概念股
  research.py     Claude 個股簡介、盤後日報、預期落差
  publish.py      把 data/ 拆成網站讀的小檔（site/data/）
  legacy_import.py 一次性匯入舊站資料（去重、清理）
data/           正式資料（題材、個股、日報、籌碼資料庫、執行紀錄）
site/           發布用靜態網站（index.html、assets/、data/）
run_daily.py    每日產線
web_server.py   本機預覽（127.0.0.1:8890）
```

## 使用
```bash
python run_daily.py              # 全部（約需 30–60 分鐘，視 Claude 回應而定）
python run_daily.py --no-ai      # 只更新官方資料並重新發布
python run_daily.py --only=themes,report
python web_server.py             # 本機預覽 http://127.0.0.1:8890/
```
Claude 用這台電腦已登入的 Claude Code，不需要 API 金鑰，用的是訂閱額度。每天的分析量在 `pipeline/config.py`（或環境變數 `THEMEMAP_*`）調整：新題材 5 個、重寫舊題材 2 個、個股簡介 30 檔、預期落差 15 則。

本站內容為研究整理，不構成任何投資建議。
