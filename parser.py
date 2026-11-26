from datetime import datetime
import json
import os
import random
import re
import time
from bs4 import BeautifulSoup
import feedparser
import requests
import trafilatura

print(f"[{time.strftime('%H:%M:%S')}] Запуск парсера (текстовый режим)...")

RSS_FEEDS = [
    "https://rap-up.com",
    "https://pagesix.com",
    "https://people.com",
    "https://allure.com",
    "https://fashiongonerogue.com",
    "https://harpersbazaar.com",
]

POLITICS_STOP_WORDS = [
    "trump", "biden", "harris", "vance", "obama", "senate", "congress",
    "election", "white house", "republican", "democrat", "ukraine",
    "russia", "putin", "zelensky", "israel", "gaza", "palestine", "nato",
    "parliament", "prime minister", "sanctions", "tariff", "pentagon",
    "governor", "mayor",
]

HISTORY_FILE = "posted.json"
MAX_HISTORY = 300
BATCH_LIMIT = 3

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VK_TOKEN = os.environ.get("VK_TOKEN")
RAW_GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)


def is_obviously_politics(text):
    lower_text = text.lower()
    for word in POLITICS_STOP_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lower_text):
            return True
    return False


def fetch_full_article(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        html = resp.text
        full_text = trafilatura.extract(
            html, include_comments=False, include_tables=False, no_fallback=False
        )

        if not full_text:
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 40
            ]
            full_text = "\n\n".join(paragraphs)

        return full_text
    except Exception as e:
        print(f"Ошибка при скачивании страницы {url}: {e}")
        return None


