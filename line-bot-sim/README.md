# AI 搜尋助手 (LINE Bot + 轉接站 + Google Apps Script 雲端架構)

本專案實作具備即時全網檢索（RAG）與資料來源索引的智慧 LINE Bot 助理系統。專案支援兩種架構部署：
1. **本地轉接站架構（`app.py`）**：在 Mac 本地端運行 Flask 轉接站與開源大語言模型（Ollama），結合 DuckDuckGo 與 Google News 即時檢索。
2. **雲端 24H 永不斷線架構（`Code.gs`）**：部署至 Google Apps Script 雲端平台，具備獨立爬蟲、Gemini 3.8 Flash 模型推論與 LINE 雙保險推播機制。

---

## 🛠️ 一、怎麼裝（環境安裝）

### 1. 本地轉接站環境安裝
* **安裝本地開源模型 (Ollama)**：
  ```bash
  # 下載安裝 Ollama：https://ollama.ai/
  # 下載 70 億參數中文強化大模型：
  ollama pull qwen2.5:7b
  ```
* **建立 Python 虛擬環境並安裝套件**：
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
  核心套件：`Flask`, `line-bot-sdk>=3.0.0`, `requests`, `feedparser`, `duckduckgo-search`。

* **安裝內網穿透工具 (Cloudflare Tunnel)**：
  用於將轉接站 `localhost:5001` 穿透為公網 HTTPS 網址：
  ```bash
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz | tar -xz -C /usr/local/bin/
  ```

### 2. 雲端 Google Apps Script 安裝
1. 開啟 [Google Apps Script 編輯器](https://script.google.com/) 並新增專案。
2. 將本專案中的 `Code.gs` 程式碼複製並貼上到編輯器中。
3. 填入你的 `LINE_CHANNEL_ACCESS_TOKEN` 與 `GEMINI_API_KEY`。

---

## 🚀 二、怎麼跑（啟動與執行步驟）

### 模式 A：本地轉接站運行模式（本機執行）
1. **啟動 Ollama 模型服務**：
   ```bash
   ollama serve
   ```
2. **啟動 Python 轉接站伺服器**：
   ```bash
   python app.py
   ```
   *(轉接站啟動於 `0.0.0.0:5001`，當 LINE 傳入題目時，終端機視窗將即時印出題目標籤與時間戳記)*
3. **啟動 Cloudflare 穿透通道**：
   ```bash
   cloudflared tunnel --url http://localhost:5001
   ```
4. **設定 LINE Webhook**：
   至 LINE Developers 後台將 Webhook URL 設定為：`https://<你的穿透網址>.trycloudflare.com/callback`，並開啟 Webhook。

### 模式 B：Google Apps Script 雲端 24 小時服務模式（免開機）
1. 在 Apps Script 編輯器點選 **【部署】 ➡️ 【新增部署作業】**。
2. 種類選擇 **「網頁應用程式 (Web App)」**：
   * 執行身分：**我 (Me)**
   * 存取權限：**所有人 (Anyone)**
3. 複製產生的網頁應用程式網址，填入 LINE Developers 的 Webhook URL 欄位並點選驗證。
4. 手機開啟 LINE 傳送訊息，即由雲端全天候毫秒級秒回！

---

## ✨ 三、你改了什麼（架構演進與優化特點）

本專案相較於原始基礎回傳，進行了六大關鍵升級與技術突破：

### 1. 雙架構自由切換（本地轉接站 `app.py` + 雲端 `Code.gs`）
* 打造了可在本機離線獨佔硬體運行的 Python 轉接站，也實作了免開電腦、24 小時無間斷服務的 Google Apps Script 雲端架構。
* 在本地轉接站中加入即時終端機除錯日誌，題目接收與回覆狀態一目瞭然。

### 2. Search-First 全網即時檢索（RAG 架構）
* 整合 **Google News 即時新聞 RSS** 與 **DuckDuckGo 全網搜尋**。
* 只要偵測到時事、人物、特定名詞檢索，系統先抓取最新真實網頁與發布時間，做成結構化參考小抄（Context）再交由大模型推論總結，徹底杜絕 AI 幻覺。

### 3. 全面強制「資料來源索引（Source Indexing）」
* 所有回答均嚴格附上結構化【資料來源索引】：
  * 搜尋資料：附上標題與真實點擊超連結。
  * 時事新聞：附上報導媒體與發布時間。
  * 對時問答：附上 Google 雲端 / Mac 本地授時伺服器時區來源。

### 4. 模型大腦與推論控溫優化
* 本地端採用 **Qwen 2.5 7B**（70 億參數中文強化模型），雲端採用 Google 最新 **Gemini 3.8 Flash**。
* 針對事實查核將推論溫度（Temperature）微調至 0.2，並針對 LINE 體驗調優，避免冗長輸出截斷或無謂等待。

### 5. 毫秒級精確時鐘注入（杜絕時間幻覺）
* 原生大語言模型沒有手錶感知，容易捏造錯誤年份。
* 系統由後端層對接真實硬體與網路標準時鐘（UTC+8 台北時間），秒回精準至秒的時間與星期，完全杜絕幻覺。

### 6. LINE 體驗雙重升級（輸入中跳動圓點 + Reply/Push 雙保險推播）
* 接收到問題的第一毫秒觸發 LINE 原生「正在輸入中（Loading Animation）」動畫，消除使用者等待焦慮。
* 實作 ReplyToken 超時自動降級切換至 Push Message API 的容錯架構，100% 確保訊息送達不漏接。
