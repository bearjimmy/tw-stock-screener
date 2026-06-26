# update.ps1 —— Windows Task Scheduler 12 小時排程用的包裝腳本。
#
# 功能：
#   - 自動切到本檔所在目錄（schtasks 排程時工作目錄不一定對）
#   - 把 fetch_and_compute.py 的 stdout/stderr 追加到 data\update.log
#   - log 含時戳，可直接看「上次跑了沒、結果如何」
#   - exit code 透傳：fetch 失敗時排程器會顯示「上一次失敗」
#
# Token 來源（fetch_and_compute.py 內部已實作，優先順序）：
#   1) $env:FINMIND_TOKEN（系統／使用者級永久變數最理想）
#   2) 本目錄下 .finmind_token 檔（單行 token，已加入 .gitignore）
#
# 手動測試：powershell -ExecutionPolicy Bypass -File d:\投資選股網頁\update.ps1
# 排程註冊：見檔尾「Task Scheduler 註冊指令」段落。

$ErrorActionPreference = 'Stop'

# 1) 切到本檔所在目錄（讓 fetch_and_compute.py 找得到 data\）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 2) 確保 data 目錄存在（首次跑時還沒有）
$DataDir = Join-Path $ScriptDir 'data'
if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir | Out-Null }
$LogPath = Join-Path $DataDir 'update.log'

# 3) 寫入開始時戳
$StartTime = Get-Date
Add-Content -Path $LogPath -Encoding utf8 -Value ""
Add-Content -Path $LogPath -Encoding utf8 -Value ("===== [{0:yyyy-MM-dd HH:mm:ss}] update.ps1 開始 =====" -f $StartTime)

# 4) 跑 fetch_and_compute.py；用 cmd.exe 原生 >> redirect，不走 PowerShell pipeline。
#
#    為什麼不用 PowerShell 的 *>&1 | Tee-Object：
#      - 5.1 的 Tee-Object 預設用 Unicode (UTF-16 LE) 寫檔 → 與 Add-Content 寫的 UTF-8 BOM
#        混在一起時，log 用任何編碼讀都會看到一半亂碼。
#      - 對原生程式做 2>&1 / *>&1 時，5.1 會把 stderr 每行包成 ErrorRecord
#        (NativeCommandError) → 與 $ErrorActionPreference='Stop' 衝突，python 即使 exit 0
#        也會被當成失敗、報 exit code 1。
#    解法：交給 cmd.exe 做合併 + 附加；python stdout/stderr 都已 reconfigure 為 UTF-8。
#
#    --days 35：策略只看近期（20 日動能、15 日新高、25 點 sparkline）；35 日綽綽有餘。
#    不用 250：每次排程不必重抓一整年，<1 分鐘完成。要長期歷史時手動跑 `python fetch_and_compute.py`。
#    --refresh-latest 2：強制重抓最新 2 個交易日（含今天 + 前一天），覆蓋盤後修正值。
try {
    $CmdLine = 'python "fetch_and_compute.py" --days 35 --refresh-latest 2 >>"' + $LogPath + '" 2>&1'
    & cmd.exe /c $CmdLine
    $ExitCode = $LASTEXITCODE
} catch {
    Add-Content -Path $LogPath -Encoding utf8 -Value ("Exception: " + $_.Exception.Message)
    $ExitCode = 1
}

$Duration = (Get-Date) - $StartTime
# .NET TimeSpan 自訂格式：「:」是保留字，得用單反斜線跳脫成 `\:`。
# PowerShell 雙引號不會處理 `\`（escape char 是 backtick），所以這裡寫成單反斜線
# .NET 才會收到正確的 `hh\:mm\:ss` 格式串。寫成 `\\` 會變字面雙反斜線、報 FormatError。
$DurStr = "{0:hh\:mm\:ss}" -f $Duration
Add-Content -Path $LogPath -Encoding utf8 -Value ("===== 結束 exit={0}  耗時 {1} =====" -f $ExitCode, $DurStr)
exit $ExitCode


<#  ====================== Task Scheduler 註冊指令 ======================

# 目前已註冊：週一至週五 17:40（台股 13:30 收盤後 ~2 小時，外資進出與法人三大資料齊全的時點）
# 由 Claude 用以下指令註冊：
schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:40 `
    /TN "TaiwanStockUpdate" `
    /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"d:\投資選股網頁\update.ps1\"" `
    /F

# 查詢狀態（看上次／下次執行時間、結果）：
schtasks /Query /TN "TaiwanStockUpdate" /V /FO LIST

# 馬上跑一次（驗證排程可以正確觸發）：
schtasks /Run /TN "TaiwanStockUpdate"

# 移除排程：
schtasks /Delete /TN "TaiwanStockUpdate" /F

# 想改時間？例：改成 18:00 重新註冊（會覆蓋舊的）：
schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:00 `
    /TN "TaiwanStockUpdate" `
    /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"d:\投資選股網頁\update.ps1\"" `
    /F

================================================================================ #>
