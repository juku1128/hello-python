import re
import time
from datetime import datetime
from collections import defaultdict
import requests
import feedparser
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, abort

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# LINE Messaging API Credentials
LINE_CHANNEL_SECRET = "bf7d81774ae8d0a79712a688cbf21406"
LINE_CHANNEL_ACCESS_TOKEN = "gWA0ijQgnWGgFbVCBBSc5h2ZFai8wbqqZ/EhS8AFP4uV0y2WC9tDFOeJjlB26BrVm/Gb/mHNrKeZeGzH4Gh/ELpkBNqaSnhLFaLhfnLWr5eWvrAF8e6s6sGxNvkcMkK0K8NlqOI/R0VDz92mqRQ05QdB04t89/1O/w1cDnyilFU="

line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_CHANNEL_SECRET)

OLLAMA_GEN_URL = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b"

# 多輪對話記憶（每個用戶記錄最近 6 則訊息，即 3 輪對話）
USER_SESSIONS = defaultdict(list)
MAX_HISTORY_TURNS = 6

NEWS_FEEDS = {
    "tech": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "world": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "business": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "sports": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "default": "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
}

NEWS_TRIGGER_KEYWORDS = ["新聞", "時事", "頭條", "快訊", "消息", "news"]
WEB_SEARCH_KEYWORDS = ["搜尋", "查詢", "找一下", "查", "找"]

TOPIC_KEYWORDS = {
    "tech": ["科技", "3c", "ai", "人工智慧", "電腦", "手機", "tech"],
    "world": ["國際", "全球", "世界", "world"],
    "business": ["財經", "經濟", "股市", "商業", "business"],
    "sports": ["體育", "運動", "棒球", "籃球", "sports"],
}
TOPIC_KEYWORDS_FLAT = {kw.lower() for kws in TOPIC_KEYWORDS.values() for kw in kws}

NEWS_SEARCH_URL = "https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

STOPWORDS = [
    "我想知道", "我想看", "幫我查", "幫我找", "幫我", "幫忙", "搜尋一下", "查一下",
    "搜尋", "查詢", "找一下", "查", "找", "最新", "新聞", "消息", "即時", "今天",
    "現在", "有什麼", "關於", "相關", "報導", "快訊", "頭條", "時事", "我要",
    "給我", "一下", "請", "的", "看", "來", "個", "嗎", "呢", "啊", "喔",
    "news", "最新消息",
]

LAST_NEWS_ITEMS = []

DEEP_TIP = "\n\n💡 想要進一步了解哪一則？請直接輸入編號（例如『2』），我會為您做深度詳細摘要！"


def ollama_generate(prompt, system=None):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7},
    }
    if system:
        payload["system"] = system
    resp = requests.post(OLLAMA_GEN_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def ollama_chat(messages, options=None):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": options or {"temperature": 0.7},
    }
    try:
        resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()
    except Exception:
        last_msg = messages[-1]["content"] if messages else ""
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else None
        return ollama_generate(last_msg, system=system)


def is_simple_greeting(text):
    t = text.strip().lower()
    greetings = {
        "你好", "您好", "嗨", "哈囉", "hello", "hi", "hey",
        "早安", "午安", "晚安", "謝謝", "多謝", "感謝", "感恩",
        "掰掰", "再見", "bye", "ok", "好的", "收到", "自我介紹",
        "你是誰", "你的名字", "介紹自己"
    }
    cleaned = re.sub(r"[!！~～?？\s]+$", "", t)
    return cleaned in greetings


def is_news_query(text):
    return any(kw in text.lower() for kw in NEWS_TRIGGER_KEYWORDS)


def is_web_search_query(text):
    return any(kw in text.lower() for kw in WEB_SEARCH_KEYWORDS)


def pick_feed(text):
    lower = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return topic
    return "default"


