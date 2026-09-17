# RegIntel v10.5 — 監理行動引擎（Ollama 本機 AI）

這一版在原本的監理資料蒐集、AI 深度分析與管理摘要之外，新增「監理影響鏈」與「改善任務追蹤」。

## 新增能力

```text
監理資訊
  ↓
AI 監理重點解析
  ↓
受影響部門
  ↓
受影響作業流程
  ↓
改善任務
  ↓
未開始 / 進行中 / 已完成
```

### 監理影響鏈

事件詳細頁會把一則監理資訊轉換成四個階段：

1. 監理要求
2. 受影響部門
3. 受影響流程
4. 改善任務

### 改善任務追蹤

AI 會產生結構化任務，包括：

- 任務內容
- 責任部門
- 優先度
- 內部建議完成時程
- 建議原因

任務狀態可切換：

- 未開始
- 進行中
- 已完成

競賽 Demo 版先使用瀏覽器 `localStorage` 保存狀態，因此不需要資料庫即可展示追蹤流程。

> 「內部建議時程」是公司內部改善工作的建議，不代表主管機關法定期限；法定期限仍以官方來源為準。

## AI

預設使用本機 Ollama：

```powershell
ollama pull qwen3:4b
python server.py
```

瀏覽器：

```text
http://127.0.0.1:8082
```

## 架構定位

RegIntel v10.5 不只是金融監理資訊整合網站，而是：

> 將監理變動轉換為企業可執行、可分工、可追蹤的合規行動。

底層仍保留規則式備援；即使 Ollama 暫時不可用，系統仍能產生基本的部門、流程與改善任務結構。

## 程式碼分層

```text
index.html                  頁面模板（只保留 HTML 結構）
assets/css/                 依畫面區域拆分的樣式
assets/js/                  共用狀態、各視圖渲染與啟動事件
server.py                   相容的啟動入口
regintel/config.py          環境與檔案設定
regintel/domain/            純規則、分類與風險分析
regintel/infrastructure/    HTTP、解析、JSON 與 Ollama adapters
regintel/application/       更新流程與 AI use cases
regintel/web.py             HTTP routes 與伺服器啟動
```

啟動方式維持不變：`python server.py`。
