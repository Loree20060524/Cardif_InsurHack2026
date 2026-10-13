# Vercel 部署與資料保存

目標是個人電腦關機後，隊友仍能使用平台。正式網址為 https://cardif-insur-hack2026.vercel.app/ ，對應 `loree1/cardif-insur-hack2026` 與 GitHub 的 `main`。網站與 API 已驗證可開啟；Neon Free 資料庫 `regintel-db` 已由使用者建立並連接 Production。五份本機資料已遷移並以新連線逐份核對 SHA-256，正式站已確認讀取 Neon。雲端 AI 改為直接呼叫 Gemini API 的免綁卡方案；金鑰與生成結果仍須於新版部署後驗證。

## 已備妥的設定

- `api/index.py` 沿用現有 HTTP API，不會呼叫 `main()`、建立監聽連接埠或預載個人電腦上的模型。
- `vercel.json` 使用 Other／無框架預設、Python 3.13、單一 Python Function，將 `/api/*` 轉交原有 API。Function 時限設為 300 秒，不代表所有資料更新與多批管理摘要已在線上驗證可於時限內完成。
- `python scripts/build_vercel.py` 只把 `index.html` 和允許的 `assets` 複製到 `public`，由 CDN 提供。設定檔、Python 程式、資料快取及開發預覽不會作為靜態網站公開。
- `.vercelignore` 排除本機快取、憑證、測試及暫存檔；`.env.example` 僅供參考，不會自動載入。不要把 API 金鑰寫入前端程式或 Git。
- 未設定資料庫連線時，Vercel 的 `VERCEL=1` 會使工作快取使用 `/tmp/regintel`。設定 Neon 連線後，五類資料改存 PostgreSQL，本機未設定連線時繼續使用原本 JSON 檔。

