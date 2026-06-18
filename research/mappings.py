"""Curated US ticker and keyword mappings to China investable themes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import ThemeNode


@dataclass(frozen=True)
class TickerMapping:
    symbol: str
    themes: list[ThemeNode] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


def _node(name: str, *keywords: str, children: list[ThemeNode] | None = None) -> ThemeNode:
    return ThemeNode(name=name, keywords=list(keywords), children=children or [])


THEME_MAPPINGS: dict[str, TickerMapping] = {
    "SPCX": TickerMapping(
        symbol="SPCX",
        keywords=[
            "SPCX",
            "space",
            "commercial space",
            "satellite",
            "rocket",
            "low earth orbit",
            "aerospace",
            "\u822a\u7a7a\u822a\u5929",
            "\u822a\u5929\u822a\u7a7a",
            "\u5546\u4e1a\u822a\u5929",
            "\u901a\u7528\u822a\u7a7a",
            "\u822a\u7a7a\u88c5\u5907",
            "\u822a\u5929\u88c5\u5907",
            "\u536b\u661f\u4e92\u8054\u7f51",
        ],
        themes=[
            _node(
                "commercial space",
                "\u5546\u4e1a\u822a\u5929",
                "\u822a\u5929\u822a\u7a7a",
                "\u536b\u661f\u4e92\u8054\u7f51",
                "satellite",
                "rocket",
            ),
            _node(
                "aerospace equipment",
                "\u822a\u7a7a\u88c5\u5907",
                "\u822a\u5929\u88c5\u5907",
                "\u822a\u7a7a\u822a\u5929",
                "\u822a\u5929\u822a\u7a7a",
            ),
            _node(
                "general aviation",
                "\u901a\u7528\u822a\u7a7a",
                "\u822a\u7a7a\u673a\u573a",
                "\u822a\u7a7a\u8fd0\u8f93",
            ),
        ],
    ),
    "NVDA": TickerMapping(
        symbol="NVDA",
        keywords=[
            "NVIDIA",
            "Blackwell",
            "AI server",
            "AI accelerator",
            "GPU",
            "HBM",
            "CPO",
            "liquid cooling",
            "optical module",
            "PCB",
            "copper clad laminate",
            "advanced packaging",
            "power supply",
            "semiconductor equipment",
            "英伟达",
            "算力",
            "AI服务器",
            "液冷",
            "光模块",
            "高速铜缆",
            "印制电路板",
            "覆铜板",
            "先进封装",
            "半导体设备",
        ],
        themes=[
            _node("AI server", "AI server", "AI服务器", "算力", "GPU"),
            _node("optical module", "optical module", "CPO", "光模块"),
            _node("liquid cooling", "liquid cooling", "液冷", "冷板"),
            _node("PCB", "PCB", "印制电路板", "高速板"),
            _node("copper clad laminate", "CCL", "覆铜板", "铜箔"),
            _node("advanced packaging", "advanced packaging", "先进封装", "CoWoS"),
            _node("semiconductor equipment", "半导体设备", "刻蚀", "薄膜沉积"),
            _node("HBM", "HBM", "高带宽内存", "存储"),
            _node("power supply", "power supply", "电源", "电源模块"),
        ],
    ),
    "TSLA": TickerMapping(
        symbol="TSLA",
        keywords=[
            "Tesla",
            "FSD",
            "robotaxi",
            "Optimus",
            "energy storage",
            "power electronics",
            "特斯拉",
            "自动驾驶",
            "机器人",
            "储能",
            "电驱",
        ],
        themes=[
            _node("FSD", "FSD", "自动驾驶", "智能驾驶"),
            _node("robotics", "Optimus", "机器人", "执行器"),
            _node("energy storage", "储能", "电池"),
            _node("power electronics", "电驱", "逆变器", "功率半导体"),
        ],
    ),
    "ASML": TickerMapping(
        symbol="ASML",
        keywords=["ASML", "lithography", "EUV", "DUV", "光刻机", "半导体设备"],
        themes=[
            _node("lithography chain", "光刻机", "EUV", "DUV"),
            _node("semiconductor equipment", "半导体设备", "量测", "刻蚀"),
            _node("materials", "光刻胶", "掩膜版", "材料"),
        ],
    ),
    "AMD": TickerMapping(
        symbol="AMD",
        keywords=["AMD", "AI GPU", "server CPU", "MI300", "AI服务器", "先进封装"],
        themes=[
            _node("AI GPU", "AI GPU", "MI300", "算力"),
            _node("server", "server CPU", "服务器"),
            _node("advanced packaging", "先进封装", "Chiplet"),
        ],
    ),
    "PLTR": TickerMapping(
        symbol="PLTR",
        keywords=["Palantir", "AI application", "data security", "信创", "数据安全"],
        themes=[
            _node("AI application", "AI应用", "企业AI"),
            _node("data security", "数据安全", "隐私计算"),
            _node("software localization", "信创", "国产软件"),
        ],
    ),
    "LLY": TickerMapping(
        symbol="LLY",
        keywords=["Eli Lilly", "GLP-1", "peptide", "obesity", "减肥药", "多肽"],
        themes=[
            _node("GLP-1", "GLP-1", "减肥药"),
            _node("peptide CDMO", "多肽", "CDMO"),
        ],
    ),
    "NVO": TickerMapping(
        symbol="NVO",
        keywords=["Novo Nordisk", "GLP-1", "semaglutide", "减肥药", "司美格鲁肽"],
        themes=[
            _node("GLP-1", "GLP-1", "司美格鲁肽"),
            _node("peptide CDMO", "多肽", "CDMO"),
        ],
    ),
    "ISRG": TickerMapping(
        symbol="ISRG",
        keywords=["Intuitive Surgical", "surgical robot", "手术机器人", "医疗器械"],
        themes=[
            _node("surgical robot", "手术机器人", "腔镜"),
            _node("high-end medical equipment", "高端医疗器械", "医疗设备"),
        ],
    ),
}

KEYWORD_ALIASES: dict[str, list[str]] = {
    "\u822a\u7a7a\u822a\u5929": [
        "\u822a\u5929\u822a\u7a7a",
        "\u5546\u4e1a\u822a\u5929",
        "\u901a\u7528\u822a\u7a7a",
        "\u822a\u7a7a\u88c5\u5907",
        "\u822a\u5929\u88c5\u5907",
        "\u822a\u7a7a\u673a\u573a",
        "\u822a\u7a7a\u8fd0\u8f93",
        "\u536b\u661f\u4e92\u8054\u7f51",
    ],
    "\u822a\u5929\u822a\u7a7a": [
        "\u822a\u7a7a\u822a\u5929",
        "\u5546\u4e1a\u822a\u5929",
        "\u901a\u7528\u822a\u7a7a",
        "\u822a\u7a7a\u88c5\u5907",
        "\u822a\u5929\u88c5\u5907",
    ],
}


def get_ticker_mapping(symbol: str) -> TickerMapping | None:
    return THEME_MAPPINGS.get(symbol.upper())


def expand_keywords(symbol: str, keywords: list[str] | None = None) -> list[str]:
    mapping = get_ticker_mapping(symbol)
    values: list[str] = []
    if mapping is not None:
        values.extend(mapping.keywords)
        for theme in mapping.themes:
            values.append(theme.name)
            values.extend(theme.keywords)
    values.extend(keywords or [])
    for keyword in keywords or []:
        values.extend(KEYWORD_ALIASES.get(keyword.strip(), []))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def get_theme_tree(symbol: str, keywords: list[str] | None = None) -> list[ThemeNode]:
    mapping = get_ticker_mapping(symbol)
    if mapping is not None:
        return mapping.themes
    return [ThemeNode(name=keyword, keywords=[keyword]) for keyword in keywords or []]


def theme_slug(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text.strip()).strip("-")
    return value.lower() or "theme"
