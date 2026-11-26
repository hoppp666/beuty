import json
import os
import random
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
import feedparser
import requests
import trafilatura

print(f"[{time.strftime('%H:%M:%S')}] Запуск парсера v4 (событийный фильтр + анти-реклама)...")

RSS_FEEDS = [
    "https://www.rap-up.com/feed/",
    "https://pagesix.com/feed/",
    "https://people.com/feed/",
    "https://www.fashiongonerogue.com/feed/",
    "https://www.harpersbazaar.com/rss/all.xml/",
    "https://www.reddit.com/r/popculturechat/.rss",
    "https://www.reddit.com/r/Fauxmoi/.rss",
]

TG_CHANNELS = [
    "https://t.me/s/superru",
    "https://t.me/s/spletnik_ru",
    "https://t.me/s/peopletalkru",
    "https://t.me/s/thevoicemag",
]

POLITICS_STOP_WORDS = [
    "trump", "biden", "harris", "vance", "obama", "senate", "congress",
    "election", "white house", "republican", "democrat", "ukraine",
    "russia", "putin", "zelensky", "israel", "gaza", "palestine", "nato",
    "parliament", "prime minister", "sanctions", "tariff", "pentagon",
    "governor", "mayor", "трамп", "байден", "выборы", "сенат", "конгресс",
    "санкции", "митинг", "депутат", "госдума", "министр", "президент",
    "правительство", "законопроект",
]

ADS_STOP_WORDS = [
    "black friday", "cyber monday", "promo code", "discount", "best deals",
    "gift guide", "shop now", "affiliate", "sponsored", "must-have",
    "on sale", "save up to", "черная пятница", "чёрная пятница", "скидки",
    "распродажа", "промокод", "erid", "реклама", "партнерский", "партнёрский",
    "подборка товаров", "купить со скидкой", "акция", "салон красоты",
    "записаться на", "как выбрать", "твердый гель", "твёрдый гель",
]

FOREIGN_AGENTS_STOP = [
    "пугачева", "пугачёва", "галкин", "макаревич", "гребенщиков", "земфира",
    "оксимирон", "oxxxymiron", "моргенштерн", "morgenshtern", "нойз", "noize mc",
    "монеточка", "дудь", "собчак", "ивлеева", "блиновская", "шац", "лазарева",
    "белый", "панин", "смольянинов", "хаматова", "белый", "литвинова",
    "поперечный", "фейс", "face", "фараон", "kizaru", "кизару", "instasamka",
    "инстасамка", "милохин", "даня милохин", "акунин", "быков", "невзоров",
    "кац", "варламов", "шульман",
]

HISTORY_FILE = "posted.json"
MAX_HISTORY = 400
BATCH_LIMIT = 3

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VK_TOKEN = os.environ.get("VK_TOKEN")
RAW_GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
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


def contains_stop_words(text):
    lower_text = text.lower()
    for word in POLITICS_STOP_WORDS + ADS_STOP_WORDS + FOREIGN_AGENTS_STOP:
        if word in lower_text:
            return word
    return None


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