def extract_keyword(text):
    cleaned = text
    for word in sorted(STOPWORDS, key=len, reverse=True):
        cleaned = re.sub(re.escape(word), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", cleaned)
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return None
    keyword = " ".join(tokens).strip()
    if not keyword or keyword.lower() in TOPIC_KEYWORDS_FLAT:
        return None
    return keyword


def parse_deep_query(text):
    stripped = (text or "").strip()
    match = re.search(r"第\s*([0-9]+)\s*則", stripped)
    if match:
        return int(match.group(1))
    if re.fullmatch(r"[0-9]+", stripped):
        return int(stripped)
    return None


WEB_QUERY_STOPWORDS = [
    "我想知道", "我想看", "幫我查", "幫我找", "幫我", "幫忙",
    "搜尋一下", "查一下", "找一下", "搜尋", "查詢", "查", "找",
    "一下", "請", "的", "嗎", "呢", "啊", "喔",
]


def extract_web_query(text):
    cleaned = text
    for word in sorted(WEB_QUERY_STOPWORDS, key=len, reverse=True):
        cleaned = re.sub(re.escape(word), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", cleaned)
    tokens = [t for t in cleaned.split() if t]
    return " ".join(tokens).strip()


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def parse_entries(feed, limit=5):
    items = []
    for entry in feed.entries[:limit]:
        items.append({
            "title": entry.get("title", "(無標題)"),
            "summary": strip_html(entry.get("summary", ""))[:200],
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": (entry.get("source", {}) or {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
        })
    return items


def fetch_news(topic, limit=5):
    feed = feedparser.parse(NEWS_FEEDS.get(topic, NEWS_FEEDS["default"]))
    return parse_entries(feed, limit)


def fetch_news_by_keyword(keyword, limit=5):
    url = NEWS_SEARCH_URL.format(encoded_keyword=quote(keyword))
    feed = feedparser.parse(url)
    return parse_entries(feed, limit)


def web_search(query, max_results=5, retries=3):
    for attempt in range(retries):
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, region="tw-tzh", max_results=max_results):
                    results.append({
                        "title": (r.get("title") or "").strip(),
                        "body": (r.get("body") or "").strip(),
                        "href": (r.get("href") or "").strip(),
                    })
            results = [r for r in results if r["title"] or r["body"]]
            if results:
                return results
        except Exception:
            pass
        time.sleep(1)
    return []


def summarize_news(items, keyword=None, user_id="default"):
    if not items:
        if keyword:
            return f"目前在 Google News 上找不到關於【{keyword}】的即時新聞，建議換個關鍵字試試看～"
        return "抱歉，我現在抓不到新聞，請稍後再試一次～"

    lines = []
    for i, item in enumerate(items, 1):
        source_name = f" ({item['source']})" if item.get('source') else ""
        lines.append(f"{i}. 標題：{item['title']}{source_name}\n   摘要：{item['summary']}")
    news_text = "\n".join(lines)

    time_str = get_current_time_str()
    system = (
        "你是「Juku的本地 AI 搜尋助手」，一個親切、高智慧的 LINE 專業資訊小助手。"
        f"現在的真實時間是：{time_str}。"
        "請一律使用繁體中文回覆，語氣輕鬆專業，排版條理清晰好讀。"
    )

    if keyword:
        header = f"為您整理關於【{keyword}】的最新重大焦點："
        prompt = (
            f"以下是剛抓到的最新新聞：\n\n{news_text}\n\n"
            f"請以親切的語氣回覆。第一行請印出「{header}」，"
            "接著條列出焦點重點（每則前面加上 emoji 或序號，用 1~2 句精華摘要），最後加上一句簡短結語。"
        )
    else:
        prompt = (
            f"以下是剛抓到的最新即時頭條：\n\n{news_text}\n\n"
            "請以親切的語氣，條列出今天最重要的新聞重點（每則前面加上 emoji 或序號，用 1~2 句精華摘要），最後加上一句簡短結語。"
        )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]
    reply = ollama_chat(messages)

    # 記錄多輪記憶
    USER_SESSIONS[user_id].append({"role": "user", "content": f"查新聞: {keyword or '即時頭條'}"})
    USER_SESSIONS[user_id].append({"role": "assistant", "content": reply})

    sources_text = "\n".join(
        f"[{i}] {item['title']}" + (f" - {item['source']}" if item.get('source') else "") + f"\n    {item['link']}"
        for i, item in enumerate(items, 1)
    )
    index_block = f"\n\n🔗【資料來源索引】\n{sources_text}"
    return reply + index_block + DEEP_TIP


