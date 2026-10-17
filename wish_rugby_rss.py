import os
import re
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin, urlparse


BASE_URL = "https://wish.sa-hiroshima.com"
START_URL = "https://wish.sa-hiroshima.com/magazines/rugby/"
OUTPUT_FILE = "wish_rugby.xml"

FEED_TITLE = "Team WISH ラグビー"
FEED_LINK = START_URL
FEED_DESCRIPTION = "Team WISH マガジン「ラグビー」更新情報"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

ARTICLE_URL_RE = re.compile(
    r"^https://wish\.sa-hiroshima\.com/(\d+)\.html/?$"
)

DATE_RE = re.compile(
    r"^(20\d{2})\.(\d{1,2})\.(\d{1,2})\s*"
)

CATEGORY_WORDS = [
    "車いすラグビー",
    "スペシャルオリンピックス",
    "3人制バスケットボール",
    "インクルーシブフットボール",
    "アーティスティックスイミング",
    "クロスカントリー",
    "トレイルランニング",
    "アウトドアスポーツ",
    "マリンスポーツ",
    "アーバンスポーツ",
    "自転車ロードレース",
    "ソフトテニス",
    "高校野球",
    "女子野球",
    "女性スポーツ",
    "パラリンピック",
    "パラスポーツ",
    "ユニバーサルスポーツ",
    "アスリート飯",
    "ハンドボール",
    "バスケットボール",
    "ラグビー",
    "TeamWISH",
    "取材記事",
    "未分類",
    "イベント",
    "コラム",
]


def fetch(url):
    last_error = None

    for attempt in range(1, 4):
        try:
            print(f"取得試行 {attempt}/3: {url}")

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            print(
                f"HTTP: {response.status_code} / "
                f"取得バイト数: {len(response.content)}"
            )

            response.raise_for_status()

            response.encoding = response.apparent_encoding

            return response.text

        except Exception as e:
            last_error = e
            print(f"取得失敗: {e}")

            if attempt < 3:
                print("10秒待って再試行します。")
                time.sleep(10)

    raise RuntimeError(
        f"ページを取得できませんでした: {url} / {last_error}"
    )


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def make_guid(link):
    return hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()


def remove_category_words(text):
    result = text.strip()

    changed = True

    while changed:
        changed = False

        for word in CATEGORY_WORDS:
            pattern = rf"^{re.escape(word)}\s*"

            new_result = re.sub(
                pattern,
                "",
                result
            ).strip()

            if new_result != result:
                result = new_result
                changed = True

    return result


