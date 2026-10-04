import datetime
import random

def main():
    name = input("請輸入你的名字: ")
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quotes = [
        "祝你有個美好的一天！",
        "寫程式就像解謎，享受其中的樂趣！",
        "保持好奇心，每天進步一點點！"
    ]
    quote = random.choice(quotes)
    
    print(f"你好，{name}！現在時間是：{current_time}")
    print(f"今日金句：{quote}")

if __name__ == "__main__":
    main()
