import re
import requests
import feedparser
from flask import Flask, render_template, request, jsonify

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

NEWS_KEYWORDS = ["新聞", "時事", "頭條", "快訊", "最新消息", "news"]

TOPIC_KEYWORDS = {
    "tech": ["科技", "3c", "ai", "人工智慧", "電腦", "手機", "tech"],
    "world": ["國際", "全球", "世界", "world"],
    "business": ["財經", "經濟", "股市", "商業", "business"],
    "sports": ["體育", "運動", "棒球", "籃球", "sports"],
}


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
    return any(kw in text.lower() for kw in NEWS_KEYWORDS)


def pick_feed(text):
    lower = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return topic
    return "default"


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_news(topic, limit=5):
    feed = feedparser.parse(NEWS_FEEDS.get(topic, NEWS_FEEDS["default"]))
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


def summarize_news(items):
    if not items:
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
    prompt = (
        "以下是我剛剛抓到的最新新聞資料：\n\n"
        f"{news_text}\n\n"
        "請用「親切的 LINE 機器人語氣」，用繁體中文條列出今天的新聞重點，"
        "每則用一行、前面加上 emoji 或數字，最後加上一句溫暖的結語。"
        "不要逐字複製原文，請幫我濃縮成 1~2 句摘要。"
    )
    return ollama_generate(prompt, system)


def chat_reply(user_text):
    system = (
        "你是「新聞小助手」，一個親切的 LINE 聊天機器人。"
        "請一律使用繁體中文回覆，語氣自然、有禮貌、帶點溫度，"
        "回覆請盡量簡短（一兩句話為主），可以適度使用表情符號。"
    )
    return ollama_generate(user_text, system)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"reply": "你好像沒有輸入內容喔～再說一次好嗎？", "type": "chat"})

    try:
        if is_news_query(message):
            topic = pick_feed(message)
            items = fetch_news(topic, limit=5)
            reply = summarize_news(items)
            return jsonify({
                "reply": reply,
                "type": "news",
                "topic": topic,
                "count": len(items),
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
    app.run(host="127.0.0.1", port=5000, debug=True)
