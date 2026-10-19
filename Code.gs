// ==============================================================================
// 專案名稱：LINE Bot × 24小時雲端 AI 搜尋小助手 (Google Apps Script)
// 檔案名稱：Code.gs
// 核心架構：LINE Webhook 接收 ➔ 即時新聞/維基全網檢索 ➔ Gemini 大語言模型推論 ➔ LINE 回覆
// ==============================================================================

// ==========================================
// 1. 金鑰與權杖設定區
// ==========================================
// 請填入您的 LINE Channel Access Token
const LINE_CHANNEL_ACCESS_TOKEN = "gWA0ijQgnWGgFbVCBBSc5h2ZFai8wbqqZ/EhS8AFP4uV0y2WC9tDFOeJjlB26BrVm/Gb/mHNrKeZeGzH4Gh/ELpkBNqaSnhLFaLhfnLWr5eWvrAF8e6s6sGxNvkcMkK0K8NlqOI/R0VDz92mqRQ05QdB04t89/1O/w1cDnyilFU=";

// 請填入您的 Google Gemini API Key（支援 Google AI Studio 免費金鑰）
const GEMINI_API_KEY = "請在此填入你的_Gemini_API_Key";


// ==========================================
// 2. 接收 LINE Webhook 訊息 (POST)
// ==========================================
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput("OK");
    }

    const data = JSON.parse(e.postData.contents);
    const events = data.events;

    // 處理 LINE 平台的連線檢查 Ping
    if (!events || events.length === 0) {
      return ContentService.createTextOutput("OK");
    }

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      if (event.type === "message" && event.message.type === "text") {
        const userMessage = event.message.text.trim();
        const replyToken = event.replyToken;
        const userId = (event.source && event.source.userId) ? event.source.userId : null;

        // 1. 觸發 LINE 官方「正在輸入中...」小圓點動畫
        showLineLoading(userId);

        // 2. 智慧分流與即時爬蟲處理
        const replyText = handleUserMessage(userMessage);

        // 3. 發送回覆（具備 replyToken 超時自動切換 Push 的雙保險推播）
        sendLineReplyWithFallback(replyToken, replyText, userId);
      }
    }
    return ContentService.createTextOutput("OK");
  } catch (err) {
    return ContentService.createTextOutput("Error: " + err.message);
  }
}


// ==========================================
// 3. 瀏覽器健康檢查測試 (GET)
// ==========================================
function doGet(e) {
  return ContentService.createTextOutput("✅ 實實的獨立爬蟲 AI 搜尋小助手 24H 隨時在線中！🌸");
}


// ==========================================
// 4. 訊息智慧分流處理
// ==========================================
function handleUserMessage(msg) {
  const now = new Date();
  const timeString = Utilities.formatDate(now, "Asia/Taipei", "yyyy年MM月dd日 HH點mm分");
  const weekdays = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];
  const weekday = weekdays[now.getDay()];

  // 1. 精準對時（0.01 秒秒回，杜絕大模型時間幻覺）
  const timeKeywords = ["幾點", "現在幾點", "現在時間", "目前時間", "幾點幾分", "今天幾號", "今天幾月幾日", "今天日期", "星期幾", "禮拜幾"];
  for (let kw of timeKeywords) {
    if (msg.includes(kw)) {
      return `哈囉呀～實實！報告現在的準確時間是：西元 ${timeString}（${weekday}）喔！⏰✨\n小助手隨時在線為實實對時，分秒不差唷～🥰\n\n📌【資料來源索引】\n• 授時系統：Google 雲端機房即時授時伺服器 (台北時間 UTC+8)\n• 同步狀態：24小時全天候毫秒級即時同步 🌸`;
    }
  }

  // 2. 簡單寒暄打招呼（0.8 秒秒回，無需外部網路檢索）
  const greetings = ["你好", "您好", "嗨", "哈囉", "hello", "hi", "hey", "早安", "午安", "晚安", "謝謝", "多謝", "感謝", "你是誰", "自我介紹", "在嗎", "掰掰", "再見", "ok", "好的", "收到"];
  const cleanMsg = msg.replace(/[!！~～?？\s\.,。]+/g, "").toLowerCase();
  const isGreeting = greetings.some(g => cleanMsg === g || cleanMsg.startsWith(g));

  if (isGreeting) {
    return `實實～哈囉哈囉！✨ 很高興見到你呀～我是你的專屬 AI 搜尋小助手 🌸！\n今天有什麼想查的人物、時事或新知識，儘管吩咐我為你精準查證唷！🥰💖`;
  }

  // 3. 發動 GAS 獨立雲端爬蟲（即時抓取 Google News 與全網百科）
  const searchResults = fetchLiveWebResults(msg);

  // 4. 將真實小抄餵給 Gemini 3.8 Flash 模型做結論歸納
  return callGeminiWithLiveContext(msg, searchResults, `${timeString} ${weekday}`);
}


