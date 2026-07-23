from __future__ import annotations

import re
import unicodedata


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[，。；：、（）【】《》“”‘’]+")
_UNIT_REPLACEMENTS = (
    ("千克", "kg"),
    ("公斤", "kg"),
    ("毫克", "mg"),
    ("毫米", "mm"),
    ("厘米", "cm"),
    ("克", "g"),
    ("米", "m"),
)

def _normalize_mass(match: re.Match[str]) -> str:
    value = float(match.group(1))
    unit = match.group(2)
    factor = {"kg": 1_000_000, "g": 1_000, "mg": 1}[unit]
    normalized = value * factor
    if normalized.is_integer():
        return f"{int(normalized)}mg"
    return f"{normalized:g}mg"


def normalize_text(value: str | None) -> str:
    """做安全的通用标准化，不尝试猜测业务含义。"""
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = text.replace("×", "x").replace("＊", "*")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text


def split_material_names(value: str | None) -> list[str]:
    """拆分 Agent 传入的原名称和别名。"""
    original = (value or "").strip()
    parts = [part.strip() for part in re.split(r"[、,，;；/]+", original) if part.strip()]
    return list(dict.fromkeys(parts))


def normalize_spec(value: str | None) -> str:
    text = normalize_text(value)
    for source, target in _UNIT_REPLACEMENTS:
        text = text.replace(source, target)
    text = re.sub(r"(?<![a-z0-9.])(\d+(?:\.\d+)?)\s*(kg|mg|g)\b", _normalize_mass, text)
    text = re.sub(r"\s*(kg|mg|mm|cm|ml|m|g|l)\b", r"\1", text)
    text = re.sub(r"\s*([x*/+-])\s*", r"\1", text)
    return text
