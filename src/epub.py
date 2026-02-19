from __future__ import annotations

import uuid
import zipfile
import datetime as _dt
from pathlib import Path
from typing import Iterable
from io import BytesIO
from PIL import Image

from .model import Book, Chapter


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_epub(book: Book, chapters: Iterable[Chapter], output_path: str | Path) -> None:
    output_path = Path(output_path)
    book_id = str(uuid.uuid4())

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        container_xml = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        zf.writestr("META-INF/container.xml", container_xml)

        spine_items: list[str] = []
        manifest_items: list[str] = []
        
        # 用于收集所有图片，避免重复写入
        all_images: dict[str, tuple[bytes, str]] = {}

        for ch in chapters:
            # 收集图片
            if hasattr(ch, "images") and ch.images:
                for filename, content in ch.images.items():
                    if filename not in all_images:
                        # 简单的 mimetype 推断
                        ext = Path(filename).suffix.lower()
                        if ext == ".png":
                            mimetype = "image/png"
                        elif ext == ".gif":
                            mimetype = "image/gif"
                        elif ext == ".webp":
                            mimetype = "image/webp"
                        else:
                            mimetype = "image/jpeg"
                        all_images[filename] = (content, mimetype)

            chapter_filename = f"OEBPS/chapter_{ch.index}.xhtml"
            spine_items.append(f'<itemref idref="chap{ch.index}"/>')
            manifest_items.append(
                f'<item id="chap{ch.index}" href="chapter_{ch.index}.xhtml" '
                f'media-type="application/xhtml+xml"/>'
            )
            body_title = ch.title or f"第 {ch.index} 章"
            body_content = ch.content_html or "<p></p>"
            chapter_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>{escape_xml(body_title)}</title>
    <meta charset="utf-8" />
  </head>
  <body>
    <h1>{escape_xml(body_title)}</h1>
    {body_content}
  </body>
</html>
"""
            zf.writestr(chapter_filename, chapter_xhtml)

        # 写入图片资源
        cover_id = None
        if book.cover_image:
            # 检测封面图片格式
            cover_ext = ".png"
            cover_mime = "image/png"
            try:
                # 使用 with 确保文件句柄关闭
                with Image.open(BytesIO(book.cover_image)) as img:
                    if img.format == "JPEG":
                        cover_ext = ".jpg"
                        cover_mime = "image/jpeg"
            except Exception:
                pass # 默认使用 png

            zf.writestr(f"OEBPS/images/cover{cover_ext}", book.cover_image)
            cover_id = "cover_img"
            manifest_items.append(
                f'<item id="{cover_id}" href="images/cover{cover_ext}" media-type="{cover_mime}" properties="cover-image"/>'
            )

        for filename, (content, mimetype) in all_images.items():
            zf.writestr(f"OEBPS/images/{filename}", content)
            manifest_items.append(
                f'<item id="img_{filename.replace(".", "_")}" href="images/{filename}" media-type="{mimetype}"/>'
            )

        # 生成 toc.ncx
        ncx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{escape_xml(book.title)}</text>
  </docTitle>
  <navMap>
"""
        for i, ch in enumerate(chapters):
             ncx_content += f"""    <navPoint id="navPoint-{i+1}" playOrder="{i+1}">
      <navLabel>
        <text>{escape_xml(ch.title)}</text>
      </navLabel>
      <content src="chapter_{ch.index}.xhtml"/>
    </navPoint>
"""
        ncx_content += """  </navMap>
</ncx>
"""
        zf.writestr("OEBPS/toc.ncx", ncx_content)
        manifest_items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')

        manifest = "\n    ".join(manifest_items)
        spine = "\n    ".join(spine_items)
        now = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        # 构建 tags 元数据
        tags_xml = "\n    ".join([f"<dc:subject>{escape_xml(tag)}</dc:subject>" for tag in book.tags])
        
        # 构建 description
        description_xml = f"<dc:description>{escape_xml(book.introduction)}</dc:description>" if book.introduction else ""
        
        # 构建 cover meta
        cover_meta = f'<meta name="cover" content="{cover_id}" />' if cover_id else ""

        content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{escape_xml(book.title)}</dc:title>
    <dc:creator>{escape_xml(book.author)}</dc:creator>
    <dc:language>zh</dc:language>
    <meta property="dcterms:modified">{now}</meta>
    {tags_xml}
    {description_xml}
    {cover_meta}
  </metadata>
  <manifest>
    {manifest}
  </manifest>
  <spine toc="ncx">
    {spine}
  </spine>
</package>
"""
        zf.writestr("OEBPS/content.opf", content_opf)