def deep_analyze(item, index, user_id="default"):
    time_str = get_current_time_str()
    system = (
        "你是「Juku的本地 AI 搜尋助手」，擅長產出結構完整、高含金量的深度時事分析報告。"
        f"現在時間：{time_str}。請一律使用繁體中文，專業深入、條理清晰。"
    )
    prompt = (
        f"請針對以下這則新聞，撰寫一份深度詳細分析報告：\n\n"
        f"標題：{item['title']}\n"
        f"摘要：{item['summary']}\n"
        f"來源：{item.get('source') or '（未提供）'}\n"
        f"發布時間：{item.get('published') or '（未提供）'}\n\n"
        "請務必使用以下三個分段輸出：\n"
        "📌【事件核心】\n"
        "🔍【詳細背景與經過】\n"
        "💡【關鍵影響與展望】\n\n"
        "每個段落請用繁體中文寫 2~4 句，內容具體扎實。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]
    reply = ollama_chat(messages)

    USER_SESSIONS[user_id].append({"role": "user", "content": f"深度分析第 {index} 則"})
    USER_SESSIONS[user_id].append({"role": "assistant", "content": reply})

    index_text = (
        f"\n\n🔗【資料來源索引】\n"
        f"[1] {item['title']} - {item.get('source') or 'Google News'}\n"
        f"    {item.get('link') or '無提供連結'}"
    )
    return f"📖 第 {index} 則深度分析\n\n{reply}{index_text}"


def summarize_web(query, results, user_id="default"):
    if not results:
        return f"抱歉，我在全網搜尋「{query}」時找不到相關資料，換個關鍵字試試看？"

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] 標題：{r['title']}\n    摘要：{r['body']}\n    網址：{r['href']}")
    web_text = "\n\n".join(lines)

    time_str = get_current_time_str()
    system = (
        "你是「Juku的本地 AI 搜尋助手」，一個客觀、專業、講求證據的資訊檢索助手。"
        f"現在的真實時間是：{time_str}。"
        "請一律使用繁體中文，只根據提供的網頁資料客觀回答，禁止憑空捏造。\n"
        "回答格式規範：\n"
        "1. 🎯【核心摘要】：用 1~2 句話直接給出總結結論。\n"
        "2. 📋【重點整理】：用 3~5 個具體重點條列說明，行文簡潔有力。\n"
        "請在回答完重點即可，結尾不用自行重複輸出網址列表。"
    )
    prompt = (
        f"使用者提問：「{query}」\n\n"
        f"以下是全網即時搜尋到的網頁資料：\n\n{web_text}\n\n"
        "請依據上述資料為使用者整理最精華的解答："
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]
    reply = ollama_chat(messages)

    USER_SESSIONS[user_id].append({"role": "user", "content": query})
    USER_SESSIONS[user_id].append({"role": "assistant", "content": reply})

    sources_text = "\n".join(f"[{i}] {r['title']}\n    {r['href']}" for i, r in enumerate(results, 1))
    return f"{reply}\n\n🔗【資料來源索引】\n{sources_text}"


def get_current_time_str():
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    return f"{now.strftime('%Y年%m月%d日')} {weekday} {now.strftime('%H點%M分')}"


def is_time_query(text):
    t = text.lower()
    time_kws = [
        "幾點", "現在幾點", "現在時間", "目前時間", "幾點幾分",
        "今天幾號", "今天幾月幾日", "今天幾月幾號", "今天日期", "現在幾號",
        "星期幾", "禮拜幾", "西元幾年", "現在年份", "今年是哪一年"
    ]
    return any(kw in t for kw in time_kws)


def chat_reply(user_text, user_id="default"):
    time_str = get_current_time_str()
    system = (
        "你是「Juku的本地 AI 搜尋助手」，一個親切、高智慧、條理分明的 LINE 聊天助手。"
        f"現在的精確真實時間是：{time_str}。"
        "請一律使用繁體中文回覆，語氣自然、專業有溫度、條列清晰。"
        "若使用者問起現在的時間、日期、年份或星期幾，請嚴格根據上述真實時間準確回答。"
        "切勿胡亂編造不知情的事實。"
    )

    history = USER_SESSIONS[user_id][-MAX_HISTORY_TURNS:]
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    reply = ollama_chat(messages)

    USER_SESSIONS[user_id].append({"role": "user", "content": user_text})
    USER_SESSIONS[user_id].append({"role": "assistant", "content": reply})
    if len(USER_SESSIONS[user_id]) > MAX_HISTORY_TURNS * 2:
        USER_SESSIONS[user_id] = USER_SESSIONS[user_id][-MAX_HISTORY_TURNS:]

    index_note = (
        "\n\n🧠【資料來源索引】\n"
        "• 知識引擎：Qwen 2.5 7B（本地開源神經網路模型）\n"
        "• 運算硬體：Apple M4 本地加速推理\n"
        "• 引用範疇：本機通用邏輯推理與語義分析"
    )
    return reply + index_note


