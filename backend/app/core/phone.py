import re

_PHONE_RE = re.compile(r"^\+7\d{10}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("8") and len(digits) == 11:
        digits = "+7" + digits[1:]
    elif digits.startswith("7") and not digits.startswith("+"):
        digits = "+" + digits
    return digits


def validate_phone(raw: str) -> str:
    normalized = normalize_phone(raw)
    if not _PHONE_RE.match(normalized):
        raise ValueError("Номер телефона должен быть в формате +7XXXXXXXXXX")
    return normalized
