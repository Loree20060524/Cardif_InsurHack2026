# Vercel 部署準備

目標是個人電腦關機後，隊友仍能使用平台。現在已備妥 Python 入口與靜態建置，尚未建立線上部署，持久化資料庫與雲端 AI 也尚未接妥；不能把這次調整視為完整功能已上線。

## 已備妥的設定

- `api/index.py` 沿用現有 HTTP API，不會呼叫 `main()`、建立監聽連接埠或預載個人電腦上的模型。
- `vercel.json` 使用 Other／無框架預設、Python 3.13、單一 Python Function，將 `/api/*` 轉交原有 API。Function 時限設為 300 秒，不代表所有資料更新與多批管理摘要已在線上驗證可於時限內完成。
- `python scripts/build_vercel.py` 只把 `index.html` 和允許的 `assets` 複製到 `public`，由 CDN 提供。設定檔、Python 程式、資料快取及開發預覽不會作為靜態網站公開。
- `.vercelignore` 排除本機快取、憑證、測試及暫存檔；`.env.example` 僅供參考，不會自動載入。不要把 API 金鑰寫入前端程式或 Git。
- Vercel 的 `VERCEL=1` 會使工作快取使用 `/tmp/regintel`，避免寫入唯讀的程式目錄；本機的預設路徑與 `python server.py` 用法維持原狀。

Vercel 官方支援既有專案使用 `BaseHTTPRequestHandler` 類別作為 Python Function，並支援將重寫的路徑參數轉為查詢參數。[Python 入口文件](https://vercel.com/docs/functions/runtimes/python/api-directory)、[路徑重寫](https://vercel.com/docs/rewrites)、[Function 限制](https://vercel.com/docs/functions/limitations)

## 上線前仍須完成

### 1. 持久化資料

目前五個 JSON 的讀寫仍使用原有檔案儲存。Vercel 的 `/tmp` 只供暫存，不能保存跨實例、重新部署及重啟的法規歷史或分析結果。設定 `REGINTEL_DATA_DIR` 也不會建立持久化磁碟。[執行環境的檔案限制](https://vercel.com/docs/functions/runtimes)

須增加共用資料庫儲存，例如 Vercel Marketplace 的 PostgreSQL 服務。整合時須一併處理多實例同時更新的合併／鎖定，以及問答索引的版本失效；單純將檔案上傳到雲端物件儲存，不能解決多人同時操作時的資料覆寫。Neon 是可評估的整合選項，但目前沒有建立或連接資料庫。[Vercel Marketplace](https://vercel.com/marketplace/neon)

本機已有的來源、法規版本、歷史事件及 AI 分析不在 GitHub 裡。保留現有成果需另外遷移這五份資料，不能把第一次雲端重新抓取當成歷史資料已遷移。新資料庫接妥後，還須驗證換一個執行實例仍能讀回原資料。

### 2. 雲端 AI

Vercel Function 不會執行目前電腦上的 Ollama。完整問答、重新分析及管理摘要需要獨立的模型服務或雲端模型 API，並保留目前的結構化輸出和引用驗證。

尚未選定模型供應商，也未新增金鑰或使用任何付費 AI。網站的免費託管不代表 AI 推論免費；選定方案後須確認免費額度、模型支援、資料使用條款，以及 300 秒內的實際回應速度。若改用模型 API，還須調整快取識別與本機 Ollama 的顯示文字。

### 3. 實際部署與驗證

部署來源為既有私人 GitHub 專案 `Loree20060524/Cardif_InsurHack2026`，預期連接 `main`，讓之後推送更新自動部署。Vercel 帳號需要具備目標工作區及此私人儲存庫的存取權；不需要將 GitHub 儲存庫改為公開。

目前準備版的 `/api/health` 會保留原有版本與時間資訊，另外回傳 `deployment.ready=false`、待完成的資料保存與 AI 項目。`ok=true` 只表示 Python API 存活。這是準備階段的狀態標記，須於資料庫與模型整合完成後替換成實際檢查，不能當成完整平台已可用。

部署後至少要實際確認頁面／API 路由、來源更新、重啟後資料保存、AI 問答引用、單筆分析及管理摘要，才能提供隊友完整使用的固定網址。

## 本機驗證

2026-10-12：88 項 Python 測試通過，包含既有功能、主機與資料目錄設定、靜態資源打包、重寫路由的 GET／POST 與編碼參數、敏感路徑拒絕及部署狀態。靜態建置成功；這些檢查不等於 Vercel 線上環境、雲端資料庫或模型已驗證。