def process_with_gemini(raw_title, full_text, is_russian=False):
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY не задан!")
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    )

    task_lang = (
        "Перепиши своими словами (рерайт) русскую новость, убрав упоминания "
        "исходного телеграм-канала."
        if is_russian
        else "Переведи и адаптируй исходную статью на английском языке."
    )

    prompt = (
        "Ты — строгий главный редактор развлекательного паблика ВКонтакте о "
        "звездах, шоу-бизнесе, громких скандалах, моде и бьюти.\n"
        f"{task_lang}\n\n"
        f"Заголовок: {raw_title}\n"
        f"Текст материала:\n{full_text[:6000]}\n\n"
        "ВЫПОЛНИ ВСЕ ПРОВЕРКИ И ВЕРНИ ОТВЕТ СТРОГО В ФОРМАТЕ JSON:\n\n"
        "1. ЖЕСТКИЙ ФИЛЬТР (если сработал хоть один пункт — верни ТОЛЬКО "
        '{"skip": true, "reason": "причина"}):\n'
        "- ПОЛИТИКА: выборы, президенты, министры, законы, войны, санкции, "
        "митинги или политические высказывания звезд.\n"
        "- РЕКЛАМА, СКИДКИ И НАТИВНЫЕ СОВЕТЫ: Черная пятница, распродажи, "
        "промокоды, подборки покупок, обзоры баночек, скрытая реклама салонов "
        "или процедур (вроде «как выбрать гель для ногтей», «5 советов по уходу»). "
        "Пропускай материал, если в нем НЕТ живого новостного события (инфоповода)!\n"
        "- НЕГАТИВНЫЕ ПЕРСОНЫ И ИНОАГЕНТЫ (для российских звезд): пропускай "
        "иноагентов, уехавших со скандалами артистов и блогеров с токсичной "
        "репутацией. Оставляй только новости про любимых и уважаемых в России "
        "звезд (Юра Борисов, Полина Гагарина, Сергей Лазарев, Ирина Шейк, "
        "Люся Чеботина, Баста, Zivert, Милош Бикович, Светлана Ходченкова и др.) "
        "или зарубежных знаменитостей.\n\n"
        "2. ТЕКСТ ПОСТА (если материал прошел все фильтры):\n"
        "- Пиши простыми, живыми, естественными русскими словами.\n"
        "- Избегай канцелярита и дословной кальки с английского.\n"
        "- Тон подстраивай под событие: скандалы, ссоры и разводы — живо и с "
        "подробностями; смерть или болезнь звезды — сдержанно и уважительно; "
        "мода, выходы в свет или музыка (Rap-Up и др.) — стильно и легко.\n"
        "- Передай ВСЕ ключевые факты целиком без обрывов на полуслове. "
        "Объем: 800–1600 символов, 3–4 абзаца. Без Markdown-разметки (** или #).\n\n"
        "3. ХЕШТЕГИ:\n"
        "- Сгенерируй строго от 10 до 12 релевантных хештегов ИЗ САМОЙ СТАТЬИ "
        "(имена знаменитостей на русском и английском, бренды, фильмы/треки, "
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
            "https://api.vk.com/method/wall.post", data=post_data, timeout=15
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


def collect_rss_candidates(history, seen_urls):
    candidates = []
    for feed_url in RSS_FEEDS:
        print(f"[{time.strftime('%H:%M:%S')}] Чтение RSS: {feed_url}")
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:5]:
                raw_link = entry.get("link", "")
                link = raw_link.split("#")[0].split("?")[0].strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "")

                if not link or link in seen_urls:
                    continue

                bad_word = contains_stop_words(f"{title} {summary}")
                if bad_word:
                    print(f"  [Стоп-слово '{bad_word}'] Пропуск: {title[:55]}...")
                    seen_urls.add(link)
                    history.append(link)
                    continue

                seen_urls.add(link)
                candidates.append({
                    "url": link,
                    "title": title,
                    "text": None,
                    "is_russian": False,
                })
        except Exception as e:
            print(f"Ошибка чтения RSS {feed_url}: {e}")
    return candidates


def collect_tg_candidates(history, seen_urls):
    candidates = []
    for tg_url in TG_CHANNELS:
        print(f"[{time.strftime('%H:%M:%S')}] Чтение Telegram: {tg_url}")
        try:
            resp = requests.get(tg_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            messages = soup.select(".tgme_widget_message_wrap")[-6:]
            for msg in messages:
                link_el = msg.select_one("a.tgme_widget_message_date")
                text_el = msg.select_one(".tgme_widget_message_text")
                if not link_el or not text_el:
                    continue
                post_url = link_el.get("href", "").strip()
                post_text = text_el.get_text("\n", strip=True)
                if not post_url or post_url in seen_urls or len(post_text) < 180:
                    continue

                bad_word = contains_stop_words(post_text)
                if bad_word:
                    print(f"  [Стоп-слово '{bad_word}'] Пропуск TG-поста...")
                    seen_urls.add(post_url)
                    history.append(post_url)
                    continue

                first_line = post_text.split("\n")[0][:90]
                seen_urls.add(post_url)
                candidates.append({
                    "url": post_url,
                    "title": first_line,
                    "text": post_text,
                    "is_russian": True,
                })
        except Exception as e:
            print(f"Ошибка чтения Telegram {tg_url}: {e}")
    return candidates


def run():
    history = load_history()
    seen_urls = set(history)

    candidates = collect_rss_candidates(history, seen_urls)
    candidates.extend(collect_tg_candidates(history, seen_urls))
    save_history(history)

    random.shuffle(candidates)
    print(f"[{time.strftime('%H:%M:%S')}] Всего кандидатов: {len(candidates)}")
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
        is_russian = item["is_russian"]
        print(f"\n--- Проверяем материал: {raw_title[:65]} ({url}) ---")

        full_text = item["text"] if item["text"] else fetch_full_article(url)
        if not full_text or len(full_text) < 220:
            print("Текст слишком короткий или страница недоступна, пропуск.")
            history.append(url)
            save_history(history)
            continue

        bad_word = contains_stop_words(full_text[:2000])
        if bad_word:
            print(f"Обнаружено стоп-слово '{bad_word}' в тексте, пропуск.")
            history.append(url)
            save_history(history)
            continue

        result = process_with_gemini(raw_title, full_text, is_russian=is_russian)
        if not result:
            print("Gemini не вернул корректный JSON, попробуем в следующий раз.")
            continue

        if result.get("skip"):
            print(
                "ИИ отфильтровал материал "
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
