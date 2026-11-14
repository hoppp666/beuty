from datetime import datetime
import json
import os
import time
from bs4 import BeautifulSoup
from google import genai
import requests

TARGET_URL = "https://anneofcarversville.com/"
BASE_DOMAIN = "https://anneofcarversville.com"
IMAGES_DIR = "temp_images"
HISTORY_FILE = "posted.json"
MAX_HISTORY = 100

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VK_TOKEN = os.environ.get("VK_TOKEN")
# Убираем минус, если случайно ввели его в секретах
RAW_GROUP_ID = os.environ.get("VK_GROUP_ID", "").lstrip("-")

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

  for attempt in range(2):
    try:
      response = client.models.generate_content(
          model="gemini-3.8-flash",
          contents=prompt,
      )
      if response and response.text:
        return response.text.strip()
    except Exception as e:
      print(f"Попытка {attempt + 1} не удалась (ошибка AI): {e}")
      time.sleep(2)

  return (
      f"Яркая бьюти-история: {model_name} в новом выпуске {magazine}. Элегантные"
      " образы, вдохновляющие детали и безупречный стиль.\n\n#beauty #fashion"
      " #editorial #makeup #style"
  )


def download_temp_image(img_url):
  if not img_url or "data:image" in img_url or "svg" in img_url:
    return None
  if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    r = requests.get(img_url, headers=headers, timeout=10)
    if r.status_code == 200 and len(r.content) > 10000:
      filename = f"temp_{abs(hash(img_url)) % 100000}.jpg"
      filepath = os.path.join(IMAGES_DIR, filename)
      with open(filepath, "wb") as f:
        f.write(r.content)
      return filepath
  except Exception as e:
    print(f"Ошибка скачивания фото {img_url}: {e}")
  return None


def upload_photo_to_vk(filepath):
  try:
    res = requests.get(
        "https://api.vk.com/method/photos.getWallUploadServer",
        params={
            "group_id": int(RAW_GROUP_ID),
            "access_token": VK_TOKEN,
            "v": "5.199",
        },
        timeout=10,
    ).json()

    if "error" in res:
      print(f"Ошибка VK getWallUploadServer: {res['error']}")
      return None

    upload_url = res["response"]["upload_url"]

    with open(filepath, "rb") as f:
      upload_res = requests.post(
          upload_url, files={"photo": f}, timeout=15
      ).json()

    save_res = requests.post(
        "https://api.vk.com/method/photos.saveWallPhoto",
        data={
            "group_id": int(RAW_GROUP_ID),
            "photo": upload_res["photo"],
            "server": upload_res["server"],
            "hash": upload_res["hash"],
            "access_token": VK_TOKEN,
            "v": "5.199",
        },
        timeout=10,
    ).json()

    if "error" in save_res:
      print(f"Ошибка VK saveWallPhoto: {save_res['error']}")
      return None

    photo_obj = save_res["response"][0]
    attachment = f"photo{photo_obj['owner_id']}_{photo_obj['id']}"
    print(f"Фото успешно загружено в VK: {attachment}")
    return attachment

  except Exception as e:
    print(f"Исключение при загрузке фото в VK: {e}")
    return None


def publish_post_to_vk(title, text, image_paths, source_link):
  if not VK_TOKEN or not RAW_GROUP_ID:
    print("Пропуск публикации: не заданы VK_TOKEN или VK_GROUP_ID.")
    return False

  attachments = []
  for path in image_paths:
    att = upload_photo_to_vk(path)
    if att:
      attachments.append(att)
    time.sleep(0.5)

  if not attachments:
    print("Не удалось загрузить ни одного фото в VK, отменяем пост.")
    return False

  full_message = f"{title}\n\n{text}\n\nИсточник: {source_link}"

  # Публикация в отложенные записи ровно через 2 часа (7200 секунд)
  future_time = int(time.time()) + 7200

  try:
    post_res = requests.post(
        "https://api.vk.com/method/wall.post",
        data={
            "owner_id": -int(RAW_GROUP_ID),  # Для стены группы нужен минус
            "from_group": 1,
            "message": full_message,
            "attachments": ",".join(attachments),
            "publish_date": future_time,  # Отправка в отложенные
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
        f"УСПЕХ! Пост сохранен в отложенные записи VK (ID записи: {post_id})"
    )
    return True

  except Exception as e:
    print(f"Исключение при вызове wall.post: {e}")
    return False


def cleanup_temp_images():
  if not os.path.exists(IMAGES_DIR):
    return
  for f in os.listdir(IMAGES_DIR):
    try:
      os.remove(os.path.join(IMAGES_DIR, f))
    except Exception:
      pass


def run():
  history = load_history()
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
  }

  print(f"Запрос к {TARGET_URL}...")
  try:
    response = requests.get(TARGET_URL, headers=headers, timeout=10)
  except Exception as e:
    print(f"Ошибка соединения с сайтом: {e}")
    return

  if response.status_code != 200:
    print(f"Сайт вернул статус {response.status_code}")
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

  print(f"Найдено новых (ещё не опубликованных) статей: {len(found_links)}")

  if not found_links:
    print("Новых статей для публикации пока нет.")
    return

  link = found_links[0]
  print(f"Обработка статьи: {link}")

  try:
    art_resp = requests.get(link, headers=headers, timeout=10)
    if art_resp.status_code != 200:
      print(f"Не удалось открыть статью: {art_resp.status_code}")
      return
    art_soup = BeautifulSoup(art_resp.text, "html.parser")
  except Exception as e:
    print(f"Ошибка загрузки статьи: {e}")
    return

  title_el = art_soup.select_one("h1") or art_soup.select_one("title")
  title = title_el.get_text(strip=True) if title_el else "Beauty Editorial"
  title = title.split("|")[0].split("-")[0].strip()

  content_block = art_soup.select_one(
      "article, .entry-content, .post-body, .content"
  ) or art_soup.select_one("body")

  image_paths = []
  seen_urls = set()
  for img in content_block.find_all("img"):
    src = (
        img.get("data-src") or img.get("data-original") or img.get("src") or ""
    )
    if src and "data:image" not in src:
      if not src.startswith("http"):
        src = BASE_DOMAIN + src
      if (
          "avatar" not in src
          and "logo" not in src
          and "icon" not in src
          and src not in seen_urls
      ):
        seen_urls.add(src)
        local_path = download_temp_image(src)
        if local_path:
          image_paths.append(local_path)
        if len(image_paths) >= 9:
          break

  print(f"Скачано фото для загрузки в VK: {len(image_paths)}")
  if not image_paths:
    print("Нет подходящих фото, пропускаем статью.")
    cleanup_temp_images()
    return

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

  success = publish_post_to_vk(title, ai_text, image_paths, link)
  if success:
    history.append(link)
    save_history(history)

  cleanup_temp_images()


if __name__ == "__main__":
  run()
