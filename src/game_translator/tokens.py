import re
from dataclasses import dataclass

TOKEN = re.compile(r"\\(?:[A-Za-z]+(?:\[[^\]\r\n]*\])?|[\\.!|^><{}$])|%(?:\d+\$)?[0-9]*[sdfi]|%\d+|\{[^{}\r\n]+\}|<[^>\r\n]+>")
MARKER = re.compile(r"__GT_\d{5}__")


def protected_tokens(text: str) -> list[str]:
    return TOKEN.findall(text)


def validate_translation(source: str, translation: str):
    if not isinstance(translation, str) or not translation.strip():
        raise ValueError("Translation must not be empty")
    translation.encode("utf-8", errors="strict")
    if "\x00" in translation or MARKER.search(translation):
        raise ValueError("Invalid character or unresolved placeholder")
    if protected_tokens(source) != protected_tokens(translation):
        raise ValueError("Protected token identity, count or order changed")


@dataclass
class ProtectedText:
    text: str
    values: list[str]

    def restore(self, translated: str) -> str:
        expected = [f"__GT_{i:05d}__" for i in range(len(self.values))]
        if MARKER.findall(translated) != expected:
            raise ValueError("Provider changed protected placeholders")
        for marker, value in zip(expected, self.values):
            translated = translated.replace(marker, value)
        return translated


def protect(text: str) -> ProtectedText:
    if MARKER.search(text):
        raise ValueError("Source collides with reserved placeholders")
    values = []
    def replace(match):
        values.append(match.group())
        return f"__GT_{len(values) - 1:05d}__"
    return ProtectedText(TOKEN.sub(replace, text), values)
