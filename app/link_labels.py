from __future__ import annotations

import urllib.parse

COUNTRY_NAME_TO_CODE = {
    "香港": "HK",
    "日本": "JP",
    "韩国": "KR",
    "美国": "US",
    "台湾": "TW",
    "新加坡": "SG",
    "土耳其": "TR",
    "澳洲": "AU",
    "澳大利亚": "AU",
    "中国": "CN",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "japan": "JP",
    "korea": "KR",
    "south korea": "KR",
    "hong kong": "HK",
    "taiwan": "TW",
    "singapore": "SG",
    "turkey": "TR",
    "australia": "AU",
    "china": "CN",
}


def _node_value(node: dict | object, key: str) -> str:
    try:
        if isinstance(node, dict):
            return str(node.get(key) or "").strip()
        if hasattr(node, "keys") and key in node.keys():
            return str(node[key] or "").strip()
        return str(getattr(node, key, "") or "").strip()
    except Exception:
        return ""


def country_code_to_flag(country_code: str) -> str:
    code = str(country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(127397 + ord(ch)) for ch in code)


def country_text_to_code(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) == 2 and text.isalpha():
        return text.upper()
    lowered = text.lower()
    if lowered in COUNTRY_NAME_TO_CODE:
        return COUNTRY_NAME_TO_CODE[lowered]
    for key, code in COUNTRY_NAME_TO_CODE.items():
        if key and key.lower() in lowered:
            return code
    return ""


def node_country_code(node: dict | object) -> str:
    manual_code = country_text_to_code(_node_value(node, "manual_country_code"))
    if manual_code:
        return manual_code
    manual_label = country_text_to_code(_node_value(node, "manual_region_label"))
    if manual_label:
        return manual_label
    auto_code = country_text_to_code(_node_value(node, "country_code"))
    if auto_code:
        return auto_code
    auto_label = country_text_to_code(_node_value(node, "country") or _node_value(node, "region_label"))
    if auto_label:
        return auto_label
    return ""


def node_flag_emoji(node: dict | object) -> str:
    return country_code_to_flag(node_country_code(node))


def vless_remark_for_node(node: dict | object, fallback_name: str = "") -> str:
    name = _node_value(node, "name") or str(fallback_name or "").strip()
    flag = node_flag_emoji(node)
    return f"{flag} {name}".strip() if flag else name


def replace_vless_fragment(link: str, remark: str) -> str:
    link = str(link or "").strip()
    remark = str(remark or "").strip()
    if not link or not remark:
        return link
    try:
        parsed = urllib.parse.urlparse(link)
    except ValueError:
        return link
    if parsed.scheme != "vless":
        return link
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            urllib.parse.quote(remark, safe=""),
        )
    )
