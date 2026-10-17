# Juku 的本地 AI 搜尋助手 (LINE Bot + 本地開源大語言模型)

本專案為「本地生成式 AI 應用開發」實作，將本地運行的開源大語言模型（LLM）透過 Flask 後端伺服器與內網穿透工具，完整串接至真實的手機官方 **LINE Bot**，並結合全網即時檢索（RAG）與新聞爬蟲，打造具備資料來源索引與對話記憶的智慧助理。

---

## 🛠️ 一、怎麼裝（環境安裝）

### 1. 安裝本地開源大模型 (Ollama)
本專案使用開源模型管理工具 **Ollama** 在本機（Apple Silicon Mac）離線運行大語言模型：
```bash
# 1. 前往官網下載安裝 Ollama：https://ollama.ai/
# 2. 下載本專案使用的 70 億參數中文強化大模型：
ollama pull qwen2.5:7b
```

### 2. 安裝 Python 虛擬環境與相關套件
進入專案目錄建立虛擬環境並安裝依賴：
```bash
cd line-bot-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

核心套件清單 (`requirements.txt`)：
* `Flask`：Web 伺服器框架與 Webhook 端點
* `line-bot-sdk>=3.0.0`：LINE 官方最新版 Messaging API SDK (v3)
* `requests`：本地 Ollama API 呼叫與 HTTP 請求
* `feedparser`：Google News 即時 RSS 新聞解析
* `duckduckgo-search` / `ddgs`：全網即時搜尋爬蟲工具

### 3. 安裝 Cloudflare Tunnel (內網穿透工具)
用於將本地 Mac 的 `localhost:5001` 對外暴露為安全的公網 HTTPS 網址：
```bash
# macOS (Apple Silicon arm64) 下載指令：
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz | tar -xz -C /usr/local/bin/
```

### 4. 取得 LINE Developers 憑證
1. 登入 [LINE Developers Console](https://developers.line.biz/)。
2. 建立 Provider 與 Messaging API Channel。
3. 取得兩組密鑰並填入 `app.py`：
   * `Channel Secret`
   * `Channel Access Token`

---

## 🚀 二、怎麼跑（啟動與執行步驟）

整個系統由三個部分協同運作：

### 步驟 1：啟動本地 Ollama 模型服務
確保本地 Ollama 正在背景運行（預設監聽 `http://localhost:11434`）：
```bash
ollama serve
```

### 步驟 2：啟動 Python Flask 後端伺服器
開啟第一個終端機視窗：
```bash
cd line-bot-sim
source .venv/bin/activate
python app.py
```
*(伺服器將啟動並監聽 `0.0.0.0:5001`)*

### 步驟 3：啟動外網穿透通道 (Cloudflare Tunnel)
開啟第二個終端機視窗：
```bash
cloudflared tunnel --url http://localhost:5001
```
*(終端機會印出一組公網網址，例如：`https://xxxx.trycloudflare.com`)*

### 步驟 4：設定 LINE Webhook
1. 前往 [LINE Official Account Manager](https://manager.line.biz/) 或 LINE Developers Console。
2. 進入「回應設定」/「Messaging API」。
3. 在 **Webhook 網址** 欄位貼上：`https://xxxx.trycloudflare.com/callback`。
4. 點選 **【儲存】** 並開啟 **「使用 Webhook」**。

👉 **完成！現在只要用手機打開 LINE App，傳送訊息給官方帳號，即可獲得本地 AI 的即時運算回覆！**

---

## ✨ 三、你改了什麼（架構演進與優化特點）

相較於基礎版的單純文字回傳，本專案在實作過程中針對實用性、精準度與使用者體驗進行了六大關鍵升級：

### 1. 模型大腦升級（從 3B 升級為 7B）
* 最初採用輕量級 `qwen2.5:3b`（30 億參數），但發現複雜推理與繁體中文表達較為生硬。
* 考量到本機為 Apple M4 晶片搭配 16GB 統一記憶體，效能優異，故全面升級為 **`qwen2.5:7b`**（70 億參數），語義理解與歸納能力大幅提升。

### 2. 毫秒級精確時鐘注入（杜絕時間幻覺）
* 原生大語言模型沒有內建手錶與即時日期感知，先前常捏造錯誤時間。
* 透過後端在 Python 層對接 Mac 系統真實硬體時鐘，只要使用者詢問「現在幾點」、「今天幾號」、「星期幾」，系統即時秒回精確到秒的時鐘資訊，並標註台北標準時間來源。

### 3. 全網檢索優先策略（Search-First RAG 架構）
* 結合 **Google News RSS**（時事焦點）與 **DuckDuckGo**（全網知識檢索）：
  * 當偵測到使用者詢問實質問題（如天氣、股價、人物、時事、科技趨勢等），後端自動進行即時網路搜尋。
  * 將抓回的最新網頁內容作為參考文本（Context）餵給本地 Qwen 2.5 7B 模型進行分析歸納，徹底解決大模型知識庫過期的痛點。

### 4. 全面強制「資料來源索引（Source Indexing）」
* 使用者提問的所有回答最下方，均主動結構化列出資料依據：
  * **聯網搜尋結果**：標註 `[1] 網頁標題 - 真實超連結`。
  * **新聞整理**：標註 `[1] 新聞標題 - 報導媒體 - 原始新聞網址`。
  * **系統資訊**：標註 Mac 本地硬體即時系統時鐘狀態。
  * **邏輯推論**：標註本地 Qwen 2.5 7B 神經網路推理引擎與 Apple M4 加速標籤。

### 5. 多輪對話上下文記憶（Session Memory）
* 針對 LINE 使用者 ID 建立會話記憶緩衝區（保留最近數輪對話）。
* 支援自然連續追問（例如：「推薦三部科幻電影」➡️「那第二部在講什麼？」），AI 能精準承接上下文脈絡。

### 6. 雙模式介面相容
* 除了正式的手機 LINE App 串接，專案中保留了 `templates/index.html` 網頁版擬真 LINE 介面（支援 RWD 手機版型自適應），方便在無外網連線時進行本地快速調試與展示。
