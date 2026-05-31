from __future__ import annotations

import json
import socket
import urllib.parse
import urllib.request

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
    "马来西亚": "MY",
    "德国": "DE",
    "英国": "GB",
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
    "malaysia": "MY",
    "germany": "DE",
    "united kingdom": "GB",
    "uk": "GB",
}

_IP_REGION_CACHE: dict[str, str] = {}


def normalize_host_value(value: str) -> str:
    host = str(value or "").strip()
    if not host:
        return ""
    if "://" in host:
        parsed = urllib.parse.urlparse(host)
        host = parsed.hostname or ""
    else:
        host = host.split("/", 1)[0].strip()
        if host.count(":") == 1 and not host.startswith("["):
            maybe_host, maybe_port = host.rsplit(":", 1)
            if maybe_port.isdigit():
                host = maybe_host
        host = host.strip("[]")
    return host.strip()


def resolve_host_for_region_lookup(host: str) -> str:
    host = normalize_host_value(host)
    if not host:
        return ""
    try:
        socket.inet_pton(socket.AF_INET, host)
        return host
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return host
    except OSError:
        pass
    try:
        info = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        for item in info:
            addr = item[4][0]
            if addr:
                return addr
    except Exception:
        return host
    return host


def lookup_country_code_by_host(host: str, timeout: float = 1.6) -> str:
    ip = resolve_host_for_region_lookup(host)
    if not ip:
        return ""
    if ip in _IP_REGION_CACHE:
        return _IP_REGION_CACHE[ip]
    try:
        url = f"http://ip-api.com/json/{urllib.parse.quote(ip)}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        code = str(data.get("countryCode") or "").strip().upper() if data.get("status") == "success" else ""
    except Exception:
        code = ""
    _IP_REGION_CACHE[ip] = code if len(code) == 2 and code.isalpha() else ""
    return _IP_REGION_CACHE[ip]


def infer_country_code_from_node_name(name: str) -> str:
    text = str(name or "").strip().lower()
    if not text:
        return ""
    for key, code in COUNTRY_NAME_TO_CODE.items():
        if key and key.lower() in text:
            return code
    return ""


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


def node_country_code(node: dict | object, *, allow_lookup: bool = False, allow_name_infer: bool = True) -> str:
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
    if allow_name_infer:
        inferred = infer_country_code_from_node_name(_node_value(node, "name"))
        if inferred:
            return inferred
    if allow_lookup:
        looked_up = lookup_country_code_by_host(_node_value(node, "ip"))
        if looked_up:
            return looked_up
    return ""


def node_flag_emoji(node: dict | object, *, allow_lookup: bool = False, allow_name_infer: bool = True) -> str:
    return country_code_to_flag(node_country_code(node, allow_lookup=allow_lookup, allow_name_infer=allow_name_infer))


def vless_remark_for_node(node: dict | object, fallback_name: str = "", *, allow_lookup: bool = False, allow_name_infer: bool = True) -> str:
    name = _node_value(node, "name") or str(fallback_name or "").strip()
    flag = node_flag_emoji(node, allow_lookup=allow_lookup, allow_name_infer=allow_name_infer)
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
