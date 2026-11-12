# 게시물 본문 정리(허용 태그만 남기기, 스크립트·이벤트 속성·위험한 주소 제거)를 확인하는 시험
import pytest

from app.domain.board.sanitize import clean_body, has_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("평범한 글", "평범한 글"),
        ("<p>문단</p><br><strong>굵게</strong>", "<p>문단</p><br><strong>굵게</strong>"),
        ("<ul><li>하나</li><li>둘</li></ul>", "<ul><li>하나</li><li>둘</li></ul>"),
        ("<script>alert(1)</script>본문", "본문"),
        ("<style>p{color:red}</style>본문", "본문"),
        ("<iframe src='x'>안</iframe>본문", "본문"),
        ('<p onclick="x()" style="a">문단</p>', "<p>문단</p>"),
        ("<img src=x onerror=alert(1)>글", "글"),
        ("<div><span>안쪽</span></div>", "안쪽"),  # 허용하지 않는 태그는 글자만 남는다
        ("a < b && c > d", "a &lt; b &amp;&amp; c &gt; d"),
        ("<p>열고 안 닫음", "<p>열고 안 닫음</p>"),
        ("닫기만</strong></p>", "닫기만"),
        ("<p><strong>겹침</p></strong>", "<p><strong>겹침</strong></p>"),
        ("<b>&lt;script&gt;</b>", "<b>&lt;script&gt;</b>"),  # 글자로 쓴 꺾쇠는 글자로 남는다
        ("<SCRIPT>x</SCRIPT>글", "글"),
        ("<script><script>x</script></script>글", "글"),
        ("<!-- 주석 -->글", "글"),
        ("<br/>줄", "<br>줄"),
        ("<svg><b>안</b></svg>글", "글"),  # 버리는 태그 안의 태그도 나오지 않는다
        ("<b><iframe></b>x</iframe>글</b>", "<b>글</b>"),  # 버리는 태그 안의 닫는 태그가 바깥을 닫지 못한다
        ("<svg><svg></svg>x</svg>글", "글"),  # 겹친 버림 태그는 바깥이 닫힐 때까지 이어진다
    ],
)
def test_허용한_태그만_남기고_나머지는_정리한다(raw: str, expected: str) -> None:
    assert clean_body(raw) == expected


@pytest.mark.parametrize(
    "scheme", ["http://example.com/a?b=1&c=2", "https://example.com", "mailto:a@example.com"]
)
def test_안전한_링크는_주소만_남기고_rel을_붙인다(scheme: str) -> None:
    out = clean_body(f'<a href="{scheme}" onclick="x()" target="_blank">링크</a>')
    assert out.startswith(f'<a href="{scheme.replace("&", "&amp;")}" rel="noopener noreferrer">')
    assert out.endswith("링크</a>") and "onclick" not in out and "target" not in out


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        " JavaScript:alert(1)",
        "data:text/html,x",
        "vbscript:x",
        "//evil.example",
        "/상대",
        "",
    ],
)
def test_위험하거나_안전하지_않은_주소의_링크는_글자만_남긴다(href: str) -> None:
    assert clean_body(f'<a href="{href}">링크</a>') == "링크"


def test_링크_주소의_따옴표는_이스케이프한다() -> None:
    out = clean_body("<a href='https://e.com/\"onmouseover=\"x'>글</a>")
    assert '"onmouseover' not in out and "&quot;" in out


def test_태그만_남은_본문은_읽을_글자가_없다() -> None:
    assert has_text("<p>글</p>") and has_text("글")
    assert (
        not has_text("") and not has_text("<p> </p><br>") and not has_text(clean_body("<script>x</script>"))
    )
    assert has_text("&lt;")  # 글자로 쓴 꺾쇠도 글자다
