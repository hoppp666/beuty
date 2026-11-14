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

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
VK_TOKEN = os.environ.get("VK_TOKEN")
RAW_GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")

print(f"[{time.strftime('%H:%M:%S')}] Инициализация скрипта...")
print(
    f"OPENROUTER_API_KEY найден: {'Да' if OPENROUTER_API_KEY else 'НЕТ!'}"
)
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


def ask_openrouter(prompt, system_prompt):
  if not OPENROUTER_API_KEY:
    print("OPENROUTER_API_KEY не задан.")
    return None

  headers = {
      "Authorization": f"Bearer {OPENROUTER_API_KEY}",
      "Content-Type": "application/json",
      "HTTP-Referer": "https://github.com/vk-beauty-autopost",
      "X-Title": "VK Beauty Editorial Bot",
  }

  free_models = [
      "meta-llama/llama-3.3-70b-instruct:free",
      "qwen/qwen-2.5-72b-instruct:free",
      "google/gemma-2-27b-it:free",
  ]

  for model_name in free_models:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }

    for attempt in range(1, 3):
      try:
        print(
            f"[{time.strftime('%H:%M:%S')}] Запрос к OpenRouter ({model_name},"
            f" попытка {attempt}/2)..."
        )
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=35,
        )
        if response.status_code == 200:
          res_json = response.json()
          if "choices" in res_json and len(res_json["choices"]) > 0:
            result_text = res_json["choices"][0]["message"]["content"].strip()
            return result_text
        else:
          print(
              f"[{time.strftime('%H:%M:%S')}] Ошибка API"
              f" {response.status_code}: {response.text[:150]}"
          )
      except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Исключение сети: {e}")

      time.sleep(2)

  return None


def generate_russian_title(original_title):
  system_prompt = (
      "You are a professional fashion journalist. Translate the given English"
      " article title into fluent, elegant, and catchy Russian suitable for a"
      " high-end fashion magazine community. Return ONLY the translated title"
      " without any extra quotes or text."
  )
  prompt = f"Translate and adapt this title into Russian: {original_title}"

  translated = ask_openrouter(prompt, system_prompt)
  if translated:
    return translated.replace('"', "").replace("'", "")
  return original_title


def generate_openrouter_article(article_title, full_context):
  system_prompt = (
      "You are a professional Russian-language fashion journalist and editor."
      " Always write, translate, and adapt all content strictly in fluent,"
      " engaging, and professional Russian."
  )

  prompt = (
      "⚠️ СТРОГОЕ ПРАВИЛО: Весь текст статьи, описания образов, бэкграунд-факты"
      " и хештеги должны быть НАПИСАНЫ ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ.\n\n"
      "Напиши полноценную, увлекательную и информативную новость-статью на"
      f" русском языке объемом 1500–2000 символов по мотивам съемки: '{article_title}'.\n\n"
      f"Исходный текст и детали со страницы: {full_context}\n\n"
      "Требования к статье:\n"
      "1. Начни с яркого, цепляющего вступления, которое сразу погружает в"
      " атмосферу съемки (модель, фотограф, издание и настроение кадров).\n"
      "2. Подробно опиши визуальную концепцию, бьюти-образы (макияж, укладки),"
      " стилистику одежды и ключевые бренды.\n"
      "3. ОБЯЗАТ
