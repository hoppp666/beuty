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

print(f"[{time.strftime('%H:%M:%S')}] Запуск парсера (мульти-источники + анти-реклама)...")

# Зарубежные RSS-ленты
RSS_FEEDS = [
    "https://www.rap-up.com/feed/",
    "https://pagesix.com/feed/",
    "https://people.com/feed/",
    "https://www.allure.com/feed/rss",
    "https://www.fashiongonerogue.com/feed/",
    "https://www.harpersbazaar.com/rss/all.xml/",
    "https://www.reddit.com/r/popculturechat/.rss",
    "https://www.reddit.com/r/Fauxmoi/.rss",
]

# Публичные русскоязычные Telegram-каналы о звездах, моде и бьюти (парсятся через t.me/s/)
TELEGRAM_CHANNELS = [
    "https://t.me/s/SuperRu",
    "https://t.me/s/spletnik2006",
    "https://t.me/s/peopletalkru",
    "https://t.me/s/thevoicemag",
    "https://t.me/s/flacon_magazine",
    "https://t.me/s/elle_russia",
]

# Стоп-слова: политика + реклама / распродажи / черная пятница
STOP_WORDS = [
    # Политика
    "trump", "biden", "harris", "vance", "obama", "senate", "congress",
    "election", "white house", "republican", "democrat", "ukraine",
    "russia", "putin", "zelensky", "israel", "gaza", "palestine", "nato",
    "parliament", "prime minister", "sanctions", "tariff", "pentagon",
    "governor", "mayor", "выборы", "президент", "госдума", "санкции",
    "митинг", "политика", "депутат", "министр",
    # Реклама, скидки, Черная пятница (Black Friday)
    "black friday", "cyber monday", "promo code", "discount", "best deals",
    "shop now", "on sale", "gift guide", "gift ideas", "amazon deals",
    "sephora sale", "ultrasale", "coupon", "affiliate", "sponsored",
    "черная пятница", "чёрная пятница", "скидки", "распродажа", "промокод",
    "купить со скидкой", "выгодные покупки", "подборка товаров", "нативная реклама",
    "erid", "реклама", "розыгрыш", "дарим", "по ссылке в шапке",
]

# Известные лица со статусом иноагента (дополнительная страховка к проверке ИИ)
FOREIGN_AGENTS_STOP = [
    "пугачева", "пугачёва", "галкин", "макаревич", "гребенщиков", "земфира",
    "монеточка", "нойз", "noize mc", "оксимирон", "oxxxymiron", "моргенштерн",
    "morgenshtern", "дудь", "собчак", "ивлеева", "блиновская", "шац", "лазарева",
    "белый", "слепаков", "поперечный", "варламов", "кац", "шульман",
    "быков", "акунин", "улицкая", "смольянинов", "панин", "хаматова",
    "белый", "назаров", "троянова", "вей", "литл биг", "little big", "прусикин",
    "таюрская", "фейс", "face", "фараон", "дремин", "иноагент", "иностранный агент",
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


def has_stop_keywords(text):
    lower_text = text.lower()
    for word in STOP_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lower_text):
            return True, f"stop-word: {word}"
    for agent in FOREIGN_AGENTS_STOP:
        if agent in lower_text:
            return True, f"stop-person: {agent}"
    return False, ""


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

    lang_note = (
        "Исходный текст на русском языке — перепиши его своими словами (рерайт) "
        "для паблика ВК, сохранив все факты и имена, убрав ссылки на первоисточник."
        if is_russian
        else "Переведи и адаптируй исходную статью с английского на живой, "
        "естественный русский язык."
    )

    prompt = (
        "Ты — опытный редактор русскоязычного паблика ВКонтакте о звездах, "
        "шоу-бизнесе, моде, бьюти и светской хронике.\n"
        f"{lang_note}\n\n"
        f"Заголовок: {raw_title}\n"
        f"Текст статьи:\n{full_text[:6000]}\n\n"
        "ВЫПОЛНИ СТРОГУЮ ПРОВЕРКУ И ВЕРНИ ОТВЕТ В ФОРМАТЕ JSON:\n\n"
        "1. ЖЕСТКИЕ ФИЛЬТРЫ (если сработал хотя бы один — верни ТОЛЬКО "
        '{"skip": true, "reason": "причина"}):\n'
        "- ПОЛИТИКА: любые новости о политике, выборах, президентах, министрах, "
        "войнах, санкциях, законах.\n"
        "- РЕКЛАМА И СКИДКИ: Черная пятница (Black Friday), распродажи, скидки, "
        "промокоды, подборки «что купить на Amazon/Sephora/Ozon/WB», обзоры "
        "выгодных покупок, рекламные интеграции.\n"
        "- РОССИЙСКИЕ ПЕРСОНЫ (КРИТИЧЕСКИ ВАЖНО!):\n"
        "  * Если новость про российских звезд/блогеров — пропускай ТОЛЬКО тех, "
        "кто имеет статус иноагента РФ, уехал с громкими политическими скандалами "
        "или вызывает резкий негатив и отторжение у широкой российской аудитории "
        "(например: Пугачева, Галкин, Моргенштерн, Земфира, Макаревич, Ивлеева, "
        "Блиновская, Собчак и т.п.).\n"
        "  * Оставляй новости про популярных и любимых в России артистов, "
        "актеров, спортсменов и моделей с хорошей репутацией (например: "
        "Юра Борисов, Милош Бикович, Полина Гагарина, Сергей Лазарев, Дима Билан, "
        "Аня Тейлор-Джой, Ирина Шейк, Наталья Водянова, Люся Чеботина, Баста, "
        "Zivert, Анна Асти, Светлана Ходченкова, Юлия Пересильд, Александр Петров "
        "и другие позитивно воспринимаемые персоны).\n"
        "  * Зарубежные звезды (Голливуд, мода, рэп-индустрия) — допускаются все, "
        "если новость не про политику и не про скидки.\n\n"
        "2. ТЕКСТ ПОСТА (если статья прошла фильтры):\n"
        "- Пиши простыми, живыми, понятными русскими словами без канцелярита и "
        "машинных оборотов.\n"
        "- Адаптируй интонацию под тему: скандалы и интриги — увлекательно и со "
        "всеми деталями; смерть или болезнь — сдержанно и уважительно; "
        "мода, бьюти-тренды или музыкальные релизы — легко и стильно.\n"
        "- Передай ВСЕ ключевые факты целиком, без обрывов. Объем: 800–1600 "
        "символов, 3–4 абзаца. Без Markdown-разметки (без ** и # в тексте).\n\n"
        "3. ХЕШТЕГИ:\n"
        "- Сгенерируй строго от 10 до 12 релевантных хештегов ИЗ САМОЙ СТАТЬИ "
        "(имена знаменитостей на русском и английском, бренды, фильмы/альбомы, "
        "ключевые события и рубрика) через пробел.\n\n"
        "Формат JSON ответа:\n"
        '{"skip": false, "title": "Заголовок на русском без кавычек", '
        '"body": "Полный связный текст поста на русском с абзацами", '
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
            print(f"  -> Записей в ленте: {len(feed.entries)}")

            for entry in feed.entries[:6]:
                raw_link = entry.get("link", "")
                link = raw_link.split("#")[0].split("?")[0].strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "")

                if not link or link in seen_urls:
                    continue

                is_bad, reason = has_stop_keywords(f"{title} {summary}")
                if is_bad:
                    print(f"  [Фильтр] Пропуск ({reason}): {title[:55]}...")
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


