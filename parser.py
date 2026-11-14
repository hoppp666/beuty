from datetime import datetime
import os
import time
from bs4 import BeautifulSoup
from google import genai
import requests

TARGET_URL = "https://anneofcarversville.com/beauty"
BASE_DOMAIN = "https://anneofcarversville.com"
FEED_FILENAME = "feed.xml"
IMAGES_DIR = "images"
MAX_ITEMS_HISTORY = 30

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
print(
    f"GEMINI_API_KEY найден: {'Да (длина ' + str(len(GEMINI_API_KEY)) + ')' if GEMINI_API_KEY else 'НЕТ!'}"
)

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def generate_ai_article(model_name, magazine, description_hint):
  if not client:
    return (
        f"Новая потрясающая фотосессия с участием {model_name} для"
        f" {magazine}. Смотрите кадры в высоком разрешении!"
    )

  prompt = (
      f"Напиши короткую, живую и увлекательную статью на русском языке"
      f" (примерно 1000-1200 символов) для бьюти-сообщества ВКонтакте. Опиши"
      f" образ, эстетику и настроение новой фотосессии, где главная звезда —"
      f" {model_name}, а съемка вышла в журнале {magazine}."
      f" Контекст/детали: {description_hint}."
      " Пиши профессионально, но легко, на чистом русском языке, без банальных"
      " клише и канцелярита."
  )

  try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text.strip()
  except Exception as e:
    print(f"Ошибка генерации текста через AI: {e}")
    return (
        f"Яркая бьюти-история: {model_name} в новом выпуске {magazine}. Элегантные"
        " образы и вдохновляющие детали макияжа."
    )


def download_and_save_image(img_url, save_dir, base_pages_url):
  if not img_url or "data:image" in img_url or "svg" in img_url:
    return None
  if not os.path.exists(save_dir):
    os.makedirs(save_dir)
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    r = requests.get(img_url, headers=headers, timeout=10)
    if r.status_code == 200 and len(r.content) > 10000:  # отсекаем мелкие иконки
      filename = (
          datetime.utcnow().strftime("%Y%m%d%H%M%S_")
          + str(abs(hash(img_url)) % 10000)
          + ".jpg"
      )
      filepath = os.path.join(save_dir, filename)
      with open(filepath, "wb") as f:
        f.write(r.content)
      print(f"Картинка успешно скачана и сохранена: {filename}")
      return f"{base_pages_url}images/{filename}"
  except Exception as e:
    print(f"Не удалось скачать картинку {img_url}: {e}")
  return None


def cleanup_old_images(save_dir, days=2):
  if not os.path.exists(save_dir):
    return
  now = time.time()
  cutoff = days * 86400
  for filename in os.listdir(save_dir):
    if filename == ".gitkeep":
      continue
    filepath = os.path.join(save_dir, filename)
    if os.path.isfile(filepath):
      if (now - os.path.getmtime(filepath)) > cutoff:
        try:
          os.remove(filepath)
        except Exception:
          pass


