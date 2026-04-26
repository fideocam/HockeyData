"""Team color helpers for exported Sankey diagrams."""

from __future__ import annotations

import hashlib
import re


# Curated primary colors for common Finnish clubs and national teams.
# Keys are normalized by removing punctuation/spacing and uppercasing.
TEAM_COLORS = {
    # National teams / countries
    "FIN": "#003580",
    "SJL": "#003580",
    "SUOMI": "#003580",
    "SWE": "#005293",
    "CZE": "#11457E",
    "CAN": "#D80621",
    "USA": "#002868",
    "SVK": "#0B4EA2",
    "SUI": "#D52B1E",
    "GER": "#000000",
    "LAT": "#9E3039",
    "DEN": "#C60C30",
    "NOR": "#BA0C2F",
    "AUT": "#ED2939",
    "FRA": "#0055A4",
    "HUN": "#477050",
    "ITA": "#008C45",
    "JPN": "#BC002D",
    "GBR": "#012169",

    # Liiga / Mestis / well-known clubs
    "HIFK": "#E30613",
    "IFK": "#E30613",
    "JOKERIT": "#D71920",
    "KARHU-KISSAT": "#F58220",
    "KKISSAT": "#F58220",
    "K-KISSAT": "#F58220",
    "TPS": "#000000",
    "ILVES": "#00843D",
    "TAPPARA": "#0033A0",
    "HPK": "#F36C21",
    "LUKKO": "#002F6C",
    "ASSAT": "#D71920",
    "ÄSSÄT": "#D71920",
    "JYP": "#C8102E",
    "KALPA": "#FFC72C",
    "KARPAT": "#FFB81C",
    "KÄRPÄT": "#FFB81C",
    "KOOKOO": "#F58220",
    "PELICANS": "#00A3E0",
    "SAIPA": "#FDD023",
    "SPORT": "#C8102E",
    "JUKURIT": "#005EB8",
    "KIEKKO-ESPOO": "#0065BD",
    "KESPOO": "#0065BD",
    "BLUES": "#005EB8",
    "K-VANTAA": "#E87722",
    "KVANTAA": "#E87722",
    "KETTERA": "#00843D",
    "KOO-VEE": "#005EB8",
    "KOOVEE": "#005EB8",
    "TUTO": "#002F6C",
    "HERMES": "#D71920",
    "IPK": "#FDB913",
    "JOKIPOJAT": "#C8102E",
    "ROKI": "#005EB8",
    "KEUPA": "#FDB913",
    "HOKKI": "#005EB8",
    "FPS": "#2E7D32",

    # Junior / regional clubs often seen in exports
    "EVU": "#005EB8",
    "HJK": "#0033A0",
    "HUNTERS": "#007A33",
    "HAUKAT": "#F58220",
    "KIEKKO-TIIKERIT": "#FFB81C",
    "KTIIKERIT": "#FFB81C",
    "K-TIIKERIT": "#FFB81C",
    "KIEKKO-LASER": "#005EB8",
    "K-LASER": "#005EB8",
    "KIEKKO-AHMA": "#F58220",
    "AHMAT": "#F58220",
    "DISKOS": "#C8102E",
    "KIEKKO-POJAT": "#005EB8",
    "KPOJAT": "#005EB8",
    "LEKI": "#005EB8",
    "KJT": "#D71920",
    "KJT-HAUKAT": "#D71920",
    "K-EPS": "#005EB8",
    "KIEKKO-EPS": "#005EB8",
    "KIEKKO-VANTAA": "#E87722",
    "K-VANTAA": "#E87722",
    "KJT HOCKEY": "#D71920",
    "KOO-VEE JUNIORIT": "#005EB8",
    "RNK": "#005EB8",
    "PIRKKALAN PINGVIINIT": "#000000",
    "PINGVIINIT": "#000000",
    "TITAANIT": "#C8102E",
    "PARA": "#005EB8",
    "PAPAS": "#00843D",
    "KIEKKO-KARHUT": "#7A3E00",
    "K-KARHUT": "#7A3E00",
    "APV": "#C8102E",
    "JUNIORI-JUKURIT": "#005EB8",
    "JUNIORI-SAIPA": "#FDD023",
    "JUNIORI-KALPA": "#FFC72C",
    "JUNIORI-PELICANS": "#00A3E0",
    "JUNIORI-HERMES": "#D71920",
    "JUNIORI-JYP": "#C8102E",
    "JUNIORI-KOOKOO": "#F58220",
    "JUNIORI-KARPAT": "#FFB81C",
    "JUNIORI-KÄRPÄT": "#FFB81C",

    # Special nodes
    "UNKNOWN": "#9CA3AF",
    "OUTOFSPORT": "#6B7280",
    "OUT-OF-SPORT": "#6B7280",
    "STAYEDLEFTGAME": "#6B7280",
}
_NORMALIZED_TEAM_COLORS: dict[str, str] | None = None

FALLBACK_PALETTE = [
    "#2563EB",
    "#DC2626",
    "#16A34A",
    "#D97706",
    "#7C3AED",
    "#0891B2",
    "#DB2777",
    "#65A30D",
    "#EA580C",
    "#4F46E5",
]


def normalize_team(value: str) -> str:
    text = (value or "").upper()
    text = text.replace("Ä", "A").replace("Ö", "O").replace("Å", "A")
    text = re.sub(r"\b(RY|OY|JUNIORIT|JUNIORI|MIEHET|NAISET|U\d+|N\d+|RED|BLUE|WHITE|BLACK|MUSTA|VALKOINEN|PUNAINEN|SININEN)\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text


def _candidate_keys(team: str) -> list[str]:
    raw = (team or "").strip()
    base = raw.split(" · ")[-1].strip()
    first_token = re.split(r"\s+", base, maxsplit=1)[0] if base else ""
    candidates = [
        raw,
        base,
        first_token,
        base.replace(" ", "-"),
        base.replace("-", " "),
    ]
    return [normalize_team(candidate) for candidate in candidates if candidate]


def _fallback_color(team: str) -> str:
    digest = hashlib.sha1((team or "team").encode("utf-8")).hexdigest()
    return FALLBACK_PALETTE[int(digest[:8], 16) % len(FALLBACK_PALETTE)]


def team_color(team: str) -> str:
    global _NORMALIZED_TEAM_COLORS
    if _NORMALIZED_TEAM_COLORS is None:
        _NORMALIZED_TEAM_COLORS = {normalize_team(key): value for key, value in TEAM_COLORS.items()}
    for key in _candidate_keys(team):
        if key in _NORMALIZED_TEAM_COLORS:
            return _NORMALIZED_TEAM_COLORS[key]
    return _fallback_color(team)


def hex_to_rgba(color: str, alpha: float) -> str:
    value = color.lstrip("#")
    if len(value) != 6:
        return f"rgba(74,144,217,{alpha})"
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
