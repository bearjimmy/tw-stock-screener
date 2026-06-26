# 台股選股網頁 v3

一個個人用台股觀察與策略篩選工具：盤後從 **FinMind** 抓全市場真實資料、用客觀規則算發動訊號與評分，再由 **FastAPI** 後端 + 純 HTML 前端呈現。

> **重要免責**：所有指標、評分、訊號與篩選結果均為依規則進行的客觀計算呈現，**非投資建議**，亦不構成買賣推薦。資料可能延遲、缺漏或計算誤差；投資有風險，請依自身判斷並諮詢合格專業人士。

## 線上 Demo（GitHub Pages 靜態版）

公開網址：**https://bearjimmy.github.io/tw-stock-screener/**

- 前端會自動偵測：在 `*.github.io` 上 → **靜態模式**，直接讀 `data/` 內的盤後 JSON 快照（不需後端）。
- 在 `localhost` 上 → **動態模式**，打本機 FastAPI 的 `/api/*`（資料即時）。
- 靜態版的資料是「**最後一次 push 的快照**」，不會自動更新；要更新就重新 `git add -f data/... && git commit && git push`（可日後加 GitHub Action 自動化）。

---

## 一、架構總覽

兩段式設計：盤後批次跑資料、線上秒級讀取。

```
            ┌─────────────────────┐         每週一~五 18:00
            │ Windows Task        │ ──────────► fetch_and_compute.py
            │ Scheduler           │             ├─ 抓 FinMind 全市場 (4 dataset × N 日)
            └─────────────────────┘             ├─ 算策略訊號、技術評等、相對強勢評分
                                                └─ 寫 data/stocks.json、details/*.json、market.json
                                                          │
                                                          ▼
                              ┌─────────────────────────────────────┐
                              │ main.py (FastAPI, port 8000)        │
                              │ ├─ /api/market   /api/stocks        │
                              │ ├─ /api/stock/{id}  /api/screener   │
                              │ └─ 靜態檔掛 / 直接 serve index.html │
                              └─────────────────────────────────────┘
                                                          │
                                                          ▼
                              http://localhost:8000/ (瀏覽器)
```

**設計取捨**：
- 抓取與計算放在**盤後一次**，使用者查詢時完全不打 FinMind → 秒級回應、節省 API 額度
- FastAPI 同時掛靜態檔 → 一個 process、沒有 CORS 問題
- 後端 `Store` 用 `stocks.json` 的 mtime 自動 reload → fetch 跑完不必重啟 server
- 前端每 5 分鐘輪詢 `market.updated` → 後端資料更新時自動清前端快取、重畫當前頁

---

## 二、快速啟動

### 2.1 環境
- Python 3.12（已驗證；3.10+ 應該也行）
- 依賴：`fastapi`、`uvicorn[standard]`、`requests`

```powershell
python -m pip install fastapi "uvicorn[standard]" requests
```

### 2.2 設定 FinMind Token

**推薦：永久使用者環境變數**（Task Scheduler 也吃得到）：
```powershell
[Environment]::SetEnvironmentVariable('FINMIND_TOKEN', '<貼上 token>', 'User')
# 重開 PowerShell 才會生效
```

**Fallback：本機檔案**（已加入 .gitignore，不會進 git）：
```powershell
Set-Content -Encoding utf8 -Path "d:\投資選股網頁\.finmind_token" -Value "<貼上 token>"
```