def collect_telegram_candidates(history, seen_urls):
    """Собирает свежие посты из публичных русских Telegram-каналов."""
    candidates = []
    for tg_url in TELEGRAM_CHANNELS:
        print(f"[{time.strftime('%H:%M:%S')}] Чтение Telegram: {tg_url}")
        try:
            resp = requests.get(tg_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            messages = soup.select(".tgme_widget_message_wrap")
            print(f"  -> Найдено постов: {len(messages)}")

            for msg in messages[-6:]:
                msg_div = msg.select_one(".tgme_widget_message")
                if not msg_div or not msg_div.get("data-post"):
                    continue

                post_id = f"https://t.me/{msg_div['data-post']}"
                if post_id in seen_urls:
                    continue

                text_div = msg.select_one(".tgme_widget_message_text")
                if not text_div:
                    continue

                # Убираем рекламные пометки и лишние ссылки
                for a in text_div.find_all("a"):
                    if "t.me/" in a.get("href", "") or "max.ru" in a.get("href", ""):
                        a.decompose()

                clean_text = text_div.get_text("\n", strip=True)
                if len(clean_text) < 280:
                    continue

                is_bad, reason = has_stop_keywords(clean_text)
                if is_bad:
                    print(f"  [Фильтр TG] Пропуск ({reason}): {clean_text[:50]}...")
                    seen_urls.add(post_id)
                    history.append(post_id)
                    continue

                first_line = clean_text.split("\n")[0][:120]
                seen_urls.add(post_id)
                candidates.append({
                    "url": post_id,
                    "title": first_line,
                    "text": clean_text,
                    "is_russian": True,
                })
        except Exception as e:
            print(f"Ошибка чтения Telegram {tg_url}: {e}")
    return candidates


def run():
    history = load_history()
    seen_urls = set(history)

    rss_items = collect_rss_candidates(history, seen_urls)
    tg_items = collect_telegram_candidates(history, seen_urls)

    candidates = rss_items + tg_items
    random.shuffle(candidates)
    save_history(history)

    print(
        f"[{time.strftime('%H:%M:%S')}] Всего кандидатов: {len(candidates)} "
        f"(Зарубежные: {len(rss_items)}, Русские TG: {len(tg_items)})"
    )
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
        print(f"\n--- Проверяем материал: {raw_title[:70]} ({url}) ---")

        full_text = item["text"] if item["text"] else fetch_full_article(url)
        if not full_text or len(full_text) < 250:
            print("Текст слишком короткий или страница недоступна, пропуск.")
            history.append(url)
            save_history(history)
            continue

        is_bad, reason = has_stop_keywords(full_text[:2000])
        if is_bad:
            print(f"Обнаружено стоп-слово в тексте ({reason}), пропуск.")
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