def parse_articles(base_pages_url):
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
  }
  print(f"Запрос к {TARGET_URL}...")
  response = requests.get(TARGET_URL, headers=headers)
  print(f"Статус ответа сайта: {response.status_code}")

  if response.status_code != 200:
    print("Ошибка: сайт не отдал страницу.")
    return []

  soup = BeautifulSoup(response.text, "html.parser")
  articles = []

  item_list = soup.select("article, .post, .summary-item")
  print(f"Найдено элементов постов на странице: {len(item_list)}")

  for item in item_list[:3]:
    title_el = item.select_one("h2 a, h3 a, .title a, h2, h3")
    link_el = item.select_one("a")
    if not title_el or not link_el:
      continue

    title = title_el.get_text(strip=True)
    link = link_el.get("href")
    if not link.startswith("http"):
      link = BASE_DOMAIN + link

    print(f"Обработка статьи: {title} ({link})")

    try:
      art_resp = requests.get(link, headers=headers)
      if art_resp.status_code != 200:
        print(f"Не удалось открыть статью, статус: {art_resp.status_code}")
        continue
      art_soup = BeautifulSoup(art_resp.text, "html.parser")
    except Exception as e:
      print(f"Ошибка запроса статьи: {e}")
      continue

    content_block = art_soup.select_one(
        ".entry-content, .post-body, .content"
    ) or art_soup.select_one("body")

    images = []
    for img in content_block.find_all("img"):
      # Проверяем разные атрибуты картинок (включая оригиналы и дата-атрибуты)
      src = (
          img.get("data-src")
          or img.get("data-original")
          or img.get("src")
          or ""
      )
      if src and "data:image" not in src:
        if not src.startswith("http"):
          src = BASE_DOMAIN + src
        if (
            "avatar" not in src
            and "logo" not in src
            and "icon" not in src
            and src not in images
            and len(images) < 9
        ):
          local_url = download_and_save_image(src, IMAGES_DIR, base_pages_url)
          if local_url:
            images.append(local_url)

    print(f"Собрано картинок для статьи: {len(images)}")
    if not images:
      print("Пропускаем статью, так как не найдено качественных фото.")
      continue

    magazine_hint = (
        title if "Vogue" in title or "Elle" in title else "Журнал"
    )
    ai_text = generate_ai_article(
        model_name=title, magazine=magazine_hint, description_hint=title
    )

    paragraphs = [
        p.get_text(strip=True)
        for p in content_block.find_all("p")
        if len(p.get_text(strip=True)) > 30
    ]
    p1 = paragraphs[0] if len(paragraphs) > 0 else ai_text
    p2 = (
        paragraphs[1]
        if len(paragraphs) > 1
        else "Детали бьюти-образа и работа команды стилистов."
    )

    formatted_html = f"<p><b>{title}</b></p>"
    formatted_html += f"<p>{ai_text}</p>"
    formatted_html += f"<p>{p1}</p>"

    for img_url in images[:3]:
      formatted_html += f'<p><img src="{img_url}" alt="beauty photo"/></p>'

    formatted_html += f"<p>{p2}</p>"

    for img_url in images[3:]:
      formatted_html += f'<p><img src="{img_url}" alt="beauty photo"/></p>'

    articles.append({
        "title": title,
        "link": link,
        "guid": link,
        "description": formatted_html,
        "pubDate": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
    })

  return articles


def load_existing_feed(filename):
  existing_items = []
  existing_guids = set()
  if not os.path.exists(filename):
    return existing_items, existing_guids
  try:
    with open(filename, "r", encoding="utf-8") as f:
      soup = BeautifulSoup(f.read(), "xml")
    for item in soup.find_all("item"):
      g = item.guid.text if item.guid else (item.link.text if item.link else "")
      if g and g not in existing_guids:
        existing_guids.add(g)
        existing_items.append({
            "title": item.title.text if item.title else "",
            "link": item.link.text if item.link else "",
            "guid": g,
            "pubDate": item.pubDate.text if item.pubDate else "",
            "description": item.description.string if item.description else "",
        })
  except Exception:
    pass
  return existing_items, existing_guids


def save_rss(articles, filename, base_pages_url):
  existing_items, existing_guids = load_existing_feed(filename)
  for art in articles:
    if art["guid"] not in existing_guids:
      existing_items.insert(0, art)
      existing_guids.add(art["guid"])

  existing_items = existing_items[:MAX_ITEMS_HISTORY]

  xml_lines = [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<rss version="2.0">',
      "  <channel>",
      "    <title>Beauty Editorial Feed</title>",
      f"    <link>{base_pages_url}</link>",
      "    <description>Automated beauty editorial RSS for VK</description>",
      "    <language>ru</language>",
  ]

  for art in existing_items:
    safe_title = (
        art["title"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    xml_lines.append("    <item>")
    xml_lines.append(f"      <title>{safe_title}</title>")
    xml_lines.append(f"      <link>{art['link']}</link>")
    xml_lines.append(f"      <guid isPermaLink='true'>{art['guid']}</guid>")
    if art.get("pubDate"):
      xml_lines.append(f"      <pubDate>{art['pubDate']}</pubDate>")
    xml_lines.append(
        f"      <description><![CDATA[{art['description']}]]></description>"
    )
    xml_lines.append("    </item>")

  xml_lines.append("  </channel>")
  xml_lines.append("</rss>")

  with open(filename, "w", encoding="utf-8") as f:
    f.write("\n".join(xml_lines))
  print(f"Файл {filename} успешно сохранен!")


if __name__ == "__main__":
  gh_repo = os.environ.get("GITHUB_REPOSITORY", "hoppp666/beuty")
  parts = gh_repo.split("/")
  owner = parts[0]
  repo = parts[1] if len(parts) > 1 else "beuty"
  pages_url = f"https://{owner}.github.io/{repo}/"

  print(f"GitHub Pages URL: {pages_url}")
  cleanup_old_images(IMAGES_DIR, days=2)
  new_articles = parse_articles(pages_url)
  if new_articles:
    save_rss(new_articles, FEED_FILENAME, pages_url)
  else:
    print("Внимание: новые статьи не были добавлены в RSS.")
