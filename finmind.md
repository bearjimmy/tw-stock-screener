# FinMind 金融資料平台 中文使用手冊

> FinMind 是一個開源金融數據平台，提供 **75+ 台灣市場資料集**與國際數據（美、英、歐、日股），透過 RESTful API 每日更新。
> 官方文件：https://finmind.github.io

---

## 目錄

- [快速開始](#快速開始)
- [API 基本資訊](#api-基本資訊)
- [會員等級說明](#會員等級說明)
- [認證登入](#認證登入)
- [Python SDK 使用方式](#python-sdk-使用方式)
- [台灣市場資料集](#台灣市場資料集)
  - [技術面（股價類）](#技術面股價類)
  - [籌碼面（法人類）](#籌碼面法人類)
  - [基本面（財報類）](#基本面財報類)
  - [衍生商品（期貨選擇權）](#衍生商品期貨選擇權)
  - [即時資訊](#即時資訊)
  - [可轉債](#可轉債)
  - [其他資料](#其他資料)
- [國際市場資料集](#國際市場資料集)
- [全球經濟數據](#全球經濟數據)
- [常用查詢範例](#常用查詢範例)

---

## 快速開始

```bash
# 安裝 Python SDK
pip install FinMind
```

```python
from FinMind.data import DataLoader

api = DataLoader()
api.login_by_token(api_token='你的token')

# 取得台積電股價
df = api.taiwan_stock_daily(
    stock_id='2330',
    start_date='2024-01-01',
    end_date='2024-12-31'
)
print(df)
```

---

## API 基本資訊

| 項目 | 說明 |
|------|------|
| **Base URL** | `https://api.finmindtrade.com/api/v4` |
| **速率限制（有Token）** | 600 請求 / 小時 |
| **速率限制（無Token）** | 300 請求 / 小時 |
| **超額回傳** | HTTP 402 錯誤 |
| **狀態監控** | https://status.finmindtrade.com |

### 四個核心端點

| 端點 | 方法 | 功能 |
|------|------|------|
| `/login` | POST | 登入取得 Token |
| `/data` | GET | 查詢資料集 |
| `/datalist` | GET | 列出可用的 data_id |
| `/translation` | GET | 欄位中英文對照 |

---

## 會員等級說明

| 等級 | 費用 | 可用資料 |
|------|------|----------|
| **Free（免費）** | 免費 | 基本股價、PER、三大法人等 |
| **Backer** | 付費 | 更多資料集（分K、週月K、持股分級等）|
| **Sponsor** | 付費 | 全部資料集（含即時、分點、分鐘級）|

> 大部分資料集：帶 `data_id`（指定個股）可用 Free；不帶 `data_id`（全市場）需要 Backer/Sponsor。

---

## 認證登入

### 方法一：API 登入取得 Token

```python
import requests

url = "https://api.finmindtrade.com/api/v4/login"
params = {
    "user_id": "你的帳號",
    "password": "你的密碼"
}
resp = requests.post(url, params=params)
token = resp.json()["token"]
print(token)
```

### 方法二：帶 Token 呼叫 API

```python
import requests

url = "https://api.finmindtrade.com/api/v4/data"
headers = {"Authorization": f"Bearer {token}"}
params = {
    "dataset": "TaiwanStockPrice",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01",
}
resp = requests.get(url, headers=headers, params=params)
data = resp.json()["data"]
```

> **Token 重設**：可在帳戶頁面自助重設，舊 Token 立即失效。

---

## Python SDK 使用方式

### 安裝

```bash
pip install FinMind
```

### 登入方式

```python
from FinMind.data import DataLoader

api = DataLoader()

# 方式一：Token 登入（推薦）
api.login_by_token(api_token='你的token')

# 方式二：帳號密碼登入
api.login(user_id='你的帳號', password='你的密碼')
```

### 查詢目前 API 使用額度

```python
print(api.api_usage_limit)
```

### 批量異步查詢（多支股票）

```python
df = api.taiwan_stock_daily(
    stock_id_list=['2330', '2317', '2454'],
    start_date='2024-01-01',
    end_date='2024-12-31',
    use_async=True   # 開啟異步，速度更快
)
```

---

## 台灣市場資料集

### 技術面（股價類）

#### TaiwanStockInfo｜台股清單總覽

- **等級**：Free
- **欄位**：`industry_category`（產業類別）, `stock_id`, `stock_name`, `type`, `date`
- **說明**：列出所有台股代碼與產業分類

```python
params = {"dataset": "TaiwanStockInfo"}
```

---

#### TaiwanStockTradingDate｜台股交易日曆

- **等級**：Free
- **欄位**：`date`
- **說明**：列出所有交易日，可用於判斷某日是否為交易日

```python
params = {"dataset": "TaiwanStockTradingDate"}
```

---

#### TaiwanStockPrice｜股價日成交資訊 ⭐ 最常用

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：1994-10-01
- **欄位**：

| 欄位 | 說明 |
|------|------|
| `date` | 日期 |
| `stock_id` | 股票代碼 |
| `open` | 開盤價 |
| `max` | 最高價 |
| `min` | 最低價 |
| `close` | 收盤價 |
| `spread` | 漲跌價差 |
| `Trading_Volume` | 成交量（股數）|
| `Trading_money` | 成交金額 |
| `Trading_turnover` | 成交筆數 |

```python
params = {
    "dataset": "TaiwanStockPrice",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01"
}
```

---

#### TaiwanStockPriceAdj｜台灣還原股價

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：1994-10-01
- **欄位**：同 `TaiwanStockPrice`
- **說明**：**除權息還原後的股價**，計算報酬率時應使用此資料集

```python
params = {
    "dataset": "TaiwanStockPriceAdj",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01"
}
```

---

#### TaiwanStockPriceTick｜逐筆成交明細

- **等級**：Backer/Sponsor
- **資料起始**：2019-01-01
- **欄位**：`date`, `stock_id`, `deal_price`, `volume`, `Time`, `TickType`
  - TickType：0=未知, 1=賣方成交, 2=買方成交
- **注意**：**單日單次請求**（start_date 只填一天）

---

#### TaiwanStockPER｜個股 PER、PBR、殖利率

- **等級**：Free
- **資料起始**：2005-10-01
- **欄位**：`date`, `stock_id`, `dividend_yield`（殖利率）, `PER`（本益比）, `PBR`（股價淨值比）

```python
params = {
    "dataset": "TaiwanStockPER",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01"
}
```

---

#### TaiwanStockKBar｜台股分 K（分鐘 K 線）

- **等級**：Sponsor
- **資料起始**：2019-01-01
- **欄位**：`date`, `minute`, `stock_id`, `open`, `high`, `low`, `close`, `volume`
- **注意**：**單日單次請求**

---

#### TaiwanStockWeekPrice｜週 K 資料

- **等級**：Backer/Sponsor
- **資料起始**：2000-01-01
- **欄位**：`stock_id`, `yweek`, `max`, `min`, `trading_volume`, `date`, `close`, `open`, `spread`

---

#### TaiwanStockMonthPrice｜月 K 資料

- **等級**：Backer/Sponsor
- **資料起始**：2000-01-01
- **欄位**：`stock_id`, `ymonth`, `max`, `min`, `trading_volume`, `date`, `close`, `open`, `spread`

---

#### TaiwanStockDayTrading｜當日沖銷統計

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2014-01-01
- **欄位**：`stock_id`, `date`, `BuyAfterSale`（先買後賣量）, `Volume`, `BuyAmount`, `SellAmount`

---

#### TaiwanStockTotalReturnIndex｜加權/櫃買報酬指數

- **等級**：Free
- **資料起始**：2003-01-01
- **欄位**：`price`, `stock_id`, `date`
- **data_id 可填**：`TAIEX`（加權指數）或 `TPEx`（櫃買指數）

---

#### TaiwanStockPriceLimit｜每日漲跌停價

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2000-01-01
- **欄位**：`date`, `stock_id`, `reference_price`（參考價）, `limit_up`（漲停）, `limit_down`（跌停）

---

#### TaiwanStockStatisticsOfOrderBookAndTrade｜每5秒委託成交統計

- **等級**：Free
- **欄位**：`Time`, `TotalBuyOrder`, `TotalBuyVolume`, `TotalSellOrder`, `TotalSellVolume`, `TotalDealOrder`, `TotalDealVolume`, `TotalDealMoney`, `date`
- **注意**：**單日單次請求**

---

### 籌碼面（法人類）

#### TaiwanStockInstitutionalInvestorsBuySell｜三大法人買賣超 ⭐

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2005-01-01
- **欄位**：`date`, `stock_id`, `name`（外資/投信/自營商）, `buy`, `sell`

```python
params = {
    "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01"
}
```

---

#### TaiwanStockInstitutionalInvestorsBuySellWide｜三大法人買賣超（寬表）

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2005-01-01
- **欄位（每個法人分開欄位）**：

| 欄位 | 說明 |
|------|------|
| `Foreign_Investor_buy/sell` | 外資買賣 |
| `Foreign_Dealer_Self_buy/sell` | 外資自營買賣 |
| `Investment_Trust_buy/sell` | 投信買賣 |
| `Dealer_buy/sell` | 自營商買賣 |
| `Dealer_self_buy/sell` | 自營商自有買賣 |
| `Dealer_Hedging_buy/sell` | 自營商避險買賣 |

---

#### TaiwanStockMarginPurchaseShortSale｜個股融資融券

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2001-01-01
- **主要欄位**：
  - `MarginPurchaseTodayBalance`：融資今日餘額
  - `MarginPurchaseYesterdayBalance`：融資昨日餘額
  - `ShortSaleTodayBalance`：融券今日餘額
  - `ShortSaleYesterdayBalance`：融券昨日餘額

---

#### TaiwanStockShareholding｜外資持股比例

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2004-02-01
- **主要欄位**：`date`, `stock_id`, `ForeignInvestmentShares`（外資持股數）, `ForeignInvestmentSharesRatio`（外資持股比例）, `ForeignInvestmentUpperLimitRatio`（外資持股上限）, `NumberOfSharesIssued`（發行股數）

---

#### TaiwanStockHoldingSharesPer｜股權持股分級表

- **等級**：Backer/Sponsor
- **資料起始**：2010-01-29
- **欄位**：`date`, `stock_id`, `HoldingSharesLevel`（持股層級）, `people`（人數）, `percent`（佔比）, `unit`（張數）
- **說明**：分析大戶/散戶籌碼集中度

---

#### TaiwanStockSecuritiesLending｜借券成交明細

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2001-05-01
- **欄位**：`date`, `stock_id`, `transaction_type`, `volume`, `fee_rate`, `close`

---

#### TaiwanStockTradingDailyReport｜台股分點資料（券商進出）

- **等級**：Sponsor
- **資料起始**：2021-06-30
- **欄位**：`securities_trader`（券商名稱）, `securities_trader_id`（券商代碼）, `stock_id`, `price`, `buy`, `sell`, `date`
- **特殊端點**：`GET /api/v4/taiwan_stock_trading_daily_report`
- **注意**：**只接受 `date` 參數（單日查詢）**，可用股票代碼或券商代碼查詢

---

#### TaiwanstockGovernmentBankBuySell｜八大行庫買賣

- **等級**：Sponsor
- **資料起始**：2021-06-30
- **欄位**：`date`, `stock_id`, `buy_amount`, `sell_amount`, `buy`, `sell`, `bank_name`

---

#### TaiwanStockDispositionSecuritiesPeriod｜處置有價證券

- **等級**：Backer/Sponsor
- **資料起始**：2001-01-01
- **欄位**：`date`, `stock_id`, `disposition_cnt`（處置次數）, `condition`, `measure`, `period_start`, `period_end`

---

### 基本面（財報類）

#### TaiwanStockFinancialStatements｜綜合損益表

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：1990-03-01（最完整）
- **欄位**：`date`, `stock_id`, `type`（項目名稱）, `value`（數值）, `origin_name`（原始名稱）
- **說明**：包含營收、毛利、營業利益、稅後淨利等損益項目

```python
params = {
    "dataset": "TaiwanStockFinancialStatements",
    "data_id": "2330",
    "start_date": "2020-01-01"
}
```

---

#### TaiwanStockBalanceSheet｜資產負債表

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2011-12-01
- **欄位**：`date`, `stock_id`, `type`, `value`, `origin_name`

---

#### TaiwanStockCashFlowsStatement｜現金流量表

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2008-06-01
- **欄位**：`date`, `stock_id`, `type`, `value`, `origin_name`

---

#### TaiwanStockDividend｜股利政策表

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2005-05-01
- **主要欄位**：

| 欄位 | 說明 |
|------|------|
| `CashEarningsDistribution` | 現金股利（盈餘分配）|
| `CashStatutorySurplus` | 現金股利（法定盈餘公積）|
| `CashExDividendTradingDate` | 現金除息日 |
| `CashDividendPaymentDate` | 現金股利發放日 |
| `StockEarningsDistribution` | 股票股利（盈餘分配）|
| `StockExDividendTradingDate` | 股票除息日 |

---

#### TaiwanStockDividendResult｜除權除息結果

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2003-05-01
- **欄位**：`date`, `stock_id`, `before_price`, `after_price`, `stock_and_cache_dividend`, `reference_price`

---

#### TaiwanStockMonthRevenue｜月營收表 ⭐

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2002-02-01
- **欄位**：`date`, `stock_id`, `revenue`（當月營收）, `revenue_month`, `revenue_year`

```python
params = {
    "dataset": "TaiwanStockMonthRevenue",
    "data_id": "2330",
    "start_date": "2023-01-01"
}
```

---

#### TaiwanStockMarketValue｜台灣個股市值

- **等級**：Backer/Sponsor
- **資料起始**：2004-01-01
- **欄位**：`date`, `stock_id`, `market_value`（市值，單位：元）

---

#### TaiwanStockDelisting｜台灣股票下市紀錄

- **等級**：Free
- **資料起始**：2001-01-01
- **欄位**：`date`, `stock_id`, `stock_name`

---

#### TaiwanStockCapitalReductionReferencePrice｜減資後參考價

- **等級**：Free
- **資料起始**：2011-01-01
- **欄位**：`date`, `stock_id`, `ClosingPriceonTheLastTradingDay`, `PostReductionReferencePrice`, `LimitUp`, `LimitDown`, `ReasonforCapitalReduction`

---

### 衍生商品（期貨選擇權）

#### TaiwanFuturesDaily｜期貨日成交資訊

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：1998-07-01
- **欄位**：`date`, `futures_id`, `contract_date`（合約月份）, `open`, `max`, `min`, `close`, `spread`, `volume`, `settlement_price`（結算價）, `open_interest`（未平倉量）, `trading_session`（日盤/夜盤）
- **常用 data_id**：`TX`（台指期）, `MTX`（小台）, `TE`（電子期）, `TF`（金融期）

---

#### TaiwanOptionDaily｜選擇權日成交資訊

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2001-12-01
- **欄位**：`date`, `option_id`, `contract_date`, `strike_price`（履約價）, `call_put`（買權/賣權）, `open`, `max`, `min`, `close`, `volume`, `open_interest`

---

#### TaiwanFuturesInstitutionalInvestors｜期貨三大法人

- **等級**：Free（帶 data_id）/ Backer/Sponsor（全市場）
- **資料起始**：2018-06-05
- **欄位**：`date`, `futures_id`, `institutional_investors`（法人名稱）, `long_deal_volume`（多單成交量）, `short_deal_volume`（空單成交量）, `long_open_interest_balance_volume`（多單未平倉）, `short_open_interest_balance_volume`（空單未平倉）

---

#### TaiwanFuturesTick｜期貨逐筆成交

- **等級**：Backer/Sponsor
- **資料起始**：2011-01-03
- **欄位**：`contract_date`, `date`, `futures_id`, `price`, `volume`
- **注意**：**單日單次請求**

---

#### TaiwanFuturesOpenInterestLargeTraders｜期貨大額交易人未沖銷部位

- **等級**：Backer/Sponsor
- **資料起始**：1998-07-01
- **欄位**：`date`, `futures_id`, 前五大/前十大交易人多空部位及比例

---

#### TaiwanFuturesFinalSettlementPrice｜期貨最後結算價

- **等級**：Backer/Sponsor
- **資料起始**：1998-01-01
- **欄位**：`date`, `contract_month`, `futures_id`, `futures_name`, `settlement_price`

---

### 即時資訊

> **注意**：即時資訊均需 **Sponsor** 等級

#### taiwan_stock_tick_snapshot｜台股即時快照

- **欄位**：`stock_id`, `date`, `open`, `high`, `low`, `close`, `volume`, `total_volume`, `buy_price`, `buy_volume`, `sell_price`, `sell_volume`, `change_price`, `change_rate`, `average_price`, `volume_ratio`, `TickType`

```python
params = {
    "dataset": "taiwan_stock_tick_snapshot",
    "data_id": "2330"
}
```

---

#### taiwan_futures_snapshot｜期貨即時快照

- **欄位**：`futures_id`, `open`, `high`, `low`, `close`, `volume`, `total_volume`, `buy_price`, `sell_price`, `change_price`, `change_rate`

---

#### taiwan_options_snapshot｜選擇權即時快照

- **欄位**：`options_id`, `open`, `high`, `low`, `close`, `volume`, `change_rate`, `buy_price`, `sell_price`

---

### 可轉債

#### TaiwanStockConvertibleBondDaily｜可轉債日成交資訊

- **等級**：Backer/Sponsor
- **欄位**：`cb_id`, `cb_name`, `close`, `open`, `max`, `min`, `trading_value`, `date`

---

#### TaiwanStockConvertibleBondDailyOverview｜可轉債每日總覽

- **等級**：Backer/Sponsor
- **欄位**：`cb_id`, `ConversionPrice`（轉換價）, `CouponRate`（票面利率）, `OutstandingAmount`（剩餘發行量）, `InitialDateOfConversion`, `DueDateOfConversion`, `EarlyRedemptionPrice`

---

### 其他資料

#### TaiwanStockNews｜個股相關新聞

- **等級**：Free
- **欄位**：`date`, `stock_id`, `title`, `description`, `link`, `source`
- **注意**：**單日單次請求**

---

#### TaiwanBusinessIndicator｜台灣景氣對策信號

- **等級**：Backer/Sponsor
- **資料起始**：1982-01-01
- **欄位**：`date`, `monitoring`（分數）, `monitoring_color`（燈號顏色：紅/黃紅/綠/黃藍/藍）, `leading`（領先指標）, `coincident`（同時指標）, `lagging`（落後指標）

---

#### TaiwanStockIndustryChain｜個體公司所屬產業鏈

- **等級**：Backer/Sponsor
- **欄位**：`stock_id`, `industry`（產業）, `sub_industry`（子產業）, `date`

---

## 國際市場資料集

### 美股（US Stock）

| 資料集 | 說明 | 欄位 |
|--------|------|------|
| `USStockInfo` | 美股基本資訊 | stock_id, stock_name, industry, market_cap |
| `USStockPrice` | 美股日 K 線 | date, stock_id, open, max, min, close, volume, adj_close |
| `USStockPriceMinute` | 美股分鐘 K（Backer+）| date, minute, stock_id, open, high, low, close, volume |

```python
# Python SDK 查詢美股
df = api.us_stock_daily(
    stock_id='AAPL',
    start_date='2024-01-01',
    end_date='2024-06-01'
)
```

---

### 日股（Japan Stock）

| 資料集 | 說明 |
|--------|------|
| `JapanStockInfo` | 日股基本資訊（代碼、交易所、產業分類）|
| `JapanStockPrice` | 日股日 K 線及調整收盤價 |

---

### 英股（UK Stock）

| 資料集 | 說明 |
|--------|------|
| `UKStockInfo` | 英股基本資訊（代碼、公司名、國家）|
| `UKStockPrice` | 英股日 K 線及調整收盤價 |

---

### 歐股（Europe Stock）

| 資料集 | 說明 |
|--------|------|
| `EuropeStockInfo` | 歐股基本資訊（代碼、市場、公司名）|
| `EuropeStockPrice` | 歐股日 K 線及調整收盤價 |

---

## 全球經濟數據

#### TaiwanExchangeRate｜外幣對台幣匯率

- **欄位**：`date`, `currency`, 現鈔買入, 現鈔賣出, 即期買入, 即期賣出
- **常用 data_id**：`USD`, `EUR`, `JPY`, `CNY`, `HKD`, `GBP`（共 18 種貨幣）

```python
params = {
    "dataset": "TaiwanExchangeRate",
    "data_id": "USD",
    "start_date": "2024-01-01"
}
```

---

#### InterestRate｜全球央行基準利率

- **欄位**：`country`, `date`, `interest_rate`
- **常用 data_id**：`FED`（美聯準會）, `ECB`（歐央行）, `BOJ`（日銀）（共 12 家央行）

---

#### GoldPrice｜黃金現貨價格

- **欄位**：`date`, `Price`

---

#### CrudeOilPrices｜原油價格

- **欄位**：`date`, `name`, `price`
- **data_id**：`WTI`（西德克薩斯中間基原油）或 `Brent`（布蘭特原油）

---

#### GovernmentBondsYield｜美國國債殖利率

- **欄位**：`date`, `name`（天期）, `value`（殖利率 %）
- **data_id**：可查詢 1月期、3月期、6月期、1年、2年、5年、10年、30年等多檔

---

#### CnnFearGreedIndex｜CNN 恐懼貪婪指數

- **欄位**：`date`, `fear_greed`（數值 0~100）, `fear_greed_emotion`（Extreme Fear / Fear / Neutral / Greed / Extreme Greed）

---

## 常用查詢範例

### 範例一：取得台積電完整資料（股價 + 法人 + PER）

```python
from FinMind.data import DataLoader
import pandas as pd

api = DataLoader()
api.login_by_token(api_token='你的token')

# 股價（還原後）
price = api.taiwan_stock_daily(
    stock_id='2330',
    start_date='2023-01-01',
    end_date='2024-01-01',
    adjusted_price=True  # 取還原股價
)

# 三大法人
institutional = api.taiwan_stock_institutional_investors(
    stock_id='2330',
    start_date='2023-01-01',
    end_date='2024-01-01'
)

# PER / PBR
per = api.taiwan_stock_per_pbr(
    stock_id='2330',
    start_date='2023-01-01',
    end_date='2024-01-01'
)
```

---

### 範例二：直接呼叫 REST API 取得月營收

```python
import requests
import pandas as pd

token = "你的token"
url = "https://api.finmindtrade.com/api/v4/data"

params = {
    "dataset": "TaiwanStockMonthRevenue",
    "data_id": "2330",
    "start_date": "2023-01-01",
    "token": token
}

resp = requests.get(url, params=params)
df = pd.DataFrame(resp.json()["data"])
print(df)
```

---

### 範例三：批量取得多支股票股價（異步）

```python
from FinMind.data import DataLoader

api = DataLoader()
api.login_by_token(api_token='你的token')

stock_list = ['2330', '2317', '2454', '2382', '3711']

df = api.taiwan_stock_daily(
    stock_id_list=stock_list,
    start_date='2023-01-01',
    end_date='2024-01-01',
    use_async=True
)
print(df.groupby('stock_id').size())  # 各股筆數
```

---

### 範例四：取得融資融券資料

```python
params = {
    "dataset": "TaiwanStockMarginPurchaseShortSale",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "end_date": "2024-06-01",
    "token": "你的token"
}
resp = requests.get("https://api.finmindtrade.com/api/v4/data", params=params)
df = pd.DataFrame(resp.json()["data"])
print(df[['date', 'MarginPurchaseTodayBalance', 'ShortSaleTodayBalance']])
```

---

## 資料集快速查詢索引

| 需求 | 資料集名稱 | 等級 |
|------|-----------|------|
| 台股清單 | `TaiwanStockInfo` | Free |
| 日K線（原始）| `TaiwanStockPrice` | Free |
| 日K線（還原）| `TaiwanStockPriceAdj` | Free |
| 分K線 | `TaiwanStockKBar` | Sponsor |
| 週K線 | `TaiwanStockWeekPrice` | Backer |
| 月K線 | `TaiwanStockMonthPrice` | Backer |
| 本益比/淨值比 | `TaiwanStockPER` | Free |
| 三大法人（長表）| `TaiwanStockInstitutionalInvestorsBuySell` | Free |
| 三大法人（寬表）| `TaiwanStockInstitutionalInvestorsBuySellWide` | Free |
| 融資融券 | `TaiwanStockMarginPurchaseShortSale` | Free |
| 外資持股 | `TaiwanStockShareholding` | Free |
| 持股分級（大戶）| `TaiwanStockHoldingSharesPer` | Backer |
| 分點券商進出 | `TaiwanStockTradingDailyReport` | Sponsor |
| 八大行庫 | `TaiwanstockGovernmentBankBuySell` | Sponsor |
| 損益表 | `TaiwanStockFinancialStatements` | Free |
| 資產負債表 | `TaiwanStockBalanceSheet` | Free |
| 現金流量表 | `TaiwanStockCashFlowsStatement` | Free |
| 股利政策 | `TaiwanStockDividend` | Free |
| 月營收 | `TaiwanStockMonthRevenue` | Free |
| 市值 | `TaiwanStockMarketValue` | Backer |
| 台指期日K | `TaiwanFuturesDaily` | Free |
| 選擇權日K | `TaiwanOptionDaily` | Free |
| 期貨法人 | `TaiwanFuturesInstitutionalInvestors` | Free |
| 台積電即時 | `taiwan_stock_tick_snapshot` | Sponsor |
| 匯率 | `TaiwanExchangeRate` | Free（推測）|
| 黃金 | `GoldPrice` | — |
| 原油 | `CrudeOilPrices` | — |
| 央行利率 | `InterestRate` | — |
| CNN 恐貪指數 | `CnnFearGreedIndex` | — |
| 景氣燈號 | `TaiwanBusinessIndicator` | Backer |

---

*本文件整理自 https://finmind.github.io/llms-full.txt，FinMind 官方網站：https://finmindtrade.com*
