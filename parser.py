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


def generate_ai_article(model_name, magazine, description_hint):
  if not client:
    return (
        f"Новая потрясающая фотосессия: {model_name} для {magazine}.\n\n#beauty"
        " #fashion #editorial #vogue"
    )

  prompt = (
      "Напиши живой, увлекательный и легкий пост-статью на русском языке"
      " (примерно 1100-1300 символов) для модного бьюти-сообщества ВКонтакте."
      f" Расскажи про новую фотосессию, где главная звезда — {model_name},"
      f" а съемка вышла в журнале {magazine}."
      f" Контекст/детали из статьи: {description_hint}."
      " Пиши так, будто ты увлеченный фэшн-инсайдер: без сухого канцелярита"
      " и банальных клише, с душой и вкусом."
      " Обязательно органично вплети в текст 1-2 интересных факта (например,"
      " о карьере модели, истории бренда, концепции фотографа или стиле"
      " съемки), чтобы читателю было действительно любопытно."
      " Не используй Markdown-разметку (звездочки ** или решетки для"
      " заголовков), так как ВКонтакте её не форматирует — используй только"
      " чистый текст и абзацы."
      " В самом конце текста обязательно добавь 5-6 актуальных хештегов на"
      " тему моды, бьюти и стиля (например: #beauty #fashion #editorial #style"
      " #vogue)."
  )

  print(
      f"[{time.strftime('%H:%M:%S' )}] Отправка запроса к Gemini API для"
      " генерации текста..."
  )
  try:
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )
    if response and response.text:
      print(
          f"[{time.strftime('%H:%M:%S' )}] Текст успешно сгенерирован"
          " нейросетью."
      )
      return response.text.strip()
  except Exception as e:
    print(
        f"[{time.strftime('%H:%M:%S' )}] Ошибка Gemini API: {e}."
        " Используем запасной текст."
    )

  return (
      f"Яркая бьюти-история: {model_name} в новом выпуске {magazine}. Элегантные"
      " образы, вдохновляющие детали и безупречный стиль.\n\n#beauty #fashion"
      " #editorial #makeup #style"
  )


def publish_post_to_vk(title, text, source_link):
  if not VK_TOKEN or not RAW_GROUP_ID:
    print("Пропуск публикации: не заданы VK_TOKEN или VK_GROUP_ID.")
    return False

  # Формируем сообщение, где ссылка идет отдельной строкой, чтобы ВК сгенерировал превью
  full_message = f"{title}\n\n{text}\n\n{source_link}"
  
  # Отложенная публикация через 2 часа (можно изменить при желании)
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

  print(
      f"[{time.strftime('%H:%M:%S' )}] Главная страница загружена,"
      f" размер ответа: {len(response.text)} символов"
  )

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
    print(
        f"[{time.strftime('%H:%M:%S' )}] Загрузка содержимого выбранной"
        " статьи..."
    )
    art_resp = requests.get(link, headers=headers, timeout=10)
    if art_resp.status_code != 200:
      print(f"Не удалось открыть страницу статьи: {art_resp.status_code}")
      return
    art_soup = BeautifulSoup(art_resp.text, "html.parser")
  except Exception as e:
    print(f"Ошибка загрузки статьи: {e}")
    return

  title_el = art_soup.select_one("h1") or art_soup.select_one("title")
  title = title_el.get_text(strip=True) if title_el else "Beauty Editorial"
  title = title.split("|")[0].split("-")[0].strip()
  print(f"[{time.strftime('%H:%M:%S' )}] Заголовок статьи: {title}")

  content_block = art_soup.select_one(
      "article, .entry-content, .post-body, .content"
  ) or art_soup.select_one("body")

  paragraphs = [
      p.get_text(strip=True)
      for p in content_block.find_all("p")
      if len(p.get_text(strip=True)) > 40
  ]
  context_hint = " ".join(paragraphs[:2])[:600] if paragraphs else title

  magazine_hint = (
      title if "Vogue" in title or "Elle" in title else "модном журнале"
  )
  ai_text = generate_ai_article(
      model_name=title, magazine=magazine_hint, description_hint=context_hint
  )

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