> Token 來自 [FinMind](https://finmindtrade.com/)；本專案以 Backer 方案設計（一次請求拿全市場）。

### 2.3 首次抓取（煙霧測試）
```powershell
# 35 個交易日，約 5-7 分鐘
python d:\投資選股網頁\fetch_and_compute.py --days 35
```

完整 250 日約 2 小時（會分批避開速率上限、自動斷點續抓）：
```powershell
python d:\投資選股網頁\fetch_and_compute.py
```

### 2.4 啟動後端
```powershell
python d:\投資選股網頁\main.py
```
打開瀏覽器 `http://localhost:8000/` 即可。

---

## 三、自動化排程（已設定好）

`update.ps1` 是 Task Scheduler 的入口；當前排程：

| 項目 | 設定 |
|---|---|
| 名稱 | `TaiwanStockUpdate` |
| 頻率 | 每週一至五 18:00 |
| 動作 | `powershell.exe -File update.ps1` |
| 內容 | 跑 `fetch_and_compute.py --days 35 --refresh-latest 2` |
| Log | `data\update.log`（每次追加時戳、exit code、耗時） |

**為何 `--days 35` 不是 250**：策略只看近期（20 日動能、15 日新高、25 點 sparkline）、35 日綽綽有餘。每次排程只跑最新一兩天（其餘走 `progress.json` 快取），<1 分鐘完成。要長期歷史請手動跑 `python fetch_and_compute.py`（預設 250 日、約 2 小時）。

**為何 18:00**：台股 13:30 收盤後 4.5 小時，FinMind 盤後三大法人、外資進出、PER/PBR 全部上齊；早於此抓會抓到空陣列（過去踩過，凌晨 02:43 跑回傳全 0 筆）。

**Windows PowerShell 5.1 編碼眉角**：`update.ps1` 必須存成 **UTF-8 with BOM**。Windows PowerShell 5.1 在 zh-TW 系統預設用 cp950 讀取 .ps1 檔；無 BOM 時中文註解的位元組被誤解碼會造成 parser 看到的行序錯位、`Unexpected token '}'` 等假錯誤。用 VSCode／PowerShell ISE 編輯時，記得把編碼選為 「UTF-8 with BOM」。

### 排程指令備忘
```powershell
# 查詢狀態
schtasks /Query /TN "TaiwanStockUpdate" /V /FO LIST

# 手動立刻跑一次
schtasks /Run /TN "TaiwanStockUpdate"

# 改時間（例如 18:00）
schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:00 `
    /TN "TaiwanStockUpdate" `
    /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"d:\投資選股網頁\update.ps1`"" /F

# 移除
schtasks /Delete /TN "TaiwanStockUpdate" /F
```

---

## 四、檔案結構

```
d:\投資選股網頁\
├─ fetch_and_compute.py        盤後批次：抓 FinMind + 算策略
├─ main.py                     FastAPI 後端
├─ index.html                  前端單檔（深色 UI、漲紅跌綠）
├─ update.ps1                  Task Scheduler 包裝（log + 失敗碼透傳）
├─ finmind.md                  FinMind API 使用手冊
├─ 選股網頁後端串接_v3_給ClaudeCode.md   原始任務規格
├─ README.md                   本檔
├─ .gitignore                  排除 token 與 data/
├─ .finmind_token              (選用) token fallback；不入 git
└─ data/                       fetch 產出（首次跑後生成）
   ├─ stocks.json              市場總覽輕量陣列（含 sparkCloses 25 點）
   ├─ market.json              大盤摘要
   ├─ universe.json            股票池（普通股 stock_id → name）
   ├─ details/<id>.json        每檔個股完整資料（K 線、法人、外資、PER…）
   ├─ raw/<dataset>/<date>.json  原始抓取結果（斷點續抓用）
   ├─ progress.json            進度檔（哪些 dataset|date 已抓）
   └─ update.log               排程執行記錄
```

---

## 五、API 端點

所有 endpoint 中文不會被轉成 `\uXXXX`；資料未產生時統一回 503 + 中文 hint。

| 路徑 | 用途 | 回傳重點 |
|---|---|---|
| `GET /api/market` | 大盤摘要 | `date / up / down / flat / fired / totalTurnover / updated` |
| `GET /api/stocks` | 市場總覽全列表 | 陣列，每筆含 `id, name, price, changePct, score, rating, fired, sparkCloses[25]…` |
| `GET /api/stock/{id}` | 個股完整資料 | `kline[]、instBars[30]、foreignTrend[30]、sig.conditions[7]、per、pbr、yieldPct…` |
| `GET /api/screener?breakout=&instbuy=&score=&streak=&foreign=` | 策略篩選 | 依條件過濾後的 `/api/stocks` 子集 |

**錯誤碼**：
- `404` — `stock_id` 不存在
- `503` — `data/` 尚未產生（提示先跑 fetch_and_compute.py）

---

## 六、前端功能

### 6.1 頁面
- `#/market` — 市場總覽表：可排序、即時前端篩選、列點擊跳個股
- `#/screener` — 策略篩選器：每改條件就打 `/api/screener` 重抓（後端過濾）
- `#/stock/{id}` — 個股詳情：K 線 + 法人 histogram + 外資 line + 策略檢查表 + 評分

### 6.2 頂部股票查詢
- 輸入代號或中文名稱即時下拉 10 筆
- 代號前綴匹配優先（輸入「23」優先顯示 2330、2317…）
- ↑↓ 切換、Enter 跳該筆、Esc 關閉、外點關閉
- 完全前端過濾（已載入記憶體的 `STOCKS`）、零 API 延遲

### 6.3 自動同步
- 每 5 分鐘輪詢 `/api/market`；`updated` 變動 → 清前端快取重畫
- 切回分頁時也立即檢查一次（避免離開很久回來看到舊資料）
- 後台分頁時跳過該輪輪詢，不浪費頻寬

---

## 七、策略發動訊號（7 條件）

對每檔股票的最近 4 根 K 線檢查；**全部成立**才標記為「⚡ 發動」。

| 條件 | 邏輯 |
|---|---|
| c1 量價突破 | 單日漲幅 > 4% |
| c2 創新高 | 收盤 ≥ 近 15 個交易日收盤最大值 |
| c3 帶量上攻 | 最新成交量 > 前 5 日均量 × 1.5 |
| c4 動能濾網 | 近 20 日報酬為正 |
| c5a 型態 | 前三日收盤連續遞減 |
| c5b 型態 | 第 2、3 日收黑（close < open） |
| c5c 型態 | 第 4 日翻紅（close > open） |
| **加強**（不影響發動）| 最新一日三大法人淨買超 > 0 → 加「法人挺」標記 |

實作在 `fetch_and_compute.py:compute_signal`。

---

## 八、相對強勢評分（0–100）

```
score = 100 × (0.35·a + 0.25·b + 0.20·c + 0.20·d)
```

| 子項 | 權重 | 量化 | 線性映射 |
|---|---|---|---|
| a 動能 | 35% | 近 20 日報酬 | -10% → 0、+10% → 1 |
| b 趨勢 | 25% | 相對 20 日均線位置 | -5% → 0、+5% → 1 |
| c 強度 | 20% | 相對近 60 日高點 | 0.80 → 0、1.00 → 1 |
| d 籌碼 | 20% | 法人淨買超方向×力道 + 外資持股微調 | 0 → 0、1 → 1 |

各成分用 `clamp(0,1)` 截斷上下限後加權；改算法的話直接改 `fetch_and_compute.py:compute_score()`。

前端顯示：≥75 高分（橘黃膠囊）、55-74 中等、<55 灰。

---

## 九、注意事項

### 9.1 資料層
- **股票池**：全部上市櫃普通股（從 `TaiwanStockInfo` 排除 ETF/ETN/權證/受益證券；普通股規則：4 碼純數字 + 產業別不在排除清單）
- **歷史長度**：排程跑 35 個交易日（夠用且每次 <1 分鐘）；手動跑可拉到 250 日或更多。策略只看近期，**不需要十年**
- **價格**：用原始價（非還原股價）；型態策略看當下狀態
- **ROE 永遠是 null**：所選 dataset 沒有 ROE 來源，前端顯示「—」是預期行為
- **TAIEX 加權指數**：本版未抓對應 dataset，市場概況列不顯示 TAIEX；改顯示真實漲跌家數／成交額／更新時間

### 9.2 抓取與快取
- FinMind 帶 Token 速率 **600 請求/小時**；本程式維護本地計數器、逼近 580 時自動 sleep ~50 分鐘續抓
- **斷點續抓**：以 `dataset|date` 為鍵記錄進度，重跑時跳過已完成；中斷無痛
- `--refresh-latest N`（預設 1）：每次強制重抓最新 N 日，避免「上午跑過、盤後再修正」被快取覆蓋。排程目前傳的是 **2**（保守一點，連同前一日一起重抓）
- 收到 HTTP 402 → 額度用盡，sleep 50 分鐘再續
- 收到 HTTP 429 → 請求過快，sleep 60 秒

### 9.3 Token 防呆
- `fetch_and_compute._sanitize_token()` 用白名單 `[A-Za-z0-9._-]` 把空白、換行、引號全砍掉
- 過去踩過的真實 bug：使用者複貼到 PowerShell env var 時帶 `\n` 與多個前置空格 → `requests` 拋 `Invalid leading whitespace in header value` 全失敗

### 9.4 篩選結果與資料世代
- 每次 fetch 跑完 → stocks.json 的 mtime 改變 → 後端 `Store.refresh_if_changed()` 自動重載 → 前端輪詢偵測 `updated` 變動 → 清 `STOCKS / STOCK_CACHE` → router 重畫
- **排名與篩選結果都會同步更新**，不必手動 F5

### 9.5 不要做的事
- 不要把 token 寫進 `.py` 或 `.html`（已用 env var／檔案分離）
- 不要在使用者請求時即時呼叫 FinMind（一律盤後預算、線上只讀）
- 不要逐檔抓（Backer 應該逐日抓全市場，省非常多請求）
- 不要把 `data/` 入 git（每次都會重生成、又大）

---

## 十、故障排除

| 症狀 | 可能原因與處置 |
|---|---|
| 開瀏覽器 503 中文提示 | `data/` 還沒生成 → 跑 `python fetch_and_compute.py --days 35` |
| fetch 報 `Invalid leading whitespace in header value` | token 被空白／換行污染 → 已修；若仍發生請檢查 `.finmind_token` 內容 |
| fetch 報 `cp950 codec can't encode '✓'` | Windows console 編碼問題 → 已用 `sys.stdout.reconfigure('utf-8')` 修掉 |
| fetch 報 `ZeroDivisionError` 在 `compute_score` | 某檔停牌 close=0 → 已過濾；若再現代表新資料形式異常 |
| 跑 `python main.py` 報 `[Errno 10048]` | port 8000 已被佔 → `Get-NetTCPConnection -LocalPort 8000` 找 PID 後 `Stop-Process` |
| 排程跑了但資料沒更新 | 看 `data/update.log` 找 exit code；常見：token 過期 → 重設 env var |
| `data/update.log` 不存在但排程已跑 | `update.ps1` 編譯／執行就掛 → 多半是檔案存成 UTF-8 無 BOM，PowerShell 5.1 用 cp950 誤解碼。重存為「UTF-8 with BOM」 |
| `update.log` 每個字後面有空白／亂碼 | 用了 `Tee-Object -FilePath`（5.1 預設 UTF-16 LE 寫檔）。改用 `cmd.exe /c "python ... >>log 2>&1"` 走 cmd 原生 redirect 即可（python stdout 已 reconfigure 為 UTF-8） |
| update.ps1 退出 code 1 但 log 看起來成功 | `*>&1 \| Tee-Object` 會把 python stderr 包成 NativeCommandError + `$ErrorActionPreference='Stop'` 把它升級成 terminating；或 `"{1:hh\\:mm\\:ss}" -f $Duration` 過度跳脫造成 FormatError（雙引號裡 `\` 不需 escape，寫單反斜線就好） |
| 瀏覽器看到舊資料 | 等 5 分鐘自動輪詢，或 Ctrl+F5 強制重抓 |
| 個股頁圖表是「圖表函式庫無法載入」 | TradingView lightweight-charts CDN 連不上 → 檢查網路 |

### Server 重啟
```powershell
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
python d:\投資選股網頁\main.py
```

### 強制重算（不重抓）
資料抓回來但發現公式想調整時，改完 `compute_*` 後：
```powershell
python d:\投資選股網頁\fetch_and_compute.py --skip-fetch
```
只跑聚合、寫檔；秒級完成。