@app.route("/")
def index():
    return render_template("index.html")


def process_user_message(message, user_id="default"):
    global LAST_NEWS_ITEMS
    message = (message or "").strip()
    if not message:
        return "你好像沒有輸入內容喔～再說一次好嗎？", "chat", {}

    # 1. 優先處理精準時間查詢（秒回真實時間，絕不幻覺）
    if is_time_query(message):
        time_str = get_current_time_str()
        reply = (
            f"報告！現在的準確時間是：西元 {time_str} 喔！⏰\n\n"
            "📌【資料來源索引】\n"
            "• 來源系統：Mac 本地硬體系統時鐘 (台北標準時間 CST / UTC+8)\n"
            "• 對時狀態：毫秒級即時精確同步"
        )
        return reply, "time", {}

    # 2. 深度新聞分析查詢
    deep_index = parse_deep_query(message)
    if deep_index is not None:
        if not LAST_NEWS_ITEMS:
            return "請先查詢新聞主題，再選擇想深入了解的編號喔！", "chat", {}
        if deep_index < 1 or deep_index > len(LAST_NEWS_ITEMS):
            return f"我這邊只有 {len(LAST_NEWS_ITEMS)} 則新聞喔，請輸入 1~{len(LAST_NEWS_ITEMS)} 之間的編號～", "chat", {}
        item = LAST_NEWS_ITEMS[deep_index - 1]
        reply = deep_analyze(item, deep_index, user_id=user_id)
        return reply, "deep", {"index": deep_index}

    # 3. 新聞檢索
    if is_news_query(message):
        keyword = extract_keyword(message)
        if keyword:
            items = fetch_news_by_keyword(keyword, limit=5)
            reply = summarize_news(items, keyword=keyword, user_id=user_id)
            if items:
                LAST_NEWS_ITEMS = items
            return reply, "news", {"keyword": keyword, "count": len(items)}

        topic = pick_feed(message)
        items = fetch_news(topic, limit=5)
        reply = summarize_news(items, user_id=user_id)
        if items:
            LAST_NEWS_ITEMS = items
        return reply, "news", {"topic": topic, "count": len(items)}

    # 4. 全網搜尋優先策略（只要不是簡單寒暄，優先進行網路即時檢索）
    if not is_simple_greeting(message):
        query = extract_web_query(message)
        if not query:
            query = message
        results = web_search(query, max_results=5)
        if results:
            reply = summarize_web(query, results, user_id=user_id)
            return reply, "web", {"query": query, "count": len(results)}

    # 5. 一般日常對話 / 邏輯推論 / 程式碼生成
    reply = chat_reply(message, user_id=user_id)
    return reply, "chat", {}


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    user_id = data.get("user_id", "web_simulator")

    try:
        reply, msg_type, extra = process_user_message(message, user_id=user_id)
        payload = {"reply": reply, "type": msg_type}
        payload.update(extra)
        return jsonify(payload)
    except requests.exceptions.ConnectionError:
        return jsonify({
            "reply": "我連不上本機的 Ollama 服務 😢\n請確認有執行 `ollama serve`，並且已下載 `qwen2.5:7b` 模型。",
            "type": "error",
        })
    except Exception as exc:
        return jsonify({"reply": f"哎呀，我這邊出了點狀況：{exc}", "type": "error"})


# ===== LINE Messaging API Webhook =====
@app.route("/callback", methods=["GET", "POST"])
def callback():
    if request.method == "GET":
        return "✅ LINE Webhook 伺服器正常運作中！此網址為 LINE 官方通訊專用，請直接在手機 LINE App 中傳送訊息測試喔！", 200

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    # 若為 LINE 後台儲存時的測試 Ping 或健康檢查（不帶簽章），直接回應 200 OK
    if not signature:
        return "OK", 200

    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as exc:
        print(f"[Webhook Error] {exc}")
        return "OK", 200

    return "OK"


@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_line_message(event):
    user_id = getattr(getattr(event, "source", None), "user_id", "line_user")
    user_text = event.message.text
    try:
        reply_text, _, _ = process_user_message(user_text, user_id=user_id)
    except requests.exceptions.ConnectionError:
        reply_text = "抱歉，我連不上本機的 Ollama 服務 😢 請確認本機有開啟 Ollama。"
    except Exception as exc:
        reply_text = f"抱歉，處理您的訊息時發生狀況：{exc}"

    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text[:5000])],
            )
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