Vercel 官方支援既有專案使用 `BaseHTTPRequestHandler` 類別作為 Python Function，並支援將重寫的路徑參數轉為查詢參數。[Python 入口文件](https://vercel.com/docs/functions/runtimes/python/api-directory)、[路徑重寫](https://vercel.com/docs/rewrites)、[Function 限制](https://vercel.com/docs/functions/limitations)

## 資料保存與後續設定

### 1. 持久化資料

`regintel.infrastructure.postgres_store` 以 psycopg 3 與 PostgreSQL JSONB 保存五類文件，名稱沿用原檔名。連線僅在請求需要資料時建立，建置或匯入模組不連線。未設定資料庫時使用原檔案模式；已設定但連線失敗時會回報錯誤，不會當成空歷史或改存暫存檔。[執行環境的檔案限制](https://vercel.com/docs/functions/runtimes)

連線依序辨識 `REGINTEL_DATABASE_URL`、`DATABASE_URL`、`POSTGRES_URL`、`STORAGE_URL`、`STORAGE_DATABASE_URL`、`STORAGE_POSTGRES_URL`、`POSTGRES_URL_NON_POOLING`；亦支援 libpq 的 `PGHOST`／`PGDATABASE`／`PGUSER`／`PGPASSWORD`。優先使用 Neon 的 pooled 連線。讀取與合併更新使用交易級 advisory locks；匯入使用獨立的排他鎖。一般 AI 生成不持有資料庫交易，生成完成後重新讀取最新快取再合併。問答索引以文件 revision 判斷是否需要重建。[Neon Marketplace](https://vercel.com/marketplace/neon)、[PostgreSQL advisory locks](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS)

本機已有的來源、法規版本、歷史事件及 AI 分析不在 GitHub 裡。保留現有成果需另外遷移這五份資料，不能把第一次雲端重新抓取當成歷史資料已遷移。新資料庫接妥後，還須驗證換一個執行實例仍能讀回原資料。

先檢查本機快照，這個指令不連線或寫入資料庫：

```powershell
python scripts/migrate_storage.py --check
```

在本機 `.env.database.local` 填入 `REGINTEL_DATABASE_URL`，連線值留在本機檔案中。正式環境的 Secret 不會由 `vercel env pull` 匯出，不要為了搬移把 Secret 改成可讀的 Config；透過 Neon 的連線設定取得所需連線。這個檔案已由 `.gitignore` 與 `.vercelignore` 排除，僅搬移工具明確以 `--env-file` 載入，`server.py` 不會自動載入。

停止本機來源更新後，在部署新儲存程式前搬移，避免新站先在空資料庫建立不同快照：

```powershell
python -m pip install -r requirements.txt
python scripts/migrate_storage.py --env-file .env.database.local --apply
python scripts/migrate_storage.py --env-file .env.database.local --verify
```

工具須完整讀到五份 JSON 才會寫入；資料庫已有不同內容或只搬了一部分時會停止，沒有覆寫選項。相同快照重跑不改資料；成功後以新連線逐份核對 SHA-256。預設命名空間為 `regintel-v1`，更改 `REGINTEL_STORAGE_NAMESPACE` 會切換到另一份資料，須讓搬移與正式環境使用相同值。資料庫仍未接妥時，勿宣稱已有持久化保存。

### 2. 雲端 AI

Vercel Function 不會執行目前電腦上的 Ollama。完整問答、重新分析及管理摘要需要獨立的模型服務或雲端模型 API，並保留目前的結構化輸出和引用驗證。

三個功能已共用模型介面：單筆分析、使用者選取範圍的管理摘要、附原文引用的監理問答。本機預設 `ollama`；Vercel 預設 `gemini`，模型為 `gemini-3.8-flash`。可明確設定 `REGINTEL_AI_PROVIDER` 與 `REGINTEL_AI_MODEL` 切換，雲端不探測或預載本機 Ollama。原本的引用檢查、規則備援與 Neon 快取保留；不同供應商與模型的快取分開，本機原有快取識別不變。

使用者已選擇不需綁卡的免費方案。2026-10-13 已核對 Google 的 [模型說明](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)、[價格](https://ai.google.dev/gemini-api/docs/pricing)、[帳單規則](https://ai.google.dev/gemini-api/docs/billing) 及 [結構化輸出](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)：Gemini 3.8 Flash 有 Free Tier 並支援 JSON Schema，新帳號可從免費層開始；升級付費須另連接帳單帳戶。免費請求次數與 token 配額依專案實際額度，超過上限會停止生成。免費層內容可能用於改善 Google 產品，適合本平台的公開監理資料，不應傳送公司機密或個資。

設定步驟：

1. 在 [Google AI Studio](https://aistudio.google.com/) 建立專案與 API 金鑰，確認 Billing Tier 為 **Free Tier**，不連接 Billing 帳戶、不升級付費。可為此平台另建一個未啟用帳單的專案，以免沿用已付費專案。
2. 到 Vercel 的 `cardif-insur-hack2026` → **Environment Variables**，新增 `GEMINI_API_KEY`，值為該金鑰，選 **Production** 並儲存。真實金鑰不貼入聊天、不存入 Git、不放在前端。
3. 若曾明確設定 `REGINTEL_AI_PROVIDER` 或 `REGINTEL_AI_MODEL`，分別改為 `gemini` 與 `gemini-3.8-flash`；未設定時使用上述預設值。
4. 儲存後重新部署，檢查 `/api/health` 的 `ai_check`，再實際驗證單筆分析、管理摘要及問答引用。金鑰存在不代表實測成功；健康檢查不會消耗生成配額。

模型請求使用 Google 官方 `generateContent` REST API，目前仍完整支援。金鑰只放 `x-goog-api-key` 標頭，不放在網址。請求以 `generationConfig.responseFormat.text` 傳送 JSON Schema、使用 low 推理深度並不要求推理文字；回覆再經程式驗證，拒絕截斷、封鎖、額外欄位與無效結果。單次輸出預設上限 4096 token、逾時 180 秒，可用 `REGINTEL_AI_MAX_TOKENS`／`REGINTEL_AI_TIMEOUT` 調整。不自動重試生成、不切到其他供應商、不啟用 Billing 或購買額度。[REST 參考](https://ai.google.dev/api/generate-content)、[推理深度](https://ai.google.dev/gemini-api/docs/thinking)

401／402／403／429 等情況回報安全且可操作的訊息，不回傳上游原始訊息、提示詞或金鑰。單筆分析仍可使用規則備援，但明確標示 `ai_used=false`；問答、管理摘要不冒充生成成功。程式無法只憑 API 金鑰判定 Google 專案的帳單層級；不產生費用的前提是使用者所選專案維持 Free Tier。

`vercel_gateway` 介面保留供日後明確選用，未被 Gemini 錯誤當成備援。先前已在線上確認 Vercel OIDC 可讀取，但 Loree 工作區的 Gateway 回傳 `customer_verification_required`；本次改用 Gemini，不要求完成該付款方式驗證。[Gateway 額度規則](https://vercel.com/docs/ai-gateway/pricing)

### 3. 實際部署與驗證

部署來源為既有私人 GitHub 專案 `Loree20060524/Cardif_InsurHack2026`，預期連接 `main`，讓之後推送更新自動部署。Vercel 帳號需要具備目標工作區及此私人儲存庫的存取權；不需要將 GitHub 儲存庫改為公開。

`/api/health` 會實際檢查儲存層：`deployment.storage=postgres` 以及 `storage_check.connected=true` 表示資料庫可讀取，`document_count` 可輔助核對五份文件；失敗則標示 unavailable。`ok=true` 只代表 API 存活。`ai_check` 回報模型的實測結果：僅有驗證值時仍為 unverified；實際生成且通過格式檢查後才為 verified。最近結果併入既有 AI 快取文件，供不同雲端實例讀取，有效期 24 小時；後續模型失敗會改成 unavailable。健康檢查本身不呼叫模型、不消耗推論額度；資料庫與模型均就緒才回報 `ready=true`。這不代表引用語義、所有功能或歷史資料已完整驗證。

部署後至少要實際確認頁面／API 路由、來源更新、重啟後資料保存、AI 問答引用、單筆分析及管理摘要，才能提供隊友完整使用的固定網址。

## 本機驗證

2026-10-12：88 項 Python 測試通過，包含既有功能、主機與資料目錄設定、靜態資源打包、重寫路由的 GET／POST 與編碼參數、敏感路徑拒絕及部署狀態。靜態建置成功；這些檢查不等於 Vercel 線上環境、雲端資料庫或模型已驗證。

2026-10-13：106 項本機測試通過，另以 Neon 實際連線完成 4 項 PostgreSQL 測試，全部通過。五份本機快照的離線檢查、靜態建置及 Neon 資料搬移均通過；搬移後已使用新連線逐份核對 SHA-256。本機原檔保留，搬移快照另存於忽略的 `tmp/neon-migration-20261013-8qu8qf28`。正式站驗證仍須在新版部署後進行。

`tests/test_postgres_integration.py` 另提供真實資料庫測試，只有明確設定 `REGINTEL_TEST_DATABASE_URL` 才執行。測試使用隨機命名空間並僅清理自己的測試資料，驗證新實例讀取、交易失敗回滾、並行合併與 revision 更新。未設定測試連線時會標示 skipped，不可視為資料庫驗證通過。

2026-10-13 雲端 AI 改動：121 項本機測試通過，4 項真實 PostgreSQL 測試本次未重跑；另完成最後錯誤處理、健康狀態與部署設定的 28 項針對性測試。靜態建置成功。上述測試使用模擬模型回覆，不代表雲端模型實測成功。

2026-10-13 Gemini 接線：133 項 Python 測試中 129 項通過、4 項真實 PostgreSQL 測試本次未重跑。涵蓋 Gemini 金鑰隔離、JSON Schema、截斷與封鎖回覆、額度錯誤、模型路徑驗證及不切換到 Gateway；上述為模擬回覆測試，尚不代表 Gemini 線上已可生成。
