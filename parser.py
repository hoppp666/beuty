import time

print(
    f"[{time.strftime('%H:%M:%S' )}] Скрипт запущен, импортируем библиотеки..."
)

from datetime import datetime
import json
import os
from bs4 import BeautifulSoup
from google import genai
import requests

print(f"[{time.strftime('%H:%M:%S' )}] Библиотеки успешно импортированы.")

TARGET_URL = "https://anneofcarversville.com/"
BASE_DOMAIN = "https://anneofcarversville.com"
HISTORY_FILE = "posted.json"
MAX_HISTORY = 100

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VK_TOKEN = os.environ.get("VK_TOKEN")
RAW_GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")

print(f"[{time.strftime('%H:%M:%S' )}] Инициализация скрипта...")
print(f"GEMINI_API_KEY найден: {'Да' if GEMINI_API_KEY else 'НЕТ!'}")
print(f"VK_TOKEN найден: {'Да' if VK_TOKEN else 'НЕТ!'}")
print(f"VK_GROUP_ID найден: {RAW_GROUP_ID if RAW_GROUP_ID else 'НЕТ!'}")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


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


def generate_ai_article(article_title, full_context):
  if not client:
    return (
        f"Новая модная съемка: {article_title}.\n\n{full_context[:500]}...\n\n#beauty"
        " #fashion #editorial #vogue"
    )

  prompt = (
      "Ты — главный редактор глянцевого модного и бьюти-издания. Напиши"
      " полноценную, увлекательную и информативную новость-статью на русском"
      " языке объемом 1500–2000 символов для сообщества ВКонтакте.\n\n"
      f"Тема и заголовок съемки: {article_title}\n"
      f"Исходный текст и детали со страницы: {full_context}\n\n"
      "Требования к статье:\n"
      "1. Начни с яркого, цепляющего вступления (лида), которое сразу погружает в"
      " атмосферу съемки (укажи модель, фотографа, издание и настроение"
      " кадров, если они есть в исходном тексте).\n"
      "2. Подробно опиши визуальную концепцию, бьюти-образы (макияж, укладки),"
      " стилистику одежды и ключевые бренды из текста.\n"
      "3. ОБЯЗАТЕЛЬНО добавь 2–3 интересных бэкграунд-факта: о карьере или"
      " достижениях этой модели, об уникальном почерке фотографа, об истории"
      " модного дома или об эстетике самого журнала.\n"
      "4. Пиши живым, профессиональным журнальным языком, без сухого"
      " машинного перевода и канцелярита. Разбей текст на 4–5 логичных абзацев"
      " для удобного чтения.\n"
      "5. НЕ используй Markdown-разметку (никаких звездочек **, решеток # для"
      " заголовков или тире для списков), так как ВКонтакте её не форматирует."
      " Используй только чистый текст.\n"
      "6. В самом конце с новой строки добавь 6–7 релевантных хештегов"
      " (например: #beauty #fashion #editorial #style #vogue #model #photoshoot)."
  )

  # Список моделей по приоритету на случай, если одна из них перегружена или недоступна
  models_to_try = [
      "gemini-3.8-flash",
      "gemini-2.5-pro",
      "gemini-2.5-flash",
      "gemini-2.0-flash",
  ]

  for model_name in models_to_try:
    print(
        f"[{time.strftime('%H:%M:%S' )}] Отправка запроса к Gemini ({model_name})..."
    )
    try:
      response = client.models.generate_content(
          model=model_name,
          contents=prompt,
      )
      if response and response.text:
        print(
            f"[{time.strftime('%H:%M:%S' )}] Статья успешно сгенерирована"
            f" моделью {model_name} (длина: {len(response.text)} симв.)."
        )
        return response.text.strip()
    except Exception as e:
      print(
          f"[{time.strftime('%H:%M:%S' )}] Модель {model_name} не ответила: {e}"
      )
      time.sleep(1)

  print(
      f"[{time.strftime('%H:%M:%S' )}] Все модели AI недоступны, формируем"
      " расширенный текст из исходника."
  )
  return (
      f"Новая фотосессия: {article_title}.\n\n{full_context[:900]}...\n\n#beauty"
      " #fashion #editorial #makeup #style #photoshoot"
  )


