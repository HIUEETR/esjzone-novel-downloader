import os

import wcwidth


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def truncate_and_pad(text: str, target_width: int) -> str:
    """
    将字符串截断或填充至指定的显示宽度。
    """
    if not text:
        text = ""

    text_width = wcwidth.wcswidth(text)

    if text_width <= target_width:
        return text + " " * (target_width - text_width)

    current_width = 0
    result = ""
    ellipsis = "…"
    ellipsis_width = wcwidth.wcwidth(ellipsis)
    if ellipsis_width < 0:
        ellipsis_width = 1

    for char in text:
        char_width = wcwidth.wcwidth(char)
        if char_width < 0:
            char_width = 0

        if current_width + char_width + ellipsis_width > target_width:
            break
        result += char
        current_width += char_width

    result += ellipsis

    return result + " " * (target_width - current_width - ellipsis_width)
