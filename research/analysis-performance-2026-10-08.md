# 分析速度改善紀錄

日期：2026-10-08。模型維持本機 `qwen3:4b`（Q4_K_M），Ollama 0.40.0；模型狀態顯示完整載入 GPU 記憶體。

## 實測結果

以同一筆較長的公開保險裁罰資料，經目前的事件分析函式執行；測試停用分析結果快取，避免把快取命中當作推論加速，且不寫入正式執行資料。

| 情境 | 整體時間 | 模型載入 | 輸入處理 | 生成文字 |
|---|---:|---:|---:|---:|
| 原設定，首次載入模型 | 83.175 秒 | 20.232 秒 | 11.804 秒 | 51.090 秒 |
| 原設定，模型已載入 | 46.804 秒 | 0.023 秒 | 1.090 秒 | 45.336 秒 |
| 關閉 thinking，模型已載入 | 17.672 秒 | 0.023 秒 | 0.986 秒 | 16.476 秒 |

排除首次載入成本後，此案例整體時間縮短約 62%，約為原本速度的 2.65 倍。原設定生成 3,032 個 token；關閉 thinking 後生成 1,086 個 token，回應不再包含 thinking 文字。另一次關閉 thinking 的測試為 17.918 秒。

上述為相同輸入的少量重複測試，後續請求有輸入前綴快取，不代表所有新公告的平均速度。其他抽樣包括法規資訊 9.326 秒、單筆管理摘要 16.240 秒；管理摘要切換至 16K 上下文時包含約 4 秒載入成本。保留原始輸入與上下文設定，未以截短原文或輸出 token 上限取得速度改善。

## 程式調整

- 預設傳送 `think: false`，單筆分析與管理摘要共用設定。可用 `OLLAMA_THINK=true` 開啟 thinking，或 `OLLAMA_THINK=auto` 沿用模型預設。
- 服務啟動後，在背景預載已安裝模型；預載不生成分析文字，不阻塞 HTTP 服務啟動。保留時間由 `OLLAMA_KEEP_ALIVE` 控制，預設仍為 `10m`。預載將載入工作提前，沒有消除首次載入本身的成本。
- 不同 thinking 設定使用不同分析與摘要快取鍵，避免切換設定後混用舊結果。
- 新生成的事件分析包含 `generation_timing`，保存來源讀取、模型載入、輸入處理、生成及整體時間。快取結果中的時間描述原分析生成過程。
- 品質抽查發現既有法規沿革摘要固定寫成「兩部管理規則」，已改用實際法規名稱並補上回歸測試。

本次量測中，較長裁罰資料已有可讀原文，來源處理只有幾毫秒，主要時間位於模型推論。因此未在這輪修改來源快取、縮小上下文或改動併發架構。

## 驗證與限制

已驗證 thinking 關閉後的 JSON 欄位可解析、單筆分析保留既有法規沿革防護、管理摘要保留使用者選取來源。此抽樣未建立整體分析準確率；模型判斷與建議仍可能需要覆核。

原有更新流程測試共用正式歷史快取，已改為每項測試使用獨立暫存檔；前端測試補齊分頁依賴與對應 DOM。36 項 Python 測試與 9 項前端測試全部通過；完整 Python 回歸測試核對正式 JSON 快取沒有任何變更。

Git 工作目錄連結仍失效，本次更新保存在目前資料夾，未提交 Git。重新啟動這個資料夾的 `server.py` 後，新的分析設定與背景預載才會生效。

## 重現方式

```powershell
python scripts/benchmark_analysis.py --event 99877b843ca21a11 --modes default off --output tmp/performance/comparison.json
python scripts/benchmark_analysis.py --event 33263fb4dbed3e6a --modes configured --output tmp/performance/law-check.json
python scripts/benchmark_analysis.py --summary --modes configured --output tmp/performance/summary-check.json
```

腳本只對本機已安裝模型送出推論請求；必要時會讀取公開官方來源。模型預載不會下載未安裝模型。原始量測結果保存在 `tmp/performance/baseline.json`、`warm-comparison.json`、`thinking-off.json`、`law-fast.json` 及 `summary-fast.json`。
