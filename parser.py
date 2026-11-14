from datetime import datetime
import json
import os
import time
from bs4 import BeautifulSoup
import requests

print(f"[{time.strftime('%H:%M:%S')}] Скрипт запущен...")

TARGET_URL = "https://anneofcarversville.com/"
BASE_DOMAIN = "https://anneofcarversville.com"
HISTORY_FILE = "posted.json"
MAX_HISTORY = 100

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VK_TOKEN = os.environ.get("VK_TOKEN")
RAW_GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")

print(f"[{time.strftime('%H:%M:%S')}] Инициализация скрипта...")
print(f"GEMINI_API_KEY найден: {'Да' if GEMINI_API_KEY else 'НЕТ!'}")
print(f"VK_TOKEN найден: {'Да' if VK_TOKEN else 'НЕТ!'}")
print(f"VK_GROUP_ID найден: {RAW_GROUP_ID if RAW_GROUP_ID else 'НЕТ!'}")


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


def ask_gemini(prompt):
  if not GEMINI_API_KEY:
    print("GEMINI_API_KEY не задан.")
    return None

  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"

  headers = {"Content-Type": "application/json"}
  payload = {"contents": [{"parts": [{"text": prompt}]}]}

  for attempt in range(1, 4):
    try:
      print(
          f"[{time.strftime('%H:%M:%S')}] Запрос к Gemini (попытка"
          f" {attempt}/3)..."
      )
      response = requests.post(
          url, headers=headers, json=payload, timeout=35
      )
      if response.status_code == 200:
        res_json = response.json()
        candidates = res_json.get("candidates", [])
        if candidates:
          text = (
              candidates[0]
              .get("content", {})
              .get("parts", [{}])[0]
              .get("text", "")
              .strip()
          )
          if text:
            return text
      else:
        print(
            f"[{time.strftime('%H:%M:%S')}] Ошибка API Gemini"
            f" {response.status_code}: {response.text[:150]}"
        )
    except Exception as e:
      print(f"[{time.strftime('%H:%M:%S')}] Исключение сети Gemini: {e}")

    time.sleep(3)

  return None


def generate_russian_title(original_title):
  prompt = (
      "Translate and adapt the following English article title into fluent,"
      " elegant, and catchy Russian suitable for a high-end fashion and beauty"
      " magazine community. Return ONLY the translated title without any"
      f" extra quotes or explanations:\n\n{original_title}"
  )

  translated = ask_gemini(prompt)
  if translated:
    return translated.replace('"', "").replace("'", "")
  return original_title


def generate_gemini_article(article_title, full_context):
  prompt = (
      "⚠️ СТРОГОЕ ПРАВИЛО: Весь текст статьи, описания образов, бэкграунд-факты"
      " и хештеги должны быть НАПИСАНЫ ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ.\n\n"
      "Ты — главный редактор глянцевого модного и бьюти-издания. Напиши"
      " полноценную, увлекательную и информативную новость-статью на русском"
      f" языке объемом 1500–2000 символов по мотивам съемки: '{article_title}'.\n\n"
      f"Исходный текст и детали со страницы: {full_context}\n\n"
      "Требования к статье:\n"
      "1. Начни с яркого, цепляющего вступления, которое сразу погружает в"
      " атмосферу съемки (модель, фотограф, издание и настроение кадров).\n"
      "2. Подробно опиши визуальную концепцию, бьюти-образы (макияж, укладки),"
      " стилистику одежды и ключевые бренды.\n"
      "3. ОБЯЗАТЕЛЬНО добавь 2–3 интересных бэкграунд-факта: о карьере модели,"
      " почерке фотографа или истории журнала.\n"
      "4. Пиши живым журнальным языком, разбей текст на 4–5 логичных абзацев.\n"
      "5. НЕ используй Markdown-разметку (никаких звездочек **, решеток # для"
      " заголовков или тире для списков).\n"
      "6. В самом конце с новой строки добавь 6–7 релевантных хештегов"
      " (например: #beauty #fashion #editorial #стиль #мода #vogue)."
  )

  ai_text = ask_gemini(prompt)
  if ai_text:
    return ai_text

  print("Не удалось получить текст от Gemini, используем резервный вариант.")
  return (
      f"Яркая бьюти-история: {article_title}.\n\n"
      f"{full_context[:800]}...\n\n"
      "#beauty #fashion #editorial #makeup #style #photoshoot"
  )


def publish_post_to_vk_custom(title, text, source_link, publish_time):
  if not VK_TOKEN or not RAW_GROUP_ID:
    print("Пропуск публикации: не заданы VK_TOKEN или VK_GROUP_ID.")
    return False

  full_message = f"{title}\n\n{text}\n\n{source_link}"

  try:
    print(
        f"[{time.strftime('%H:%M:%S')}] Отправка отложенного поста в VK"
        f" (время публикации: {datetime.fromtimestamp(publish_time).strftime('%Y-%m-%d %H:%M')})..."
    )
    post_res = requests.post(
        "https://api.vk.com/method/wall.post",
        data={
            "owner_id": -int(RAW_GROUP_ID),
            "from_group": 1,
            "message": full_message,
            "publish_date": publish_time,
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
        f"[{time.strftime('%H:%M:%S')}] УСПЕХ! Пост сохранен в отложенные"
        f" записи ВК (ID: {post_id})"
    )
    return True

  except Exception as e:
    print(f"[{time.strftime('%H:%M:%S')}] Исключение при вызове wall.post: {e}")
    return False


def extract_article_title(art_soup, url):
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
          el.get("content", "")
          if el.name == "meta"
          else el.get_text(strip=True)
      )
      clean_title = (
          raw_title.split("— Anne of Carversville")[0].split("|")[0].strip()
      )
      if clean_title and clean_title.lower() != "anne of carversville":
        return clean_title

  slug = url.rstrip("/").split("/")[-1]
  return slug.replace("-", " ").title()


def run():
  history = load_history()
  print(
      f"[{time.strftime('%H:%M:%S')}] Загружена история, записей в"
      f" posted.json: {len(history)}"
  )

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
  }

  print(f"[{time.strftime('%H:%M:%S')}] Запрос главной страницы {TARGET_URL}...")
  try
