import re
import time
from datetime import datetime
import requests
import feedparser
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b"

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
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


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


def summarize_news(items, keyword=None):
    if not items:
        if keyword:
            return f"目前在 Google News 上找不到關於【{keyword}】的即時新聞，建議換個關鍵字試試看～"
        return "抱歉，我現在抓不到新聞，請稍後再試一次～"

    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. 標題：{item['title']}\n   摘要：{item['summary']}")
    news_text = "\n".join(lines)

    system = (
        "你是一個親切的 LINE 新聞小助手，名字叫「新聞小助手」。"
        "請一律使用繁體中文，語氣輕鬆、有禮貌，可以適度使用表情符號。"
        "重點是條列清楚、好讀。"
    )

    if keyword:
        header = f"為您整理關於【{keyword}】的最新新聞重點："
        prompt = (
            "以下是我剛剛抓到的相關新聞資料：\n\n"
            f"{news_text}\n\n"
            f"請用「親切的 LINE 機器人語氣」，用繁體中文回覆。"
            f"請務必在第一行原文輸出這句標題：「{header}」，"
            "接著再條列出新聞重點，每則用一行、前面加上 emoji 或數字，最後加上一句溫暖的結語。"
            "不要逐字複製原文，請幫我濃縮成 1~2 句摘要。"
        )
    else:
        prompt = (
            "以下是我剛剛抓到的最新新聞資料：\n\n"
            f"{news_text}\n\n"
            "請用「親切的 LINE 機器人語氣」，用繁體中文條列出今天的新聞重點，"
            "每則用一行、前面加上 emoji 或數字，最後加上一句溫暖的結語。"
            "不要逐字複製原文，請幫我濃縮成 1~2 句摘要。"
        )
    return ollama_generate(prompt, system) + DEEP_TIP


def deep_analyze(item, index):
    system = (
        "你是「新聞小助手」，一個親切的 LINE 聊天機器人，"
        "擅長把新聞整理成深入淺出、有條理的深度分析報告。"
        "請一律使用繁體中文，語氣親切專業，格式清楚好讀。"
    )
    prompt = (
        f"請針對以下這則新聞，撰寫一份深度詳細分析報告：\n\n"
        f"標題：{item['title']}\n"
        f"摘要：{item['summary']}\n"
        f"來源：{item.get('source') or '（未提供）'}\n"
        f"連結：{item.get('link') or '（未提供）'}\n"
        f"發布時間：{item.get('published') or '（未提供）'}\n\n"
        "請務必使用以下四個標題分段輸出，並保留標題文字與 emoji：\n"
        "📌【事件核心】\n"
        "🔍【詳細背景與經過】\n"
        "💡【關鍵影響與展望】\n"
        "🔗【新聞來源與連結】\n\n"
        "每個段落請用繁體中文寫 2~4 句，內容具體、有條理。"
        "在【新聞來源與連結】段落中請附上新聞來源與連結網址。"
    )
    reply = ollama_generate(prompt, system)
    return f"📖 第 {index} 則深度分析\n\n{reply}"


def summarize_web(query, results):
    if not results:
        return f"抱歉，我在全網搜尋「{query}」時找不到相關資料，換個關鍵字試試看？"

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. 標題：{r['title']}\n   摘要：{r['body']}\n   網址：{r['href']}")
    web_text = "\n".join(lines)

    system = (
        "你是「新聞小助手」，一個客觀、中立的資訊檢索小助手。"
        "請一律使用繁體中文，只根據使用者提供的網頁資料作答，"
        "絕對不要憑空捏造或加入資料以外的內容，格式清楚、條列分明。"
    )
    prompt = (
        f"使用者想查詢：「{query}」\n\n"
        f"以下是我在全網搜尋到的網頁資料：\n\n{web_text}\n\n"
        "請扮演客觀的資訊檢索小助手，用繁體中文條列出查詢對象的重點資訊。"
        "請先用一句話做總結，接著用 3~6 個重點條列說明。"
        "只根據上述資料回答，若資料不足請誠實說明，不要臆測。"
        "重點說明完即可，不需要自行列出網址或來源清單。"
    )
    reply = ollama_generate(prompt, system)
    sources = "\n".join(f"{i}. {r['title']}\n   {r['href']}" for i, r in enumerate(results, 1))
    return f"{reply}\n\n【參考網頁來源】\n{sources}"


def chat_reply(user_text):
    now_str = datetime.now().strftime("%Y年%m月%d日")
    system = (
        "你是「新聞小助手」，一個親切的 LINE 聊天機器人。"
        f"今天是西元 {now_str}。"
        "請一律使用繁體中文回覆，語氣自然、有禮貌、帶點溫度，"
        "若使用者問起現在的年份、日期、時間或今天幾號，請根據上述今天的真實日期準確回答。"
        "回覆請盡量簡短（一兩句話為主），可以適度使用表情符號。"
    )
    return ollama_generate(user_text, system)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    global LAST_NEWS_ITEMS

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"reply": "你好像沒有輸入內容喔～再說一次好嗎？", "type": "chat"})

    try:
        deep_index = parse_deep_query(message)
        if deep_index is not None:
            if not LAST_NEWS_ITEMS:
                return jsonify({
                    "reply": "請先查詢新聞主題，再選擇想深入了解的編號喔！",
                    "type": "chat",
                })
            if deep_index < 1 or deep_index > len(LAST_NEWS_ITEMS):
                return jsonify({
                    "reply": f"我這邊只有 {len(LAST_NEWS_ITEMS)} 則新聞喔，請輸入 1~{len(LAST_NEWS_ITEMS)} 之間的編號～",
                    "type": "chat",
                })
            item = LAST_NEWS_ITEMS[deep_index - 1]
            reply = deep_analyze(item, deep_index)
            return jsonify({"reply": reply, "type": "deep", "index": deep_index})

        if is_news_query(message):
            keyword = extract_keyword(message)
            if keyword:
                items = fetch_news_by_keyword(keyword, limit=5)
                reply = summarize_news(items, keyword=keyword)
                if items:
                    LAST_NEWS_ITEMS = items
                return jsonify({
                    "reply": reply,
                    "type": "news",
                    "keyword": keyword,
                    "count": len(items),
                })

            topic = pick_feed(message)
            items = fetch_news(topic, limit=5)
            reply = summarize_news(items)
            if items:
                LAST_NEWS_ITEMS = items
            return jsonify({
                "reply": reply,
                "type": "news",
                "topic": topic,
                "count": len(items),
            })

        if is_web_search_query(message):
            query = extract_web_query(message)
            if not query:
                return jsonify({
                    "reply": "你想搜尋什麼呢？請提供更明確的關鍵字，我再幫你查查看～",
                    "type": "chat",
                })
            results = web_search(query, max_results=5)
            reply = summarize_web(query, results)
            return jsonify({
                "reply": reply,
                "type": "web",
                "query": query,
                "count": len(results),
            })

        reply = chat_reply(message)
        return jsonify({"reply": reply, "type": "chat"})

    except requests.exceptions.ConnectionError:
        return jsonify({
            "reply": "我連不上本機的 Ollama 服務 😢\n請確認有執行 `ollama serve`，並且已下載 `qwen2.5:3b` 模型。",
            "type": "error",
        })
    except Exception as exc:
        return jsonify({"reply": f"哎呀，我這邊出了點狀況：{exc}", "type": "error"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