def publish_post_to_vk(title, text, source_link):
  if not VK_TOKEN or not RAW_GROUP_ID:
    print("Пропуск публикации: не заданы VK_TOKEN или VK_GROUP_ID.")
    return False

  full_message = f"{title}\n\n{text}\n\n{source_link}"
  future_time = int(time.time()) + 7200

  try:
    print(
        f"[{time.strftime('%H:%M:%S' )}] Отправка отложенного поста в VK"
        " (wall.post)..."
    )
    post_res = requests.post(
        "https://api.vk.com/method/wall.post",
        data={
            "owner_id": -int(RAW_GROUP_ID),
            "from_group": 1,
            "message": full_message,
            "publish_date": future_time,
            "access_token": VK_TOKEN,
            "v": "5.199",
        },
        timeout=15,
    ).json()

    if "error" in post_res:
      print(f"Ошибка сохранения отложенного поста в VK: {post_res['error']}")
      return False

    post_id = post_res["response"]["post_id"]
    print(
        f"[{time.strftime('%H:%M:%S' )}] УСПЕХ! Пост сохранен в отложенные"
        f" записи VK (ID: {post_id})"
    )
    return True

  except Exception as e:
    print(f"[{time.strftime('%H:%M:%S' )}] Исключение при вызове wall.post: {e}")
    return False


def extract_article_title(art_soup, url):
  # Ищем реальный заголовок статьи на Squarespace (игнорируя логотип сайта)
  selectors = [
      "h1.entry-title",
      "article h1",
      ".post-title",
      ".entry-header h1",
      "meta[property='og:title']",
  ]
  for sel in selectors:
    el = art_soup.select_one(sel)
    if el:
      raw_title = (
          el.get("content", "") if el.name == "meta" else el.get_text(strip=True)
      )
      clean_title = raw_title.split("— Anne of Carversville")[0].split("|")[0].strip()
      if clean_title and clean_title.lower() != "anne of carversville":
        return clean_title

  # Если заголовок не найден в тегах, берем его прямо из красивого URL статьи
  slug = url.rstrip("/").split("/")[-1]
  return slug.replace("-", " ").title()


def run():
  history = load_history()
  print(
      f"[{time.strftime('%H:%M:%S' )}] Загружена история, записей в"
      f" posted.json: {len(history)}"
  )

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
  }

  print(f"[{time.strftime('%H:%M:%S' )}] Запрос главной страницы {TARGET_URL}...")
  try:
    response = requests.get(TARGET_URL, headers=headers, timeout=10)
  except Exception as e:
    print(
        f"[{time.strftime('%H:%M:%S' )}] Ошибка соединения с сайтом-источником:"
        f" {e}"
    )
    return

  if response.status_code != 200:
    print(
        f"[{time.strftime('%H:%M:%S' )}] Сайт вернул неожиданный статус:"
        f" {response.status_code}"
    )
    return

  soup = BeautifulSoup(response.text, "html.parser")
  found_links = []
  for a in soup.find_all("a", href=True):
    href = a["href"]
    if (
        "/2026/" in href
        or "/2025/" in href
        or "/post/" in href
        or "/editorial/" in href
    ):
      if not href.startswith("http"):
        href = BASE_DOMAIN + href
      clean_link = href.split("#")[0]
      if (
          clean_link != TARGET_URL
          and clean_link not in found_links
          and clean_link not in history
      ):
        found_links.append(clean_link)

  print(
      f"[{time.strftime('%H:%M:%S' )}] Найдено новых неопубликованных статей:"
      f" {len(found_links)}"
  )

  if not found_links:
    print(f"[{time.strftime('%H:%M:%S' )}] Новых статей для публикации нет.")
    return

  link = found_links[0]
  print(f"[{time.strftime('%H:%M:%S' )}] Выбрана статья для обработки: {link}")

  try:
    art_resp = requests.get(link, headers=headers, timeout=10)
    if art_resp.status_code != 200:
      print(f"Не удалось открыть страницу статьи: {art_resp.status_code}")
      return
    art_soup = BeautifulSoup(art_resp.text, "html.parser")
  except Exception as e:
    print(f"Ошибка загрузки статьи: {e}")
    return

  title = extract_article_title(art_soup, link)
  print(f"[{time.strftime('%H:%M:%S' )}] Реальный заголовок статьи: {title}")

  content_block = art_soup.select_one(
      "article, .entry-content, .post-body, .sqs-block-content"
  ) or art_soup.select_one("body")

  paragraphs = [
      p.get_text(" ", strip=True)
      for p in content_block.find_all("p")
      if len(p.get_text(strip=True)) > 30
  ]
  # Забираем до 3000 символов исходного текста, чтобы AI получил максимум деталей
  full_context = "\n".join(paragraphs)[:3000] if paragraphs else title
  print(
      f"[{time.strftime('%H:%M:%S' )}] Собрано текста со страницы:"
      f" {len(full_context)} символов."
  )

  ai_text = generate_ai_article(article_title=title, full_context=full_context)

  success = publish_post_to_vk(title, ai_text, link)
  if success:
    history.append(link)
    save_history(history)
    print(
        f"[{time.strftime('%H:%M:%S' )}] Ссылка добавлена в историю posted.json."
    )

  print(f"[{time.strftime('%H:%M:%S' )}] Работа скрипта успешно завершена.")


if __name__ == "__main__":
  run()
