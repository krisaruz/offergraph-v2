"""文本清洗与标准化工具"""

import hashlib
import re
from html.parser import HTMLParser


class _HTMLStripper(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._parts)


def clean_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    stripper.close()
    return normalize_text(stripper.text)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_INTERVIEW_KEYWORDS = [
    "面试", "面经", "笔试", "一面", "二面", "三面", "终面", "HR面",
    "技术面", "算法题", "手撕", "offer", "秋招", "春招", "社招",
    "实习", "暑期", "校招", "OC", "意向书", "录用", "追问", "反问",
]


def extract_keywords(text: str) -> list[str]:
    found = []
    text_lower = text.lower()
    for kw in _INTERVIEW_KEYWORDS:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def is_likely_interview_content(text: str, min_keywords: int = 2) -> bool:
    if len(text) < 30:
        return False
    return len(extract_keywords(text)) >= min_keywords
