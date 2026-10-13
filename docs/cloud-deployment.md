# 雲端部署準備

目前選擇以 Vercel 為部署方向，相關入口、建置設定及尚未完成項目見 [Vercel 部署準備](vercel-deployment.md)。以下保留一般 Python 主機與 Docker 的設定說明；Vercel 不會執行 `python server.py` 或掛載此處所述的持久化磁碟。

目標是讓個人電腦關機後，隊友仍可透過固定網址使用平台。雲端必須同時提供 Python 後端、獨立的 AI 運算及資料保存。此文件先記錄已完成的執行環境設定；建立實際主機、選擇付費方案及接上 AI 仍須依使用需求完成，不能將本機網址當成已部署網址。

## 主機與資料

| 環境變數 | 本機預設 | 雲端用途 |
| --- | --- | --- |
| `REGINTEL_HOST` | `127.0.0.1` | 設為 `0.0.0.0`，讓雲端反向代理連到後端 |
| `PORT` | `8082` | 沿用雲端主機提供的連接埠 |
| `REGINTEL_DATA_DIR` | 專案目錄 | 設為持久化磁碟的掛載目錄，例如 `/app/data` |

五個 JSON 檔案（來源資料、事件清單、AI 快取、歷史資訊及法規版本）會放在同一資料目錄。程式和資料分開保存；雲端只會保留真正掛載於持久化磁碟下的資料，設定一個目錄名稱並不會自動建立雲端磁碟。

現有本機快取不會自動上傳；新主機首次啟動時會從官方來源建立資料。若需要保留現有法規歷史與分析結果，應另外將這五個檔案複製到雲端資料磁碟，不能只依賴 GitHub 部署。

本專案使用單一 Python 程序與檔案鎖，初期應部署單一實例。多實例共用 JSON 檔案前，須先將資料保存改為支援跨程序同步的儲存方式。

## 執行方式

原生 Python 主機的建置命令為 `pip install -r requirements.txt`，啟動命令為 `python server.py`；健康檢查為 `GET /api/health`。健康檢查代表網頁後端存活，不代表 AI 已完成連線或模型已可用。

已提供 Dockerfile，映像僅包含程式與靜態資源，不包含本機快取、憑證或暫存資料。Docker 部署仍需另外設定持久化磁碟與 AI；映像本身不會下載或執行 Ollama 模型。

`.env.example` 僅列出設定範例。程式讀取的是執行環境變數，不會自動載入 `.env`。

## AI

本機預設為 `qwen3:4b` 與 Ollama 的結構化輸出。Vercel 部署預設直接呼叫 Gemini API 的 `gemini-3.8-flash`；其他雲端主機可明確設定 `REGINTEL_AI_PROVIDER=gemini` 並提供伺服器端 `GEMINI_API_KEY`。使用者選擇不需綁卡的方案，須在 Google AI Studio 使用未啟用 Billing 的 Free Tier 專案，免費用量有上限。雲端的 `127.0.0.1:11434` 指向雲端主機本身，不會連到個人電腦。金鑰設定與實測流程見 [Vercel 部署文件](vercel-deployment.md)。

Ollama Cloud 目前不支援本專案使用的結構化輸出，不能只更換網址就假定所有 AI 功能正常。[Ollama 官方說明](https://docs.ollama.com/capabilities/structured-outputs)

## Render 方案差異

2026-10-12 查核：免費 Web Service 閒置 15 分鐘後會休眠，下一次開啟約需一分鐘，而且不能掛載持久化磁碟。若要保存法規歷史並避免每次休眠後重新抓取，需使用可保存資料的方案。[免費方案限制](https://render.com/docs/free)

Render 目前最小付費主機為每月 US$7，持久化磁碟為每 GB 每月 US$0.25；這是網頁後端的費用，AI 運算、超額流量或其他資源另計。512 MB 主機不能直接承載目前的 4B Ollama 模型。[官方價格](https://render.com/pricing)、[持久化磁碟](https://render.com/docs/disks)

完成帳號連接與方案選擇後，再建立實際服務、設定 AI 與資料磁碟、驗證線上功能並取得固定網址。之後可連接 GitHub 的 `main` 分支，自動部署新的提交。
