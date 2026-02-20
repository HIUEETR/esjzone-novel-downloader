from __future__ import annotations

import re
from urllib.parse import urljoin
from typing import Tuple, List, Dict

from bs4 import BeautifulSoup, Tag

from .model import Book, Chapter


def _get_text_or_empty(node: Tag | None) -> str:
    if node is None:
        return ""
    return node.get_text(strip=True)


def _guess_chapter_title(a_elem: Tag) -> str:
    p = a_elem.find("p")
    if p is not None:
        return p.get_text(strip=True)
    return a_elem.get_text(strip=True)


def parse_book(html: str, url: str) -> Book:
    soup = BeautifulSoup(html, "html.parser")

    title_node = soup.select_one(".book-detail h2")
    if title_node is None:
        raise ValueError("无法从 .book-detail h2 获取书籍标题")
    title = _get_text_or_empty(title_node)

    author = "未知作者"
    for li in soup.select("ul.book-detail li"):
        if li.text and "作者:" in li.text:
            a = li.find("a")
            if a:
                author = _get_text_or_empty(a)
            break

    intro_dom = soup.select_one(".description")
    if intro_dom is None:
        # 尝试其他可能的简介容器
        intro_dom = soup.select_one(".book-description")
    introduction = intro_dom.get_text("\n", strip=True) if intro_dom else ""

    cover_node = soup.select_one(".product-gallery img")
    if cover_node is None:
        cover_node = soup.select_one(".book-detail img")
    cover_url = cover_node.get("src") if cover_node else None
    if cover_url and not cover_url.startswith("http"):
         cover_url = urljoin(url, cover_url)

    tags = [a.get_text(strip=True) for a in soup.select("section.widget-tags.m-t-20 a.tag")]
    if not tags:
        # 尝试更宽泛的选择器
        tags = [a.get_text(strip=True) for a in soup.select(".widget-tags a.tag")]

    book = Book(
        url=url,
        title=title,
        author=author,
        introduction=introduction,
        cover_url=cover_url,
        tags=tags,
    )

    chapter_container = soup.select_one("#chapterList")
    if chapter_container is None:
        return book

    chapter_index = 0
    section_index = 0
    section_name: str | None = None

    for node in chapter_container.children:
        if not isinstance(node, Tag):
            continue
        if node.name == "a":
            chapter_index += 1
            title_text = _guess_chapter_title(node)
            chapter_url = urljoin(url, node.get("href", ""))
            book.chapters.append(
                Chapter(
                    url=chapter_url,
                    title=title_text,
                    index=chapter_index,
                    section_name=section_name,
                    section_index=section_index or None,
                )
            )
        elif node.name == "details":
            summary = node.find("summary")
            section_name = _get_text_or_empty(summary)
            section_index += 1
            for a in node.find_all("a"):
                chapter_index += 1
                title_text = _guess_chapter_title(a)
                chapter_url = urljoin(url, a.get("href", ""))
                book.chapters.append(
                    Chapter(
                        url=chapter_url,
                        title=title_text,
                        index=chapter_index,
                        section_name=section_name,
                        section_index=section_index,
                    )
                )
        elif node.name == "p":
            section_name = _get_text_or_empty(node)
            section_index += 1

    return book


def parse_chapter(html: str, url: str, title: str | None = None) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".forum-content")
    if content is None:
        return title or url, ""

    for node in content.select("h3, footer"):
        node.decompose()

    return title or url, str(content)


def parse_favorites(html: str) -> Tuple[List[Dict[str, str]], int]:
    """
    解析收藏夹/最近更新列表
    返回: (小说列表, 总页数)
    小说列表项: {title, url, latest_chapter, last_viewed, update_time}
    """
    soup = BeautifulSoup(html, "html.parser")
    novels = []
    
    # 解析小说列表
    # 结构通常在表格内
    for tr in soup.select("tr"):
        item = tr.select_one(".product-item")
        if not item:
            continue
            
        title_elem = item.select_one(".product-title a")
        if not title_elem:
            continue
            
        title = title_elem.get_text(strip=True)
        url = title_elem.get("href")
        if url and not url.startswith("http"):
            url = f"https://www.esjzone.one{url}"
            
        latest_chapter_elem = item.select_one(".book-ep .mr-3 a")
        latest_chapter = latest_chapter_elem.get_text(strip=True) if latest_chapter_elem else ""
        
        # 最后观看记录位于 .book-ep 的第二个 div 中
        book_ep_divs = item.select(".book-ep > div")
        last_viewed = ""
        if len(book_ep_divs) > 1:
             last_viewed = book_ep_divs[1].get_text(strip=True).replace("最後觀看：", "").strip()
             
        update_time_elem = item.select_one(".book-update")
        update_time = update_time_elem.get_text(strip=True).replace("更新日期：", "").strip() if update_time_elem else ""
        
        novels.append({
            "title": title,
            "url": url,
            "latest_chapter": latest_chapter,
            "last_viewed": last_viewed,
            "update_time": update_time
        })
        
    # 解析总页数
    total_pages = 1
    script_content = ""
    for script in soup.find_all("script"):
        if script.string and "bootpag" in script.string:
            script_content = script.string
            break
            
    if script_content:
        match = re.search(r"total:\s*(\d+)", script_content)
        if match:
            total_pages = int(match.group(1))
            
    return novels, total_pages

