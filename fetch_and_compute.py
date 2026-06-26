# -*- coding: utf-8 -*-
"""
fetch_and_compute.py —— 台股選股網頁 v3 的「盤後批次」程式。

職責（任務規格第一節「抓取與計算腳本」）：
  1. 從 FinMind「逐交易日抓全市場」抓 4 個 dataset（日K／三大法人／外資持股／PER）。
  2. 對每檔股票用真實日K計算「發動訊號」、技術評等、相對強勢評分。
  3. 把算好的結果存成本地 JSON（data/stocks.json、data/details/<id>.json、data/market.json）。

設計重點：
  - Backer 方案 → 只給 date、不給 data_id，一次請求拿回該日全市場（最省請求）。
  - 速率限制 600 請求/小時：本地計數器，逼近上限前自動 sleep ~50 分再續（見 RateLimiter）。
  - 斷點續抓：以「dataset + 日期」為單位記錄進度，重跑時跳過已完成者（見 PROGRESS / raw 檔存在判斷）。
  - 全程 utf-8-sig 寫檔，避免中文亂碼。
  - Token 只從環境變數 FINMIND_TOKEN 讀，絕不硬編碼。

用法：
  set FINMIND_TOKEN=你的token            (Windows cmd)
  $env:FINMIND_TOKEN="你的token"          (PowerShell)
  python fetch_and_compute.py --days 35   # 煙霧測試（少量）
  python fetch_and_compute.py             # 預設 250 個交易日（完整，約 2 小時、會分批續抓）
  python fetch_and_compute.py --skip-fetch  # 不抓、只用既有 raw 重新計算

# ← 之後若改用 FinMind 官方 SDK 或其他資料源，只需替換「抓取層」，計算層（compute_*）不必動。
"""

import os
import sys
import json
import time
import argparse
import collections
from datetime import datetime, date
from pathlib import Path

import requests

# Windows console 預設 cp950 無法印「✓」「⏸」等符號 → 把 stdout/stderr 重設為 utf-8。
# Python 3.7+ 支援 reconfigure；errors='replace' 確保即使遇到無法表達的字也不會 crash。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ============================ 基本設定 ============================
BASE_URL = "https://api.finmindtrade.com/api/v4/data"
HOURLY_LIMIT = 600          # 帶 Token 速率限制：600 請求/小時
SAFE_LIMIT = 580            # 保守上限，逼近時主動休息
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DETAIL_DIR = DATA_DIR / "details"
PROGRESS_FILE = DATA_DIR / "progress.json"

# 要逐日抓的 dataset（皆支援「不帶 data_id、逐日抓全市場」）。順序：先日K最重要，其餘依序補。
DATASETS = [
    "TaiwanStockPrice",                                  # 日K（開高低收量）
    "TaiwanStockInstitutionalInvestorsBuySell",          # 三大法人買賣超
    "TaiwanStockShareholding",                           # 外資持股比率／發行股數
    "TaiwanStockPER",                                    # PER／PBR／殖利率
]

# 排除非普通股用的產業關鍵字（ETF、ETN、受益證券、指數等）
NON_COMMON_INDUSTRY = {"ETF", "ETN", "Index", "大盤", "受益證券", "ETN證券", ""}


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# JWT token 只含 [A-Za-z0-9._-]；任何空白／換行皆視為複貼噪音、一律剔除。
_TOKEN_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


def _sanitize_token(raw: str) -> str:
    """剔除 token 字串中所有空白、引號與不合法字元，避免 HTTP header 拒收。

    觸發過的真實 bug：使用者把 token 透過互動式問題複貼進 env var，內含 \\n 與多個前置空格，
    導致 requests 拋 'Invalid leading whitespace ... in header value' → fetch 全失敗。
    用白名單把雜訊全砍掉，比逐個字元案例化更穩。
    """
    return "".join(ch for ch in (raw or "") if ch in _TOKEN_OK)


def _load_token() -> str:
    """優先 env var；env 缺則 fallback 讀 .finmind_token 檔（單行 token）。"""
    raw = os.environ.get("FINMIND_TOKEN", "")
    if not raw.strip():
        token_file = ROOT / ".finmind_token"
        if token_file.exists():
            raw = token_file.read_text(encoding="utf-8", errors="replace")
    return _sanitize_token(raw)


