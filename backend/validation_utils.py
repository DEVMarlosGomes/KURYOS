import re


EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)


def clean_text(value: str) -> str:
    return str(value or "").strip()


def normalize_email(value: str) -> str:
    return clean_text(value).lower()


def is_valid_email(value: str) -> bool:
    email = normalize_email(value)
    return bool(email) and bool(EMAIL_RE.match(email))


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def is_valid_phone(value: str) -> bool:
    digits = normalize_phone(value)
    if len(digits) not in (10, 11, 12, 13):
        return False
    return digits != digits[:1] * len(digits)


def normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def is_valid_cnpj(value: str) -> bool:
    digits = normalize_cnpj(value)
    if len(digits) != 14 or digits == digits[:1] * 14:
        return False

    def calc_digit(base: str, factors: list[int]) -> str:
        total = sum(int(digit) * factor for digit, factor in zip(base, factors))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = calc_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = calc_digit(digits[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[-2:] == first + second