def process_with_gemini(raw_title, full_text):
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY не задан!")
        return None

    url = (
        "https://googleapis.com"
        f"gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    )

    prompt = (
        "Ты — опытный редактор русскоязычного паблика ВКонтакте о звездах, "
        "шоу-бизнесе, скандалах, моде и бьюти.\n"
        "Проанализируй исходную статью на английском языке.\n\n"
        f"Заголовок: {raw_title}\n"
        f"Текст статьи:\n{full_text[:6000]}\n\n"
        "ВЫПОЛНИ ЗАДАЧИ И ВЕРНИ ОТВЕТ СТРОГО В ФОРМАТЕ JSON:\n\n"
        "1. ФИЛЬТР ПОЛИТИКИ:\n"
        "Если статья касается политики, выборов, президентов, министров, "
        "законов, войн, санкций, митингов или политических скандалов — верни "
        'ТОЛЬКО: {"skip": true, "reason": "politics"}\n'
        "Даже если в статье упоминается певица или актер, но суть новости "
        "про политику — пропускай!\n\n"
        "2. ПЕРЕВОД И АДАПТАЦИЯ (если статья подходит):\n"
        "- Пиши простыми, живыми, естественными русскими словами, как пишут "
        "в популярных развлекательных и лайфстайл-медиа.\n"
        "- Избегай канцелярита и машинного перевода с английского.\n"
        "- Адаптируй тон под суть новости: скандалы и слухи — живо и с "
        "подробностями; смерть или болезнь — сдержанно и уважительно; "
        "мода, бьюти или музыка (Rap-Up и др.) — стильно и легко.\n"
        "- Передай ВСЕ ключевые факты целиком без обрывов. Объем: 800–1600 "
        "символов, 3–4 логичных абзаца. Без Markdown-разметки.\n\n"
        "3. ХЕШТЕГИ:\n"
        "- Сгенерируй строго от 10 до 12 релевантных хештегов ИЗ САМОЙ СТАТЬИ "
        "(имена звезд на русском и английском, бренды, альбомы/фильмы, "
        "ключевые события и рубрика) через пробел.\n\n"
        "Формат JSON ответа:\n"
        '{"skip": false, "title": "Заголовок на русском без кавычек", '
        '"body": "Полный текст поста на русском с абзацами", '
        '"hashtags": "#тег1 #тег2 #тег3 #тег4 #тег5 #тег6 #тег7 #тег8 #тег9 #тег10"}'
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.65,
        },
    }

    for attempt in range(1, 4):
        try:
            print(
                f"[{time.strftime('%H:%M:%S')}] Обработка в Gemini "
                f"(попытка {attempt}/3)..."
            )
            resp = requests.post(url, json=payload, timeout=40)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_out = parts[0].get("text", "").strip()
                        raw_out = re.sub(r"^```json\s*|\s*```$", "", raw_out).strip()
                        return json.loads(raw_out)
            else:
                print(f"Ошибка Gemini API {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"Сбой при обработке ответа Gemini: {e}")
        time.sleep(3)

    return None


def publish_to_vk(title, body, hashtags, publish_time):
    if not VK_TOKEN or not RAW_GROUP_ID:
        print("Пропуск публикации: нет VK_TOKEN или VK_GROUP_ID.")
        return False

    full_message = f"{title}\n\n{body}\n\n{hashtags}"

    if len(full_message) > 3900:
        trimmed_body = body[:3400].rsplit(".", 1)[0]
        full_message = f"{title}\n\n{trimmed_body}.\n\n{hashtags}"

    post_data = {
        "owner_id": -int(RAW_GROUP_ID),
        "from_group": 1,
        "message": full_message,
        "publish_date": publish_time,
        "access_token": VK_TOKEN,
        "v": "5.199",
    }

    try:
        res = requests.post(
            "https://vk.com", data=post_data, timeout=15
        ).json()
        if "error" in res:
            print(f"Ошибка ВК wall.post: {res['error']}")
            return False

        post_id = res["response"]["post_id"]
        dt_str = datetime.fromtimestamp(publish_time).strftime("%Y-%m-%d %H:%M")
        print(
            f"[{time.strftime('%H:%M:%S')}] УСПЕХ! Пост (ID: {post_id}) "
            f"в отложке на {dt_str}"
        )
        return True
    except Exception as e:
        print(f"Исключение при отправке в ВК: {e}")
        return False


def collect_candidates(history):
    candidates = []
    seen_urls = set(history)

    for feed_url in RSS_FEEDS:
        print(f"[{time.strftime('%H:%M:%S')}] Чтение ленты: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                raw_link = entry.get("link", "")
                link = raw_link.split("#")[0].split("?")[0].strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "")

                if not link or link in seen_urls:
                    continue

                if is_obviously_politics(f"{title} {summary}"):
                    print(f"  [Фильтр] Пропуск политики: {title[:60]}...")
                    seen_urls.add(link)
                    history.append(link)
                    continue

                seen_urls.add(link)
                candidates.append({"url": link, "title": title})
        except Exception as e:
            print(f"Ошибка чтения RSS {feed_url}: {e}")

    random.shuffle(candidates)
    return candidates


def run():
    history = load_history()
    candidates = collect_candidates(history)
    save_history(history)

    print(f"[{time.strftime('%H:%M:%S')}] Найдено кандидатов: {len(candidates)}")
    if not candidates:
        return

    published_count = 0
    base_delay = 10800
    step_delay = 7200

    for item in candidates:
        if published_count >= BATCH_LIMIT:
            break

        url = item["url"]
        raw_title = item["title"]
        print(f"\n--- Проверяем статью: {raw_title} ({url}) ---")

        full_text = fetch_full_article(url)
        if not full_text or len(full_text) < 250:
            print("Текст слишком короткий или страница недоступна, пропуск.")
            history.append(url)
            save_history(history)
            continue

        if is_obviously_politics(full_text[:1500]):
            print("Обнаружена политика в тексте статьи, пропуск.")
            history.append(url)
            save_history(history)
            continue

        result = process_with_gemini(raw_title, full_text)
        if not result:
            print("Gemini не вернул корректный JSON, попробуем в следующий раз.")
            continue

        if result.get("skip"):
            print(
                "ИИ отфильтровал статью "
                f"(причина: {result.get('reason', 'не подходит')})."
            )
            history.append(url)
            save_history(history)
            continue

        ru_title = result.get("title", "").strip()
        ru_body = result.get("body", "").strip()
        hashtags = result.get("hashtags", "").strip()

        if not ru_title or not ru_body:
            continue

        publish_time = int(time.time()) + base_delay + (published_count * step_delay)
        if publish_to_vk(ru_title, ru_body, hashtags, publish_time):
            published_count += 1
            history.append(url)
            save_history(history)

        time.sleep(3)

    print(f"\n[{time.strftime('%H:%M:%S')}] Готово! В отложке: {published_count}")


if __name__ == "__main__":
    run()