def write_json(path: Path, obj):
    """一律以 utf-8-sig 寫檔，避免 Excel/記事本打開中文亂碼。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(obj, f, ensure_ascii=False)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ============================ 速率限制器（600/hr）============================
class RateLimiter:
    """維護近一小時內的請求時間戳；逼近上限前主動休息，確保不超過 FinMind 限制。"""
    def __init__(self, safe_limit=SAFE_LIMIT, window=3600):
        self.safe_limit = safe_limit
        self.window = window
        self.stamps = collections.deque()

    def acquire(self):
        now = time.time()
        # 移除超過一小時的舊紀錄
        while self.stamps and now - self.stamps[0] > self.window:
            self.stamps.popleft()
        # 若一小時內已達保守上限 → 睡到最舊那筆滿一小時為止
        if len(self.stamps) >= self.safe_limit:
            sleep_s = self.window - (now - self.stamps[0]) + 2
            mins = sleep_s / 60
            log(f"⏸ 已達 {self.safe_limit} 請求/小時保守上限，休息約 {mins:.1f} 分鐘後自動續抓…")
            time.sleep(max(1, sleep_s))
            return self.acquire()
        self.stamps.append(time.time())


# ============================ FinMind 抓取層 ============================
class FinMind:
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self.limiter = RateLimiter()
        self.session = requests.Session()

    def fetch(self, dataset, start_date=None, end_date=None, data_id=None, max_retry=3):
        """呼叫 /data，回傳 data 陣列。處理 402 超額與暫時性錯誤的重試。"""
        params = {"dataset": dataset}
        if data_id:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        for attempt in range(1, max_retry + 1):
            self.limiter.acquire()
            try:
                resp = self.session.get(BASE_URL, headers=self.headers, params=params, timeout=60)
            except requests.RequestException as e:
                log(f"  網路錯誤（{e}），10 秒後重試（{attempt}/{max_retry}）")
                time.sleep(10)
                continue

            if resp.status_code == 402:
                # 超出額度：休息一段時間再續（斷點續抓保證不重抓）
                log("  收到 402（額度用盡），休息 50 分鐘後續抓…")
                time.sleep(50 * 60)
                continue
            if resp.status_code == 429:
                log("  收到 429（請求過快），休息 60 秒…")
                time.sleep(60)
                continue
            if resp.status_code != 200:
                log(f"  HTTP {resp.status_code}，10 秒後重試（{attempt}/{max_retry}）：{resp.text[:120]}")
                time.sleep(10)
                continue

            payload = resp.json()
            # FinMind 正常回傳 status 200 與 data 陣列
            return payload.get("data", [])
        log(f"  ✗ {dataset} {start_date} 連續失敗，略過（之後重跑會自動補抓）")
        return []


# ============================ 交易日 / 股票池 ============================
def get_trading_dates(api: FinMind, days: int):
    """取 ≤ 今日的最後 N 個交易日。"""
    data = api.fetch("TaiwanStockTradingDate")
    today = date.today().isoformat()
    dates = sorted({row["date"] for row in data if row.get("date") and row["date"] <= today})
    if not dates:
        log("⚠ 無法取得交易日清單，改用價格資料推斷可能失敗，請檢查 token。")
    return dates[-days:]


def get_universe(api: FinMind):
    """取得普通股股票池（排除 ETF/ETN/權證/受益證券等）。回傳 {stock_id: name}。"""
    data = api.fetch("TaiwanStockInfo")
    universe = {}
    for row in data:
        sid = str(row.get("stock_id", ""))
        industry = (row.get("industry_category") or "").strip()
        # 普通股規則：4 碼純數字 + 產業別非 ETF/ETN/指數等（6 碼權證、0 開頭 ETF 自然濾掉）
        if len(sid) == 4 and sid.isdigit() and industry not in NON_COMMON_INDUSTRY:
            # 同一 stock_id 可能多筆（上市/上櫃），保留第一個名稱即可
            universe.setdefault(sid, row.get("stock_name", sid))
    return universe


# ============================ 逐日抓取（含斷點續抓）============================
def raw_path(dataset, d):
    return RAW_DIR / dataset / f"{d}.json"


def invalidate_recent(dates, datasets, refresh_latest):
    """每次跑都把「最新 N 個交易日」從快取剔除 → 強制重抓。

    為什麼：fetch_and_compute 用 dataset|date 為快取鍵；若早上跑過、把當日標為已完成，
    晚上盤後資料修正了卻會被當作「已抓」跳過。每次重抓最後 N 天即可吃到修正值，
    其餘較舊的日期仍走快取、不浪費請求。
    """
    if refresh_latest <= 0 or not dates:
        return
    targets = dates[-refresh_latest:]
    progress = set(read_json(PROGRESS_FILE, default=[]) or [])
    removed_keys = 0
    removed_files = 0
    for dataset in datasets:
        for d in targets:
            key = f"{dataset}|{d}"
            if key in progress:
                progress.discard(key)
                removed_keys += 1
            p = raw_path(dataset, d)
            if p.exists():
                try:
                    p.unlink()
                    removed_files += 1
                except OSError:
                    pass
    write_json(PROGRESS_FILE, sorted(progress))
    log(f"重抓最新 {refresh_latest} 個交易日（{targets[0]}~{targets[-1]}）："
        f"清掉 {removed_keys} 筆進度、{removed_files} 個 raw 檔。")


def fetch_all(api: FinMind, dates, datasets):
    """逐 dataset × 逐交易日抓全市場，存成 raw/<dataset>/<date>.json。已存在則跳過（續抓）。"""
    progress = set(read_json(PROGRESS_FILE, default=[]) or [])
    total = len(datasets) * len(dates)
    done = 0
    fetched_now = 0
    for dataset in datasets:
        for d in dates:
            key = f"{dataset}|{d}"
            p = raw_path(dataset, d)
            done += 1
            # 斷點續抓：進度檔已記錄或 raw 檔已存在 → 跳過，不重抓
            if key in progress or p.exists():
                continue
            rows = api.fetch(dataset, start_date=d, end_date=d)
            write_json(p, rows)
            progress.add(key)
            write_json(PROGRESS_FILE, sorted(progress))
            fetched_now += 1
            if done % 10 == 0 or rows:
                log(f"  抓取 {dataset} {d} → {len(rows)} 筆（進度 {done}/{total}）")
    log(f"✓ 抓取階段完成（本次實際抓 {fetched_now} 次／快取命中 {total - fetched_now} 次）")


# ============================ 載入 raw 並依股票歸戶 ============================
def load_dataset_by_stock(dataset, dates):
    """讀 raw/<dataset>/<date>.json，回傳 {stock_id: [row, ...]}（依日期排序）。"""
    by_stock = collections.defaultdict(list)
    for d in dates:
        rows = read_json(raw_path(dataset, d), default=[]) or []
        for row in rows:
            sid = str(row.get("stock_id", ""))
            if sid:
                by_stock[sid].append(row)
    for sid in by_stock:
        by_stock[sid].sort(key=lambda r: r.get("date", ""))
    return by_stock


# ============================ 策略計算（真邏輯，對齊前端 v2）============================
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def compute_signal(kline, inst_net_latest):
    """突破發動訊號（Cody「關鍵一條線」概念）。輸入真實日K，逐條計算。
    kline: [{open,high,low,close,volume,time}, ...]（時間升冪，最後一根=最新=第4日）。
    回傳 {fired, instBacked, signalIndex, conditions:[{key,label,pass}]}（欄位對齊前端）。"""
    n = len(kline) - 1
    if n < 1:
        return {"fired": False, "instBacked": inst_net_latest > 0,
                "signalIndex": n, "conditions": []}
    c = lambda i: kline[i]["close"]
    o = lambda i: kline[i]["open"]
    v = lambda i: kline[i]["volume"]

    # 條件1：量價突破——單日漲幅 > 4%
    c1 = c(n) > c(n - 1) * 1.04
    # 條件2：創近 15 個交易日（含當日）收盤新高
    lo2 = max(0, n - 14)
    c2 = c(n) >= max(c(i) for i in range(lo2, n + 1))
    # 條件3：放量——最新量 > 前 5 日均量 × 1.5
    prev5 = [v(i) for i in range(max(0, n - 5), n)]
    avg5 = sum(prev5) / len(prev5) if prev5 else v(n)
    c3 = v(n) > avg5 * 1.5
    # 條件4：動能濾網——近 20 日報酬為正
    c4 = (n - 20 >= 0) and c(n) > c(n - 20)
    # 條件5：「2 黑 1 紅」型態（n-3..n 為第1~4日）
    c5a = (n - 3 >= 0) and c(n - 3) > c(n - 2) > c(n - 1)        # 前三日收盤連續遞減
    c5b = (n - 2 >= 0) and (c(n - 2) < o(n - 2)) and (c(n - 1) < o(n - 1))  # 第2、3日收黑
    c5c = c(n) > o(n)                                            # 第4日翻紅

    conditions = [
        {"key": "c1",  "label": "量價突破：單日漲幅 > 4%",        "pass": bool(c1)},
        {"key": "c2",  "label": "創近 15 日收盤新高",             "pass": bool(c2)},
        {"key": "c3",  "label": "帶量上攻：量 > 前5日均量 ×1.5",   "pass": bool(c3)},
        {"key": "c4",  "label": "動能濾網：近 20 日報酬為正",      "pass": bool(c4)},
        {"key": "c5a", "label": "型態：前三日收盤連續遞減",        "pass": bool(c5a)},
        {"key": "c5b", "label": "型態：第2、3日收黑（2 黑）",      "pass": bool(c5b)},
        {"key": "c5c", "label": "型態：第4日翻紅突破（1 紅）",     "pass": bool(c5c)},
    ]
    fired = all(x["pass"] for x in conditions)
    return {"fired": fired, "instBacked": inst_net_latest > 0,
            "signalIndex": n, "conditions": conditions}


def compute_rating(kline):
    """技術評等（對標 TradingView 色階）：用 MA5/MA20/20日動能計分。"""
    n = len(kline) - 1
    c = lambda i: kline[i]["close"]
    def ma(p):
        seg = [c(i) for i in range(max(0, n - p + 1), n + 1)]
        return sum(seg) / len(seg)
    ma5, ma20 = ma(5), ma(20)
    bull = 0
    if c(n) > ma5: bull += 1
    if ma5 > ma20: bull += 1
    if n - 20 >= 0 and c(n) > c(n - 20): bull += 1
    if c(n) > ma20: bull += 1
    levels = [
        {"level": 0, "label": "強力偏空", "cls": "r-sd"},
        {"level": 1, "label": "偏空",     "cls": "r-d"},
        {"level": 2, "label": "中立",     "cls": "r-n"},
        {"level": 3, "label": "偏多",     "cls": "r-u"},
        {"level": 4, "label": "強力偏多", "cls": "r-su"},
    ]
    return levels[bull]


def compute_score(kline, inst_net_latest, foreign_pct):
    """相對強勢評分（0–100）：技術面 + 籌碼面客觀加權。公式透明、便於日後調整。
      a 動能(35%)：近20日報酬，-10%→0、+10%→1
      b 趨勢(25%)：相對20日均線位置，-5%→0、+5%→1
      c 強度(20%)：相對近60日高點，0.8→0、1.0→1
      d 籌碼(20%)：法人淨買超方向與幅度 + 外資比率微調
    """
    n = len(kline) - 1
    c = lambda i: kline[i]["close"]
    close = c(n)
    # 防呆：分母可能因停牌或缺資料為 0，全部退回中立 0.5。
    base20 = c(n - 20) if n - 20 >= 0 else 0
    ret20 = (close / base20 - 1) if base20 > 0 else 0.0
    a = clamp((ret20 + 0.10) / 0.20)
    seg20 = [c(i) for i in range(max(0, n - 19), n + 1)]
    ma20 = (sum(seg20) / len(seg20)) if seg20 else close
    b = clamp((close / ma20 - 1 + 0.05) / 0.10) if ma20 > 0 else 0.5
    seg60 = [c(i) for i in range(max(0, n - 59), n + 1)]
    hi60 = max(seg60) if seg60 else close
    c_ = clamp((close / hi60 - 0.8) / 0.20) if hi60 > 0 else 0.5
    d_inst = 0.5 + (0.5 if inst_net_latest > 0 else -0.5) * clamp(abs(inst_net_latest) / 5000.0)
    d_foreign = clamp((foreign_pct or 0) / 100.0) * 0.2
    d = clamp(d_inst * 0.8 + d_foreign)
    score = 100 * (0.35 * a + 0.25 * b + 0.20 * c_ + 0.20 * d)
    return int(round(clamp(score / 100) * 100))


# ============================ 聚合：把 raw 算成前端要的結構 ============================
def aggregate(dates, universe):
    log("讀取 raw 並逐股票計算…")
    price = load_dataset_by_stock("TaiwanStockPrice", dates)
    inst = load_dataset_by_stock("TaiwanStockInstitutionalInvestorsBuySell", dates)
    share = load_dataset_by_stock("TaiwanStockShareholding", dates)
    per = load_dataset_by_stock("TaiwanStockPER", dates)

    stocks_list = []   # 給市場總覽表（輕量）
    details = {}       # 給個股詳情頁（完整）

    for sid, name in universe.items():
        bars_raw = price.get(sid, [])
        if len(bars_raw) < 2:
            continue   # 資料太少無法計算，略過
        # --- 日K（量：股數→張）---
        # 過濾掉停牌/無交易的列（close <= 0 或 None/空字串）→ 避免 compute_signal/score 除以零。
        kline = []
        for r in bars_raw:
            try:
                cl = float(r.get("close", 0) or 0)
            except (TypeError, ValueError):
                cl = 0.0
            if cl <= 0:
                continue
            kline.append({
                "time": r["date"],
                "open": float(r.get("open", cl) or cl),
                "high": float(r.get("max", cl) or cl),
                "low": float(r.get("min", cl) or cl),
                "close": cl,
                "volume": int(round(float(r.get("Trading_Volume", 0) or 0) / 1000)),
            })
        if len(kline) < 2:
            continue

        # --- 三大法人合計淨額（近 30 日）---
        inst_by_date = collections.defaultdict(float)
        for r in inst.get(sid, []):
            net = (float(r.get("buy", 0)) - float(r.get("sell", 0))) / 1000.0   # 股→張
            inst_by_date[r["date"]] += net
        inst_items = sorted(inst_by_date.items())
        inst_bars = [{"time": d, "value": int(round(val))} for d, val in inst_items][-30:]
        inst_net_latest = inst_bars[-1]["value"] if inst_bars else 0
        # 法人連續買超天數（最新往前數）
        streak = 0
        for d, val in reversed(inst_items):
            if val > 0: streak += 1
            else: break

        # --- 外資持股比率（近 30 日趨勢）+ 發行股數（算市值）---
        share_rows = share.get(sid, [])
        foreign_trend = [{"time": r["date"],
                          "value": round(float(r.get("ForeignInvestmentSharesRatio", 0) or 0), 2)}
                         for r in share_rows if r.get("date")][-30:]
        foreign_pct = foreign_trend[-1]["value"] if foreign_trend else 0.0
        shares_issued = 0.0
        for r in reversed(share_rows):
            if r.get("NumberOfSharesIssued"):
                shares_issued = float(r["NumberOfSharesIssued"]); break

        # --- PER/PBR/殖利率（最新）---
        per_rows = per.get(sid, [])
        per_latest = per_rows[-1] if per_rows else {}
        per_val = _f(per_latest.get("PER"))
        pbr_val = _f(per_latest.get("PBR"))
        yield_val = _f(per_latest.get("dividend_yield"))

        # --- 盤面數字（由 K 線最末根換算，與圖表、訊號一致）---
        last, prev = kline[-1], kline[-2]
        prices_close = last["close"]
        change = round(prices_close - prev["close"], 2)
        change_pct = round((prices_close / prev["close"] - 1) * 100, 2) if prev["close"] else 0.0
        volume = last["volume"]
        turnover = round(prices_close * volume * 1000 / 1e8, 2)            # 成交額（億元）
        market_cap = int(round(prices_close * shares_issued / 1e8)) if shares_issued else 0  # 市值（億元）
        shares_e = round(shares_issued / 1e8, 2) if shares_issued else 0   # 億股
        spark = [b["close"] for b in kline[-25:]]

        # --- 策略計算 ---
        sig = compute_signal(kline, inst_net_latest)
        rating = compute_rating(kline)
        score = compute_score(kline, inst_net_latest, foreign_pct)

        # --- 市場表用（輕量）---
        stocks_list.append({
            "id": sid, "name": name,
            "price": prices_close, "change": change, "changePct": change_pct,
            "volume": volume, "turnover": turnover, "marketCap": market_cap,
            "instNet": inst_net_latest, "instStreak": streak,
            "foreignPct": foreign_pct, "score": score,
            "rating": rating, "ratingLevel": rating["level"],
            "fired": sig["fired"], "sig": {"instBacked": sig["instBacked"]},
            "sparkCloses": spark,
        })
        # --- 個股詳情用（完整）---
        details[sid] = {
            "id": sid, "name": name,
            "price": prices_close, "change": change, "changePct": change_pct,
            "volume": volume, "turnover": turnover, "marketCap": market_cap, "shares": shares_e,
            "instNet": inst_net_latest, "instStreak": streak,
            "foreignPct": foreign_pct, "score": score,
            "roe": None,                       # 指定 dataset 無 ROE 來源 → 前端顯示「—」
            "per": per_val, "pbr": pbr_val, "yieldPct": yield_val,
            "rating": rating, "ratingLevel": rating["level"], "fired": sig["fired"],
            "sig": sig,
            "kline": kline, "instBars": inst_bars, "foreignTrend": foreign_trend,
            "sparkCloses": spark,
        }

    return stocks_list, details


def _f(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


def build_market(api_dates, stocks_list):
    """大盤摘要：漲跌家數、發動檔數、總成交額、更新時間（TAIEX 由報酬指數估示意）。"""
    up = sum(1 for s in stocks_list if s["changePct"] > 0)
    down = sum(1 for s in stocks_list if s["changePct"] < 0)
    flat = len(stocks_list) - up - down
    fired = sum(1 for s in stocks_list if s["fired"])
    turnover = round(sum(s["turnover"] for s in stocks_list), 2)
    return {
        "date": api_dates[-1] if api_dates else "",
        "up": up, "down": down, "flat": flat,
        "fired": fired, "totalTurnover": turnover,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }


# ============================ 主流程 ============================
def main():
    parser = argparse.ArgumentParser(description="FinMind 逐日全市場抓取 + 策略計算")
    parser.add_argument("--days", type=int, default=250, help="抓最近 N 個交易日（預設 250）")
    parser.add_argument("--skip-fetch", action="store_true", help="不抓取，只用既有 raw 重新計算")
    parser.add_argument("--refresh-latest", type=int, default=1,
                        help="每次跑強制重抓最新 N 個交易日（盤後修正用，預設 1；設 0 完全靠快取）")
    args = parser.parse_args()

    token = _load_token()
    if not token:
        log("✗ 未取得 FINMIND_TOKEN。請於 PowerShell 設定 $env:FINMIND_TOKEN='...'，"
            "或於專案目錄放 .finmind_token 檔（單行 token、不入 git）。")
        sys.exit(1)

    api = FinMind(token)
    DATA_DIR.mkdir(exist_ok=True)

    # 1) 交易日 + 股票池（各一次請求）
    log(f"取得最近 {args.days} 個交易日與股票池…")
    dates = get_trading_dates(api, args.days)
    if not dates:
        log("✗ 取不到交易日，終止。"); sys.exit(1)
    log(f"交易日範圍：{dates[0]} ~ {dates[-1]}（{len(dates)} 日）")

    universe = get_universe(api)
    write_json(DATA_DIR / "universe.json", universe)
    log(f"普通股股票池：{len(universe)} 檔（已排除 ETF/ETN/權證等）")

    # 2) 逐日抓全市場（可斷點續抓 + 強制重抓最新 N 日）
    if not args.skip_fetch:
        invalidate_recent(dates, DATASETS, args.refresh_latest)
        fetch_all(api, dates, DATASETS)
    else:
        log("略過抓取，直接用既有 raw 計算。")

    # 3) 聚合 + 計算 + 存檔
    stocks_list, details = aggregate(dates, universe)
    stocks_list.sort(key=lambda s: s["score"], reverse=True)

    write_json(DATA_DIR / "stocks.json", stocks_list)
    for sid, d in details.items():
        write_json(DETAIL_DIR / f"{sid}.json", d)
    write_json(DATA_DIR / "market.json", build_market(dates, stocks_list))

    fired_n = sum(1 for s in stocks_list if s["fired"])
    log(f"✓ 完成：{len(stocks_list)} 檔可用，其中 {fired_n} 檔符合發動訊號。")
    log(f"  輸出：data/stocks.json、data/details/*.json、data/market.json")


if __name__ == "__main__":
    main()
