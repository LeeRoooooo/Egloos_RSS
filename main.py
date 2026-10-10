import xml.etree.ElementTree as ET
from datetime import datetime
import re
from urllib.parse import urljoin, quote
from playwright.sync_api import sync_playwright


def parse_date_string(date_val):
    """
    썸네일 파일명 속 14자리 숫자(예: 20261010141009) 또는 ISO 8601 문자열을 RSS 규격으로 변환
    """
    if not date_val:
        return datetime.now().strftime("%Y.%m.%d %H:%M:%S")

    # 1. 썸네일 파일명 속 14자리 숫자 추출
    match_14 = re.search(r'(\d{14})', str(date_val))
    if match_14:
        try:
            dt = datetime.strptime(match_14.group(1), "%Y%m%d%H%M%S")
            return dt.strftime("%Y.%m.%d %H:%M:%S")
        except ValueError:
            pass

    # 2. ISO 8601 형식 파싱
    clean_iso = str(date_val).replace("Z", "").split(".")[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(clean_iso, fmt)
            return dt.strftime("%Y.%m.%d %H:%M:%S")
        except ValueError:
            continue

    return datetime.now().strftime("%Y.%m.%d %H:%M:%S")


def scrape_egloos_with_playwright():
    target_url = "https://egloos.com/posts"

    # RSS 피드 기본 틀 구성
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "이글루스 최신 포스트 피드"
    ET.SubElement(channel, "link").text = target_url
    ET.SubElement(channel, "description").text = "실시간 업로드 시간 동기화 피드"

    items_processed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        print(f"[1/4] 접속 중: {target_url}")
        page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

        # 캡처를 통해 확인된 실제 카드 컴포넌트 클래스 대기
        card_selector = "a[class*='SearchPostCard_card']"
        try:
            page.wait_for_selector(card_selector, timeout=10000)
            print("[2/4] SearchPostCard 렌더링 감지 완료.")
        except Exception:
            print("[경고] 선택자 대기 시간 초과. 3초간 추가 대기합니다.")
            page.wait_for_timeout(3000)

        # 카드가 렌더링된 요소 목록 획득
        post_cards = page.locator("a[class*='SearchPostCard_card']").all()
        print(f"[3/4] 발견된 카드 수: {len(post_cards)}개")

        for card in post_cards:
            try:
                # 1. 링크 추출 (카드 자체가 a 태그)
                raw_href = card.get_attribute("href") or ""
                if not raw_href or raw_href.startswith("http") and "egloos.com" not in raw_href:
                    continue
                full_link = urljoin("https://egloos.com", quote(raw_href, safe="/:?=&"))

                # 2. 제목 추출
                title_elm = card.locator("p[class*='title']").first
                if title_elm.count() == 0:
                    continue
                title = title_elm.inner_text().strip()
                if not title:
                    continue

                # 3. 요약 본문 추출
                desc_elm = card.locator("p[class*='description']").first
                description = desc_elm.inner_text().strip() if desc_elm.count() > 0 else title

                # 4. 작성 채널명 추출 (옵션)
                channel_elm = card.locator("span[class*='channelName']").first
                channel_name = channel_elm.inner_text().strip() if channel_elm.count() > 0 else ""

                # 5. 썸네일 이미지 파일명에서 14자리 시간 추출 (예: 20261010141009)
                pub_date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
                thumb_img = card.locator("div[class*='thumb'] img").first
                if thumb_img.count() > 0:
                    img_src = thumb_img.get_attribute("srcset") or thumb_img.get_attribute("src") or ""
                    pub_date = parse_date_string(img_src)

                # 6. RSS Element 등록
                rss_item = ET.SubElement(channel, "item")
                ET.SubElement(rss_item, "title").text = f"[{channel_name}] {title}" if channel_name else title
                ET.SubElement(rss_item, "link").text = full_link
                ET.SubElement(rss_item, "description").text = description
                ET.SubElement(rss_item, "pubDate").text = pub_date

                items_processed += 1
            except Exception:
                continue

        browser.close()

    # XML 들여쓰기 및 파일 저장
    ET.indent(rss, space="  ", level=0)
    xml_str = ET.tostring(rss, encoding="utf-8", method="xml").decode("utf-8")
    final_rss = '<?xml version="1.0" encoding="UTF-8" ?>\n' + xml_str

    output_filename = "egloos_feedv2.xml"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_rss)

    print(f"[4/4] 완료: '{output_filename}' 파일 생성 완료 (총 {items_processed}개 추출)")


if __name__ == "__main__":
    scrape_egloos_with_playwright()
