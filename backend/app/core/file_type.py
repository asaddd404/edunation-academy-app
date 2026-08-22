"""Content sniffing for uploads.

The extension and the client's `Content-Type` are both attacker-supplied:
renaming `payload.html` to `payload.png` satisfies an extension allow-list
completely, and the browser sends whatever the form says. So the bytes get
the final word.

Signatures rather than `python-magic`: libmagic is a system package that
would have to be installed into the image and kept in step with it, and the
five formats this project accepts are all identified by a fixed prefix.
"""

from fastapi import HTTPException, UploadFile, status

# extension -> the byte prefixes that are valid for it.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),  # plus the "WEBP" tag at offset 8, checked below
    ".pdf": (b"%PDF-",),
}

# Formats with no usable signature. A .txt/.doc/.docx homework attachment is
# accepted on its extension alone -- but see `save_homework_file`: those are
# only ever served back as `Content-Disposition: attachment` with `nosniff`,
# so a browser never renders one no matter what is inside it.
_UNSIGNED_EXTENSIONS = {".txt", ".doc", ".docx"}

# A .docx is a zip; a .doc is an OLE2 compound file. Neither is required, but
# when the prefix *is* one of these it must match the extension claimed.
_ZIP_PREFIX = b"PK\x03\x04"
_OLE2_PREFIX = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Prefixes that must never be accepted under any extension, because a browser
# coaxed into rendering them executes them.
_ALWAYS_REJECT = (b"<!DOCTYPE", b"<html", b"<HTML", b"<?xml", b"<svg", b"<script", b"<?php", b"#!")


def matches_extension(head: bytes, extension: str) -> bool:
    """Whether `head` (the first bytes of a file) is consistent with `extension`."""
    extension = extension.lower()

    stripped = head.lstrip()[:16]
    if any(stripped.startswith(marker) for marker in _ALWAYS_REJECT):
        return False

    if extension == ".webp":
        return head.startswith(b"RIFF") and head[8:12] == b"WEBP"

    signatures = _SIGNATURES.get(extension)
    if signatures is not None:
        return any(head.startswith(sig) for sig in signatures)

    if extension in _UNSIGNED_EXTENSIONS:
        if head.startswith(_ZIP_PREFIX):
            return extension == ".docx"
        if head.startswith(_OLE2_PREFIX):
            return extension == ".doc"
        return True

    return False


def assert_matches_extension(contents: bytes, extension: str, message: str) -> None:
    if not matches_extension(contents[:32], extension):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message)


async def peek(upload: UploadFile, size: int = 32) -> bytes:
    """Reads the first bytes and rewinds, so the caller can still read it all."""
    head = await upload.read(size)
    await upload.seek(0)
    return head