def extract_articles_from_page(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    articles = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(
            BASE_URL,
            a["href"]
        )

        parsed = urlparse(href)

        normalized_link = (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{parsed.path}"
        )

        if not ARTICLE_URL_RE.match(
            normalized_link
        ):
            continue

        if normalized_link in seen_links:
            continue

        text = clean_text(
            a.get_text(" ", strip=True)
        )

        if not text:
            continue

        date_match = DATE_RE.match(text)

        if not date_match:
            continue

        year = int(
            date_match.group(1)
        )
        month = int(
            date_match.group(2)
        )
        day = int(
            date_match.group(3)
        )

        try:
            published = datetime(
                year,
                month,
                day,
                12,
                0,
                0,
                tzinfo=JST
            )

        except ValueError:
            continue

        title = text[
            date_match.end():
        ].strip()

        title = remove_category_words(
            title
        )

        if not title:
            continue

        articles.append({
            "title": title,
            "link": normalized_link,
            "guid": make_guid(
                normalized_link
            ),
            "published": published,
            "description": title,
        })

        seen_links.add(
            normalized_link
        )

    return articles


def find_rugby_pages(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    pages = {
        START_URL.rstrip("/")
    }

    for a in soup.find_all(
        "a",
        href=True
    ):
        href = urljoin(
            BASE_URL,
            a["href"]
        )

        href = href.rstrip("/")

        if href == START_URL.rstrip("/"):
            pages.add(href)
            continue

        if re.fullmatch(
            r"https://wish\.sa-hiroshima\.com/"
            r"magazines/rugby-\d+\.html",
            href
        ):
            pages.add(href)

    def page_number(url):
        if url == START_URL.rstrip("/"):
            return 1

        match = re.search(
            r"rugby-(\d+)\.html$",
            url
        )

        if match:
            return int(
                match.group(1)
            )

        return 999999

    return sorted(
        pages,
        key=page_number
    )


def collect_current_articles():
    first_html = fetch(
        START_URL
    )

    pages = find_rugby_pages(
        first_html
    )

    print()
    print(
        f"検出したラグビーページ数: "
        f"{len(pages)}"
    )

    for page in pages:
        print(f"  {page}")

    all_articles = {}

    for index, page_url in enumerate(
        pages,
        1
    ):
        if (
            page_url.rstrip("/")
            == START_URL.rstrip("/")
        ):
            html = first_html

        else:
            html = fetch(
                page_url
            )

        articles = extract_articles_from_page(
            html
        )

        print(
            f"ページ{index}: "
            f"{len(articles)}件"
        )

        for article in articles:
            all_articles[
                article["link"]
            ] = article

    articles = list(
        all_articles.values()
    )

    articles.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    return articles


def load_existing():
    existing = {}

    if not os.path.exists(
        OUTPUT_FILE
    ):
        return existing

    tree = ET.parse(
        OUTPUT_FILE
    )

    root = tree.getroot()

    for item in root.findall(
        "./channel/item"
    ):
        title = item.findtext(
            "title",
            ""
        ).strip()

        link = item.findtext(
            "link",
            ""
        ).strip()

        guid = item.findtext(
            "guid",
            ""
        ).strip()

        pub_date = item.findtext(
            "pubDate",
            ""
        ).strip()

        description = item.findtext(
            "description",
            ""
        ).strip()

        if not link:
            continue

        try:
            published = parsedate_to_datetime(
                pub_date
            )

            if published.tzinfo is None:
                published = published.replace(
                    tzinfo=JST
                )

        except Exception:
            continue

        existing[link] = {
            "title": title,
            "link": link,
            "guid": (
                guid
                or make_guid(link)
            ),
            "published": published,
            "description": description,
        }

    return existing


def build_rss(articles):
    rss = ET.Element(
        "rss",
        version="2.0"
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link"
    ).text = FEED_LINK

    ET.SubElement(
        channel,
        "description"
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language"
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        datetime.now(JST)
    )

    for article in articles:
        item = ET.SubElement(
            channel,
            "item"
        )

        ET.SubElement(
            item,
            "title"
        ).text = article["title"]

        ET.SubElement(
            item,
            "link"
        ).text = article["link"]

        guid = ET.SubElement(
            item,
            "guid"
        )

        guid.set(
            "isPermaLink",
            "false"
        )

        guid.text = article["guid"]

        ET.SubElement(
            item,
            "pubDate"
        ).text = format_datetime(
            article["published"]
        )

        ET.SubElement(
            item,
            "description"
        ).text = article[
            "description"
        ]

    tree = ET.ElementTree(
        rss
    )

    try:
        ET.indent(
            tree,
            space="  "
        )
    except AttributeError:
        pass

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )


def main():
    existing = load_existing()

    print(
        f"既存RSS件数: "
        f"{len(existing)}"
    )

    try:
        current = collect_current_articles()

        print()
        print(
            f"公式サイトから取得: "
            f"{len(current)}件"
        )

        if not current:
            raise RuntimeError(
                "記事を1件も抽出できませんでした。"
            )

        current_by_link = {
            article["link"]: article
            for article in current
        }

        new_count = sum(
            1
            for link in current_by_link
            if link not in existing
        )

        merged = dict(
            existing
        )

        merged.update(
            current_by_link
        )

        all_articles = list(
            merged.values()
        )

        all_articles.sort(
            key=lambda x: x["published"],
            reverse=True
        )

        print(
            f"新規記事: "
            f"{new_count}件"
        )

        print(
            f"累積RSS件数: "
            f"{len(all_articles)}"
        )

        print()
        print("最新30件:")

        for article in all_articles[:30]:
            print(
                article["published"]
                .astimezone(JST)
                .strftime("%Y-%m-%d"),
                article["title"]
            )

        build_rss(
            all_articles
        )

        print()
        print(
            f"保存完了: "
            f"{OUTPUT_FILE} "
            f"({len(all_articles)}件)"
        )

    except Exception:
        print()
        print(
            "取得・解析に失敗したため、"
            "既存RSSは変更しません。"
        )
        raise


if __name__ == "__main__":
    main()