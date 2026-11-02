import pytest

from agents.fetch.formats.text import HtmlParser, PlainTextParser

PL = "zażółć gęślą jaźń"


def txt(data: bytes, charset: str | None = None) -> str:
    return PlainTextParser().parse(data, charset=charset)


def html(data: bytes | str, charset: str | None = None) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return HtmlParser().parse(raw, charset=charset)


def test_txt_utf8_bom_utf16() -> None:
    assert txt(PL.encode()) == PL
    assert txt(b"\xef\xbb\xbf" + PL.encode()) == PL
    assert txt(PL.encode("utf-16")) == PL
    assert txt(b"\xff\xfe" + PL.encode("utf-16-le")) == PL
    assert txt(b"\xfe\xff" + PL.encode("utf-16-be")) == PL


def test_txt_cp1250_declared() -> None:
    assert txt(PL.encode("cp1250"), "windows-1250") == PL


def test_txt_cp1250_fallback() -> None:
    assert txt(PL.encode("cp1250")) == PL


def test_txt_unknown_and_wrong_charset() -> None:
    assert txt(PL.encode(), "nope") == PL
    assert txt(PL.encode(), "ascii") == PL


def test_txt_newlines_and_empty() -> None:
    assert txt(b"a\r\nb\rc\nd") == "a\nb\nc\nd"
    assert txt(b"") == ""


def test_txt_never_raises() -> None:
    assert "�" in txt(b"a\x81\x98b")


def test_txt_does_not_sniff_meta() -> None:
    data = '<meta charset="windows-1250">' + PL
    assert txt(data.encode()) == data


def test_html_drops_script_style() -> None:
    out = html("<SCRIPT>var x=1;</SCRIPT>a<style>p{}</style>b<Script>y</sCript>c")
    assert out == "abc"


def test_html_script_content_is_raw() -> None:
    assert html("<script><b>x</script>y") == "y"


def test_html_unclosed_script() -> None:
    assert html("a<script>b<p>c") == "a"


def test_html_stray_end_script() -> None:
    assert html("</script>a") == "a"


def test_html_title_kept_comments_dropped() -> None:
    assert html("<!DOCTYPE html><title>T</title><!-- c --><p>x</p>") == "T\nx"


def test_html_entities() -> None:
    assert html("<p>a &amp; b &lt; c&nbsp;d &ldquo;q&rdquo;</p>") == "a & b < c d “q”"


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("<p>a</p><p>b</p>", "a\nb"),
        ("a<br>b", "a\nb"),
        ("a<br/>b", "a\nb"),
        ("<li>x</li><li>y</li>", "x\ny"),
        ("<b>ab</b>c", "abc"),
        ("a<hr>b", "a\nb"),
        ("<h1>a</h1>b", "a\nb"),
    ],
)
def test_html_block_tags(src: str, expected: str) -> None:
    assert html(src) == expected


def test_html_whitespace() -> None:
    out = html("<p>  a \t\xa0 b  </p>\n\n\n<p> </p><div>\r\n c\r</div>\n")
    assert out == "a b\nc"
    assert not out.endswith("\n")


def test_html_meta_charset() -> None:
    data = b'<meta charset="windows-1250"><p>' + PL.encode("cp1250")
    assert html(data) == PL


def test_html_meta_http_equiv() -> None:
    data = (
        b'<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-2"><p>'
        + PL.encode("iso-8859-2")
    )
    assert html(data) == PL


def test_html_meta_limited_to_2048_bytes() -> None:
    data = b"<p>" + b"x" * 2100 + b'</p><meta charset="iso-8859-2">' + "ą".encode("cp1250")
    assert html(data).endswith("ą")


def test_html_meta_unknown_ignored() -> None:
    assert html(b'<meta charset="nope"><p>' + PL.encode()) == PL


def test_html_meta_decode_error_falls_through() -> None:
    data = b'<meta charset="ascii"><p>' + PL.encode()
    assert html(data) == PL


def test_html_charset_arg_beats_meta() -> None:
    data = b'<meta charset="iso-8859-2"><p>' + PL.encode("cp1250")
    assert html(data, "windows-1250") == PL


def test_html_bom_beats_all() -> None:
    data = b'\xef\xbb\xbf<meta charset="windows-1250"><p>' + PL.encode()
    assert html(data, "windows-1250") == PL


def test_html_malformed() -> None:
    assert html("<p>unclosed <b>bold") == "unclosed bold"
    assert "a" in html("a < b <")
    assert html("<div>" * 10000 + "x") == "x"


def test_html_attributes_ignored() -> None:
    assert html('<a href="http://x.example" title="t">link</a>') == "link"


def test_html_polish_roundtrip() -> None:
    assert html(f"<p>{PL}</p>") == PL


def test_txt_declared_charset_used() -> None:
    assert txt("\u0105".encode("iso-8859-2"), "iso-8859-2") == "\u0105"


def test_html_bare_cr_is_line_break() -> None:
    assert html("a\rb") == "a\nb"