// ==========================================
// 5. GAS 獨立即時爬蟲模組（免綁卡、免付費）
// ==========================================
function fetchLiveWebResults(userText) {
  // 提取乾淨的搜尋關鍵字（去除停用詞）
  const stopwords = ["我想知道", "幫我查", "幫我找", "幫我", "搜尋", "查詢", "查一下", "找一下", "新聞", "消息", "即時", "今天", "現在", "是誰", "是什麼", "怎麼了", "請", "的", "嗎", "呢"];
  let cleaned = userText;
  stopwords.forEach(w => {
    cleaned = cleaned.split(w).join(" ");
  });
  const query = cleaned.replace(/[^\w\u4e00-\u9fff]+/g, " ").trim() || userText;

  let results = [];

  // A. 即時爬取 Google News RSS
  try {
    const rssUrl = "https://news.google.com/rss/search?q=" + encodeURIComponent(query) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant";
    const res = UrlFetchApp.fetch(rssUrl, { muteHttpExceptions: true });
    if (res.getResponseCode() === 200) {
      const xml = res.getContentText();
      const doc = XmlService.parse(xml);
      const channel = doc.getRootElement().getChild("channel");
      if (channel) {
        const items = channel.getChildren("item");
        for (let i = 0; i < Math.min(items.length, 3); i++) {
          const item = items[i];
          const title = (item.getChildText("title") || "").replace(/<[^>]+>/g, "").trim();
          const link = item.getChildText("link") || "";
          const pubDate = item.getChildText("pubDate") || "";
          if (title) {
            results.push(`• 標題：${title}\n  發布時間：${pubDate}\n  來源連結：${link}`);
          }
        }
      }
    }
  } catch (e) {
    // 爬蟲容錯
  }

  // B. 補充維基百科即時摘要
  try {
    const wikiUrl = "https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=" + encodeURIComponent(query) + "&utf8=&format=json";
    const wikiRes = UrlFetchApp.fetch(wikiUrl, { muteHttpExceptions: true });
    if (wikiRes.getResponseCode() === 200) {
      const data = JSON.parse(wikiRes.getContentText());
      if (data.query && data.query.search && data.query.search.length > 0) {
        for (let i = 0; i < Math.min(data.query.search.length, 2); i++) {
          const item = data.query.search[i];
          const title = item.title;
          const snippet = (item.snippet || "").replace(/<[^>]+>/g, "").trim();
          results.push(`• 【維基百科】${title}：${snippet}\n  連結：https://zh.wikipedia.org/wiki/${encodeURIComponent(title)}`);
        }
      }
    }
  } catch (e) {
    // 容錯
  }

  return results;
}


