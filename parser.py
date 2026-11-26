import os
import re
import json
import time
import random
from datetime import datetime
import requests
import feedparser
import trafilatura
from bs4 import BeautifulSoup

print(f"[{time.strftime('%H:%M:%S')}] Запуск парсера (v3: строгий фильтр нативной рекламы и советов)...")

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
    "superru",
    "spletnikru",
    "peopletalkru",
    "thevoicemag",
]

POLITICS_STOP_WORDS = [
    "trump", "biden", "harris", "vance", "obama", "senate", "congress",
    "election", "white house", "republican", "democrat", "ukraine",
    "russia", "putin", "zelensky", "israel", "gaza", "palestine", "nato",
    "parliament", "prime minister", "sanctions", "tariff", "pentagon",
    "governor", "mayor", "выборы", "президент", "госдума", "депутат",
    "министр", "санкции", "политика", "парламент", "сенат", "конгресс",
    "митинг", "протест", "законопроект",
]

ADS_AND_ADVICE_STOP_WORDS = [
    "black friday", "cyber monday", "promo code", "discount", "best deals",
    "gift guide", "sale", "shop now", "affiliate", "sponsored", "partner",
    "must-have", "best products", "editors' picks",
    "черная пятница", "чёрная пятница", "скидки", "скидка", "распродажа",
    "промокод", "акция", "erid", "реклама", "партнерский", "партнёрский",
    "подборка", "купить со скидкой", "выгодная цена", "каталог",
    "советы косметолога", "как выбрать", "топ средств", "салон красоты",
    "записаться", "онлайн-запись", "уход за ногтями", "наращивание",
]

