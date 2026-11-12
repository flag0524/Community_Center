# 게시물 본문의 서식을 허용 목록만 남기고 정리하는 도구. 스크립트·이벤트 속성·위험한 주소는 저장 전에 걸러 낸다
import html
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS = frozenset(
    {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h3", "h4", "blockquote", "a"}
)
VOID_TAGS = frozenset({"br"})
DROP_WITH_CONTENT = frozenset(
    {"script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math"}
)
SAFE_SCHEMES = frozenset({"http", "https", "mailto"})


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []
        self.skipping = 0  # 내용까지 버릴 태그 안에 있는 깊이

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROP_WITH_CONTENT:
            self.skipping += 1
            return
        if self.skipping or tag not in ALLOWED_TAGS:
            return  # 허용하지 않는 태그는 태그만 버리고 안의 글자는 남긴다
        if tag == "a":
            href = next((v for k, v in attrs if k == "href" and v), None)
            if href is None or urlparse(href.strip()).scheme.lower() not in SAFE_SCHEMES:
                return  # 안전한 주소가 없는 링크는 글자만 남긴다
            self.out.append(f'<a href="{html.escape(href.strip(), quote=True)}" rel="noopener noreferrer">')
            self.open.append("a")
            return
        self.out.append(f"<{tag}>")  # 속성은 모두 버린다
        if tag not in VOID_TAGS:
            self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in DROP_WITH_CONTENT:
            self.skipping = max(0, self.skipping - 1)
            return
        if self.skipping or tag not in self.open:
            return  # 짝이 없는 닫는 태그는 버린다
        while self.open:  # 안쪽에 열린 태그를 먼저 닫아 짝을 맞춘다
            closing = self.open.pop()
            self.out.append(f"</{closing}>")
            if closing == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.open:
            self.out.append(f"</{self.open.pop()}>")
        return "".join(self.out)


def clean_body(raw: str) -> str:
    """허용 태그(문단·줄바꿈·굵게·기울임·밑줄·목록·소제목·인용·안전한 링크)만 남긴다. 속성은 링크 주소뿐이다."""
    cleaner = _Cleaner()
    cleaner.feed(raw)
    cleaner.close()
    return cleaner.result().strip()


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def has_text(cleaned: str) -> bool:
    """정리한 본문에 사람이 읽을 글자가 있는가. 태그만 남은 본문은 비어 있는 것이다."""
    reader = _Text()
    reader.feed(cleaned)
    reader.close()
    return bool("".join(reader.parts).strip())