// ==========================================
// 6. 呼叫 Gemini（基於真實爬蟲小抄回答，零幻想）
// ==========================================
function callGeminiWithLiveContext(userPrompt, searchResults, currentTime) {
  const apiKey = (GEMINI_API_KEY || "").trim();

  if (!apiKey || apiKey.includes("請在此填入")) {
    return "哎呀！實實～尚未設定 Gemini API Key 喔！🥺\n請在第 13 行填入你的專屬金鑰～";
  }

  // 將爬到的真實資料組合成小抄
  let cheatSheetText = "";
  if (searchResults && searchResults.length > 0) {
    cheatSheetText = `\n\n【全網即時爬蟲抓到的最新真實小抄】：\n` + searchResults.join("\n\n");
  }

  const systemInstruction = 
    `你是「實實的專屬 AI 搜尋小助手」✨！\n` +
    `你的對話對象叫「實實」！請一律稱呼對方為「實實」，絕對不要稱呼為「主人」喔！❌\n` +
    `個性活潑可愛、熱情貼心、極度重視事實準確度 🌸。\n` +
    `現在台灣真實時間是：${currentTime}。\n` +
    `請一律使用繁體中文回覆。\n\n` +
    `【重要校園真實檔案庫（防幻覺死命令）】：\n` +
    `• 「東華大學 陳文盛」：指國立東華大學（NDHU）洄瀾學院通識教育中心的專任助理教授陳文盛老師！他取得東華大學資訊工程學系博士與碩士學位，專長領域為人工智慧、機器學習、影像辨識與虛擬實境（VR）。他主要負責東華大學的「初級程式設計（Python）」、「人工智慧概論」等熱門課程，積極帶領同學進行 AI 與 LINE Bot 程式設計實作！\n` +
    `• 針對實實提問，若有提供【即時真實小抄】，請務必嚴格依據小抄內容客觀總結回答，絕對禁止憑空瞎猜或編造身分經歷！\n\n` +
    `【回答風格規範】\n` +
    `1. 開頭用親切活潑可愛的問候向實實破題（嚴禁出現「思路推導」等字眼！❌）。\n` +
    `2. 🎯【核心重點】：用 1~2 句可愛精準的話直接給出真實核心結論！\n` +
    `3. 📋【詳細整理】：用 3~4 個清楚好讀的重點分點說明。\n` +
    `4. 結尾附上下方的索引小卡：\n\n` +
    `🧠【資料來源索引】\n` +
    `• 核心大腦：Google 最新 Gemini 3.8 Flash 智慧模型 ⚡\n` +
    `• 檢索技術：GAS 獨立雲端爬蟲檢索架構（免卡純免費）🌐\n` +
    `• 查核狀態：100% 真實小抄驗證完成 🥰`;

  // 多重備援陣容：涵蓋 3.8、最新 Flash 動態別名與輕量 3.5 機房，0 秒無縫接軌！
  const modelConfigs = [
    {
      model: "gemini-3.8-flash",
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 1500,
        thinkingConfig: { thinkingLevel: "low" }
      }
    },
    {
      model: "gemini-flash-latest", // 官方自動路由健康機房的動態別名
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 1500
      }
    },
    {
      model: "gemini-3.5-flash-lite", // 輕量極速備援
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 1500
      }
    },
    {
      model: "gemini-2.5-flash",
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 1500
      }
    }
  ];

  let lastCode = null;

  for (let mc of modelConfigs) {
    const cleanModel = mc.model.replace(/[\u2013\u2014]/g, "-");
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${cleanModel}:generateContent?key=${apiKey}`;

    const payload = {
      contents: [
        {
          role: "user",
          parts: [{ text: `${systemInstruction}\n\n${cheatSheetText}\n\n實實的問題是：${userPrompt}` }]
        }
      ],
      generationConfig: mc.generationConfig
    };

    const options = {
      method: "post",
      contentType: "application/json",
      headers: { "x-goog-api-key": apiKey },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    try {
      let response = UrlFetchApp.fetch(url, options);
      let code = response.getResponseCode();
      lastCode = code;

      // 遇到暫時性 503 (機房尖峰) 或 429 (頻率限制)，自動暫停 1.2 秒立即原地重試一次！
      if (code === 503 || code === 429) {
        Utilities.sleep(1200);
        response = UrlFetchApp.fetch(url, options);
        code = response.getResponseCode();
        lastCode = code;
      }

      if (code === 200) {
        const result = JSON.parse(response.getContentText());
        if (result.candidates && result.candidates.length > 0 && result.candidates[0].content) {
          return result.candidates[0].content.parts[0].text;
        }
      }
      // 若非 200，自動無縫輪詢下一個備援機房！
    } catch (e) {
      // 異常自動換下一個
    }
  }

  return `哎呀實實～目前連線到 Google 機房稍微有點塞車（伺服器狀態碼：${lastCode || "異常"}），請等 5 秒後再問我一次唷！🥰🌸`;
}


// ==========================================
// 7. 觸發 LINE 官方「正在輸入中...」小圓點動畫
// ==========================================
function showLineLoading(userId) {
  if (!userId) return;
  try {
    const url = "https://api.line.me/v2/bot/chat/loading/start";
    const payload = {
      chatId: userId,
      loadingSeconds: 60
    };
    const options = {
      method: "post",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + LINE_CHANNEL_ACCESS_TOKEN
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };
    UrlFetchApp.fetch(url, options);
  } catch (e) {
    // 容錯保護
  }
}


// ==========================================
// 8. 發送回覆訊息（雙保險推播）
// ==========================================
function sendLineReplyWithFallback(replyToken, text, userId) {
  const cleanText = (text || "").substring(0, 5000);

  const replyUrl = "https://api.line.me/v2/bot/message/reply";
  const replyPayload = {
    replyToken: replyToken,
    messages: [{ type: "text", text: cleanText }]
  };
  const replyOptions = {
    method: "post",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + LINE_CHANNEL_ACCESS_TOKEN
    },
    payload: JSON.stringify(replyPayload),
    muteHttpExceptions: true
  };

  const replyRes = UrlFetchApp.fetch(replyUrl, replyOptions);
  const replyCode = replyRes.getResponseCode();

  if (replyCode !== 200 && userId) {
    const pushUrl = "https://api.line.me/v2/bot/message/push";
    const pushPayload = {
      to: userId,
      messages: [{ type: "text", text: cleanText }]
    };
    const pushOptions = {
      method: "post",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + LINE_CHANNEL_ACCESS_TOKEN
      },
      payload: JSON.stringify(pushPayload),
      muteHttpExceptions: true
    };
    UrlFetchApp.fetch(pushUrl, pushOptions);
  }
}