FOREIGN_AGENTS_AND_TOXIC_STOP = [
    "иноагент", "иностранный агент", "пугачева", "пугачёва", "галкин",
    "моргенштерн", "morgenshtern", "oxxxymiron", "оксимирон", "земфира",
    "литл биг", "little big", "прусикин", "гребенщиков", "макаревич",
    "дудь", "собчак", "ивлеева", "блиновская", "шаман", "shaman",
    "мизулина", "мельниченко", "поперечный", "гудков", "лазарева",
    "смольянинов", "хаматова", "белый", "слепаков", "кац", "варламов",
    "монеточка", "нойз", "noize mc", "фейс", "face", "лобода", "барских",
    "брежнева", "мельникова", "панин", "назаров", "ахеджакова",
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


def contains_stop_words(text, word_list):
    lower_text = text.lower()
    for word in word_list:
        if re.search(rf"\b{re.escape(word)}\b", lower_text):
            return word
    return None


def check_text_filters(text):
    if contains_stop_words(text, POLITICS_STOP_WORDS):
        return "politics"
    if contains_stop_words(text, ADS_AND_ADVICE_STOP_WORDS):
        return "ads_or_advice"
    if contains_stop_words(text, FOREIGN_AGENTS_AND_TOXIC_STOP):
        return "blocked_person"
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


def process_with_gemini(raw_title, full_text, lang="en"):
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY не задан!")
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    )

    source_note = (
        "Исходный текст на АНГЛИЙСКОМ языке — переведи и адаптируй его."
        if lang == "en"
        else "Исходный текст на РУССКОМ языке (из СМИ/Telegram) — сделай живой уникальный рерайт своими словами, убери упоминания других каналов и ссылок."
    )

    prompt = (
        "Ты — строгий главный редактор развлекательного паблика ВКонтакте о "
        "жизни звезд, шоу-бизнесе, светских скандалах, музыке, моде и бьюти.\n"
        f"{source_note}\n\n"
        f"Заголовок: {raw_title}\n"
        f"Текст материала:\n{full_text[:6000]}\n\n"
        "ВЫПОЛНИ ПРОВЕРКИ И ВЕРНИ ОТВЕТ СТРОГО В ФОРМАТЕ JSON:\n\n"
        "1. ЖЕСТКИЙ ФИЛЬТР (ПРОПУСКАТЬ НЕМЕДЛЕННО):\n"
        "- ПОЛИТИКА: выборы, президенты, министры, законы, войны, санкции, "
        "митинги, политические высказывания. Верни: {"skip": true, "reason": "politics"}\n"
        "- ЛЮБАЯ РЕКЛАМА И НАТИВНЫЕ ОБЗОРЫ: скидки, Черная пятница, распродажи, "
        "промокоды, подборки косметики/одежды («лучшие кремы», «что купить»), "
        "а также любые завуалированные рекламные тексты и описания процедур/товаров "
        "без реального инфоповода (например, тексты в стиле «для тех, кто мечтает о "
        "длинных ногтях, существует твердый гель, доверяйте профессионалам...»). "
        "Верни: {"skip": true, "reason": "ads"}\n"
        "- ПОЛЕЗНЫЕ СОВЕТЫ БЕЗ ЗВЕЗД: инструкции («как сделать маникюр», «5 правил "
        "ухода», «чем отличается гель от акрила»), если в новости нет конкретного "
        "события со знаменитостью или модным домом. Верни: {"skip": true, "reason": "advice"}\n"
        "- РОССИЙСКИЕ ПЕРСОНЫ С НЕГАТИВНОЙ РЕПУТАЦИЕЙ: если речь о российских "
        "звездах со статусом иноагента, уехавших со скандалами или вызывающих "
        "сильный негатив у аудитории — пропускай! Пропускай ТОЛЬКО новости про "
        "тех российских артистов, актеров и моделей, к которым в России относятся "
        "тепло и с симпатией (Юра Борисов, Полина Гагарина, Сергей Лазарев, Ирина "
        "Шейк, Zivert, Баста, Люся Чеботина, Милош Бикович и т.п.). "
        "Верни: {"skip": true, "reason": "reputation"}\n\n"
        "2. ТРЕБОВАНИЯ К ПОСТУ (если материал прошел все фильтры и содержит реальное событие):\n"
        "- Пиши простыми, живыми, естественными русскими словами, без канцелярита "
        "и машинного перевода.\n"
        "- Не добавляй от себя рекламных призывов («доверяйте профессионалам», "
        "«наслаждайтесь результатом» и т.п.).\n"
        "- Подстраивай подачу: скандалы и слухи — увлекательно и с деталями; "
        "смерть или болезнь — сдержанно и уважительно; мода, музыка (Rap-Up) и "
        "светская хроника — легко и стильно.\n"
        "- Передай все ключевые факты без обрывов. Объем: 800–1600 символов, "
        "3–4 абзаца. Без Markdown-разметки (** или #).\n\n"
        "3. ХЕШТЕГИ:\n"
        "- Сгенерируй строго от 10 до 12 релевантных хештегов ИЗ САМОЙ СТАТЬИ "
        "(имена звезд на русском и английском, бренды, фильмы/треки, события и "
        "рубрика) через пробел.\n\n"
        "Формат JSON ответа:\n"
        "{"skip": false, "title": "Заголовок на русском без кавычек", "
        ""body": "Полный связный текст поста на русском с абзацами", "
        ""hashtags": "#тег1 #тег2 #тег3 #тег4 #тег5 #тег6 #тег7 #тег8 #тег9 #тег10"}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.55,
        },
    }

    for attempt in range(1, 4):
        try:
            print(
                f"[{time.strftime('%H:%M:%S')}] Проверка и редактура в Gemini "
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

                reason = check_text_filters(f"{title} {summary}")
                if reason:
                    print(f"  [Стоп-фильтр: {reason}] {title[:55]}...")
                    seen_urls.add(link)
                    history.append(link)
                    continue

                seen_urls.add(link)
                candidates.append({"url": link, "title": title, "lang": "en", "text": None})
        except Exception as e:
            print(f"Ошибка чтения RSS {feed_url}: {e}")
    return candidates


def collect_tg_candidates(history, seen_urls):
    candidates = []
    for channel in TG_CHANNELS:
        url = f"https://t.me/s/{channel}"
        print(f"[{time.strftime('%H:%M:%S')}] Чтение Telegram-канала: @{channel}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            messages = soup.select(".tgme_widget_message")
            for msg in messages[-6:]:
                post_id = msg.get("data-post", "")
                if not post_id:
                    continue
                post_url = f"https://t.me/{post_id}"
                if post_url in seen_urls:
                    continue

                text_el = msg.select_one(".tgme_widget_message_text")
                if not text_el:
                    continue
                raw_text = text_el.get_text("\n", strip=True)
                if len(raw_text) < 180:
                    continue

                reason = check_text_filters(raw_text)
                if reason:
                    print(f"  [Стоп-фильтр TG: {reason}] {raw_text[:55]}...")
                    seen_urls.add(post_url)
                    history.append(post_url)
                    continue

                first_line = raw_text.split("\n")[0][:120]
                seen_urls.add(post_url)
                candidates.append({
                    "url": post_url,
                    "title": first_line,
                    "lang": "ru",
                    "text": raw_text,
                })
        except Exception as e:
            print(f"Ошибка чтения TG @{channel}: {e}")
    return candidates


def run():
    history = load_history()
    seen_urls = set(history)

    candidates = collect_rss_candidates(history, seen_urls)
    candidates.extend(collect_tg_candidates(history, seen_urls))
    save_history(history)

    random.shuffle(candidates)
    print(f"[{time.strftime('%H:%M:%S')}] Отобрано кандидатов после первичных фильтров: {len(candidates)}")
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
        lang = item["lang"]
        print(f"\n--- Проверяем материал ({lang.upper()}): {raw_title[:70]} ---")

        full_text = item["text"] if item["text"] else fetch_full_article(url)
        if not full_text or len(full_text) < 200:
            print("Текст слишком короткий или недоступен, пропуск.")
            history.append(url)
            save_history(history)
            continue

        reason = check_text_filters(full_text[:2500])
        if reason:
            print(f"Отсеяно по стоп-словам в тексте ({reason}), пропуск.")
            history.append(url)
            save_history(history)
            continue

        result = process_with_gemini(raw_title, full_text, lang=lang)
        if not result:
            print("Gemini не вернул корректный JSON, попробуем в следующий раз.")
            continue

        if result.get("skip"):
            print(f"ИИ отклонил материал (причина: {result.get('reason', 'не подходит')}).")
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

    print(f"\n[{time.strftime('%H:%M:%S')}] Готово! Поставлено в отложку: {published_count}")


if __name__ == "__main__":
    run()
