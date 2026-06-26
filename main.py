# -*- coding: utf-8 -*-
"""
main.py —— 台股選股網頁 v3 的 FastAPI 後端。

職責（任務規格第五節）：
  只「讀取」fetch_and_compute.py 算好的本地結果，回應前端 API；
  完全不在請求時呼叫 FinMind（線上讀檔、零外部依賴）。

設計重點：
  - Store 類在啟動時把 stocks.json / market.json / universe.json 一次性 load 進記憶體；
    每個 endpoint 進入前用 mtime 比對自動 reload（fetch 跑完後不用重啟）。
  - details/<id>.json 用 lru_cache 延遲載入（避免啟動掃幾百個檔）。
  - JSON 回傳中文不轉 \\uXXXX（自訂 UTF8JSONResponse）。
  - 同時 mount StaticFiles 在 /，瀏覽器訪問 http://localhost:8000/ 即可看到 index.html。
  - 開發階段 CORS 全開，避免日後拆 server 時還要回頭改。
  - data/ 不存在 → 503 + 中文 hint；stock_id 不存在 → 404。

用法：
  python main.py
  # 等同：uvicorn main:app --host 127.0.0.1 --port 8000 --reload
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DETAIL_DIR = DATA_DIR / "details"
STOCKS_FILE = DATA_DIR / "stocks.json"
MARKET_FILE = DATA_DIR / "market.json"
UNIVERSE_FILE = DATA_DIR / "universe.json"


# ============================ JSON 中文不轉 \uXXXX ============================
class UTF8JSONResponse(JSONResponse):
    """覆寫預設 JSONResponse：ensure_ascii=False，讓 curl 與肉眼除錯看得到中文。"""

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _read_json(path: Path):
    """fetch_and_compute.py 用 utf-8-sig 寫檔，這裡也用 utf-8-sig 讀以容忍 BOM。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ============================ 資料載入：Store + mtime 自動 reload ============================
# _load_detail 必須先宣告，Store.refresh_if_changed() 會呼叫它的 cache_clear()。
@lru_cache(maxsize=512)
def _load_detail(stock_id: str):
    """個股詳情 lazy 載入；首次請求才讀檔。回 None 代表找不到。"""
    p = DETAIL_DIR / f"{stock_id}.json"
    if not p.exists():
        return None
    return _read_json(p)


class Store:
    """把 stocks / market / universe 載入記憶體；mtime 變了自動 reload。

    為什麼：每次請求重讀 JSON 太浪費；但又不想 fetch 完還要重啟 server。
    取捨：只看 stocks.json 的 mtime 作為「資料世代」指標（三個檔同批寫出，看一個就夠）。
    """

    def __init__(self):
        self.stocks: list = []
        self.market: dict = {}
        self.universe: dict = {}
        self._mtime: float = 0.0
        self.refresh_if_changed()

    def refresh_if_changed(self):
        if not STOCKS_FILE.exists():
            # 資料還沒生成；endpoint 各自會回 503。
            self.stocks, self.market, self.universe = [], {}, {}
            self._mtime = 0.0
            return
        mtime = STOCKS_FILE.stat().st_mtime
        if mtime == self._mtime:
            return
        self.stocks = _read_json(STOCKS_FILE) if STOCKS_FILE.exists() else []
        self.market = _read_json(MARKET_FILE) if MARKET_FILE.exists() else {}
        self.universe = _read_json(UNIVERSE_FILE) if UNIVERSE_FILE.exists() else {}
        self._mtime = mtime
        # detail cache 也要清，否則舊資料殘留。
        _load_detail.cache_clear()


store = Store()


def _ensure_data_ready():
    """資料未生成時統一回 503，避免 500 stack trace 嚇到使用者。"""
    store.refresh_if_changed()
    if not store.stocks:
        raise HTTPException(
            status_code=503,
            detail="資料尚未產生，請先執行 python fetch_and_compute.py --days 35",
        )


# ============================ FastAPI 應用 ============================
app = FastAPI(
    title="台股選股網頁後端 v3",
    description="只讀 fetch_and_compute.py 算好的本地 JSON，回應前端。",
    default_response_class=UTF8JSONResponse,
)

# 開發階段全開；上線改成具體 origin。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ============================ API endpoints ============================
@app.get("/api/market")
def api_market():
    """大盤摘要（fetch_and_compute 直出 market.json）。"""
    _ensure_data_ready()
    return store.market


@app.get("/api/stocks")
def api_stocks():
    """市場總覽表：含 sparkCloses 近 25 點，供前端 sparkline 直接畫。"""
    _ensure_data_ready()
    return store.stocks


@app.get("/api/stock/{stock_id}")
def api_stock(stock_id: str):
    """個股詳情頁：K 線、法人 30 日、外資趨勢、PER/PBR/殖利率、各策略條件通過明細。"""
    _ensure_data_ready()
    detail = _load_detail(stock_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"找不到股票 {stock_id}，可能未上市或資料尚未計算",
        )
    return detail


@app.get("/api/screener")
def api_screener(
    breakout: Optional[int] = Query(None, description="1=只回符合發動訊號"),
    instbuy: Optional[int] = Query(None, description="1=只回三大法人最新淨買超 > 0"),
    score: Optional[float] = Query(None, description="評分門檻：>= score 才入選"),
    streak: Optional[int] = Query(None, description="法人連續買超天數門檻"),
    foreign: Optional[float] = Query(None, description="外資持股比率門檻 (%)"),
):
    """策略篩選器：依條件過濾 store.stocks。未給的條件不啟用。"""
    _ensure_data_ready()
    result = store.stocks
    if breakout:
        result = [s for s in result if s.get("fired")]
    if instbuy:
        result = [s for s in result if (s.get("instNet") or 0) > 0]
    if score is not None:
        result = [s for s in result if (s.get("score") or 0) >= score]
    if streak is not None:
        result = [s for s in result if (s.get("instStreak") or 0) >= streak]
    if foreign is not None:
        result = [s for s in result if (s.get("foreignPct") or 0) >= foreign]
    return result


# ============================ 靜態檔掛載 ============================
# 必須在所有 /api/* 路由註冊「之後」掛載，因為 StaticFiles 是 catch-all。
# 瀏覽器訪問 http://localhost:8000/ 直接看到 index.html，免雙伺服器。
app.mount("/", StaticFiles(directory=str(ROOT), html=True), name="static")


# ============================ 啟動 ============================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
