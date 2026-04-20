from __future__ import annotations

import re


COUNTRY_LABELS_RU: dict[str, str] = {
    "AE": "ОАЭ",
    "AM": "Армения",
    "AR": "Аргентина",
    "BD": "Бангладеш",
    "BE": "Бельгия",
    "CL": "Чили",
    "CO": "Колумбия",
    "AU": "Австралия",
    "AZ": "Азербайджан",
    "BR": "Бразилия",
    "CA": "Канада",
    "CN": "Китай",
    "DZ": "Алжир",
    "DE": "Германия",
    "EG": "Египет",
    "ET": "Эфиопия",
    "ES": "Испания",
    "FR": "Франция",
    "GB": "Великобритания",
    "GE": "Грузия",
    "HK": "Гонконг",
    "ID": "Индонезия",
    "IL": "Израиль",
    "IN": "Индия",
    "IR": "Иран",
    "IT": "Италия",
    "JP": "Япония",
    "KE": "Кения",
    "KR": "Южная Корея",
    "LV": "Латвия",
    "MA": "Марокко",
    "MY": "Малайзия",
    "MX": "Мексика",
    "NG": "Нигерия",
    "NL": "Нидерланды",
    "NO": "Норвегия",
    "NZ": "Новая Зеландия",
    "PE": "Перу",
    "PH": "Филиппины",
    "PK": "Пакистан",
    "PL": "Польша",
    "QA": "Катар",
    "RU": "Россия",
    "SA": "Саудовская Аравия",
    "SE": "Швеция",
    "SG": "Сингапур",
    "SY": "Сирия",
    "TH": "Таиланд",
    "TR": "Турция",
    "TW": "Тайвань",
    "UA": "Украина",
    "US": "США",
    "VE": "Венесуэла",
    "VN": "Вьетнам",
    "ZA": "ЮАР",
}

TOP_COUNTRY_CODES: list[str] = [
    "US", "GB", "DE", "FR", "IT", "ES", "NL", "BE", "PL", "UA",
    "RU", "TR", "IL", "IR", "AM", "AZ", "SA", "AE", "QA", "EG", "ZA", "NG",
    "MA", "DZ", "ET", "KE", "CN", "JP", "KR", "IN", "PK", "BD",
    "ID", "MY", "SG", "TH", "VN", "PH", "HK", "TW", "AU", "NZ",
    "CA", "MX", "BR", "AR", "CL", "CO", "PE", "VE", "SE", "NO",
]

COUNTRY_ALIASES: dict[str, str] = {
    "ae": "AE",
    "am": "AM",
    "armenia": "AM",
    "arab emirates": "AE",
    "argentina": "AR",
    "ar": "AR",
    "australia": "AU",
    "australian": "AU",
    "au": "AU",
    "azerbaijan": "AZ",
    "az": "AZ",
    "bangladesh": "BD",
    "bd": "BD",
    "belgium": "BE",
    "be": "BE",
    "brazil": "BR",
    "br": "BR",
    "britain": "GB",
    "canada": "CA",
    "ca": "CA",
    "chile": "CL",
    "cl": "CL",
    "china": "CN",
    "cn": "CN",
    "colombia": "CO",
    "co": "CO",
    "de": "DE",
    "dz": "DZ",
    "algeria": "DZ",
    "egypt": "EG",
    "eg": "EG",
    "ethiopia": "ET",
    "et": "ET",
    "england": "GB",
    "es": "ES",
    "fr": "FR",
    "france": "FR",
    "germany": "DE",
    "ge": "GE",
    "georgia": "GE",
    "gb": "GB",
    "great britain": "GB",
    "hong kong": "HK",
    "hk": "HK",
    "id": "ID",
    "india": "IN",
    "indonesia": "ID",
    "in": "IN",
    "iran": "IR",
    "ir": "IR",
    "israel": "IL",
    "il": "IL",
    "italy": "IT",
    "it": "IT",
    "japan": "JP",
    "jp": "JP",
    "kenya": "KE",
    "ke": "KE",
    "korea": "KR",
    "kr": "KR",
    "latvia": "LV",
    "lv": "LV",
    "malaysia": "MY",
    "morocco": "MA",
    "ma": "MA",
    "my": "MY",
    "mexico": "MX",
    "mx": "MX",
    "netherlands": "NL",
    "nl": "NL",
    "new zealand": "NZ",
    "nz": "NZ",
    "nigeria": "NG",
    "ng": "NG",
    "norway": "NO",
    "no": "NO",
    "pakistan": "PK",
    "pk": "PK",
    "peru": "PE",
    "pe": "PE",
    "philippines": "PH",
    "ph": "PH",
    "poland": "PL",
    "pl": "PL",
    "qatar": "QA",
    "qa": "QA",
    "russia": "RU",
    "russian federation": "RU",
    "ru": "RU",
    "sa": "SA",
    "saudi arabia": "SA",
    "sg": "SG",
    "singapore": "SG",
    "south korea": "KR",
    "syria": "SY",
    "sy": "SY",
    "sweden": "SE",
    "se": "SE",
    "taiwan": "TW",
    "tw": "TW",
    "thailand": "TH",
    "th": "TH",
    "tr": "TR",
    "turkey": "TR",
    "turkiye": "TR",
    "uae": "AE",
    "uk": "GB",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "united states": "US",
    "united states of america": "US",
    "ukraine": "UA",
    "ua": "UA",
    "us": "US",
    "usa": "US",
    "venezuela": "VE",
    "ve": "VE",
    "vietnam": "VN",
    "vn": "VN",
    "za": "ZA",
    "south africa": "ZA",
}

UNKNOWN_MARKERS = {"", "unknown", "none", "null", "n/a", "—", "-"}


def normalize_country_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in UNKNOWN_MARKERS:
        return None
    if len(cleaned) == 2 and cleaned.upper() in COUNTRY_LABELS_RU:
        return cleaned.upper()
    normalized = re.sub(r"[^a-z\s]+", " ", lowered)
    normalized = " ".join(normalized.split())
    if normalized in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[normalized]
    return None


def country_label_ru(value: str | None) -> str | None:
    code = normalize_country_code(value)
    if not code:
        return None
    return COUNTRY_LABELS_RU.get(code, code)


def normalize_country_label_ru(value: str | None) -> str | None:
    label = country_label_ru(value)
    if label:
        return label
    cleaned = " ".join(str(value).split()).strip() if value else ""
    if not cleaned or cleaned.lower() in UNKNOWN_MARKERS:
        return None
    return cleaned


def top_country_options_ru() -> list[dict[str, str]]:
    return [
        {"code": code, "label": COUNTRY_LABELS_RU[code]}
        for code in TOP_COUNTRY_CODES
        if code in COUNTRY_LABELS_RU
    ]
