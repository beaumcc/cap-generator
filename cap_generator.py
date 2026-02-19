#!/usr/bin/env python3
# cap_generator.py
# Generate .CAP files from season stat XML files.
#
# DISCLAIMER: This code was generated with AI assistance (Claude).
# This software is provided "as is" without warranty of any kind. The author(s)
# claim no ownership rights and grant no rights to users. Use at your own risk.
# No liability for incorrect, incomplete, or corrupted data, nor for any data loss.
# See LICENSE for full terms.
#
#
# Progress display:
#   - Prints [i/N] status for each XML processed
#
# Header: 292 bytes (team name/id/date + dynamic tail built from XML totals/opponent)
# Body:   N * 216-byte player records (N = number of <player> nodes)
#
# Player record (216 bytes):
#   [0:8]    team id (ASCII, space padded)
#   [8]      0x00
#   [9:21]   player name (12 bytes) ->
#   [21]     0x00
#   [22]     0x20
#   [23]     
#   [24:216] 96 * uint16 little-endian stats

import sys
import struct
from typing import NamedTuple, Callable
from pathlib import Path
import xml.etree.ElementTree as ET

HEADER_SIZE = 292
REC_SIZE = 216

U16_START = 0x18
U16_COUNT = 96
U16_STRUCT_FMT = "<" + "H" * U16_COUNT
REC_TEMPLATE = b"\x00" * REC_SIZE

# u16 index mapping (everything else stays 0)
MAP_U16 = {
    # core batting counts
    "gp": 0, "gs": 1,
    "ab": 2, "r": 3, "h": 4, "rbi": 5,
    "double": 6, "triple": 7, "hr": 8,
    "bb": 9, "sb": 10, "hbp": 12,
    "cs": 11, "sh": 13, "sf": 14,
    "so": 16, "kl": 17, "gdp": 18, "hitdp": 19,

    # missing hitting stats
    "ibb": 21,       # intentional walks
    "picked": 26,    # picked off

    # fielding
    "po": 27, "a": 28, "e": 29, "pb": 30, "indp": 31, "csb": 33,
    "sba": 34,
    "ci": 35,        # catcher's interference (from fielding element)

    # hitting situation summary
    "rcherr": 22, "rchfc": 23, "ground": 24, "fly": 25,
    "adv": 79, "lob": 80,

    # pair fields (made/opp)
    "w2outs_opp": 67, "w2outs_made": 68,
    "wrunners_opp": 69, "wrunners_made": 70,
    "wrbiops_opp": 71, "wrbiops_made": 72,
    "vsleft_opp": 73, "vsleft_made": 74,
    "rbi3rd_opp": 75, "rbi3rd_made": 76,
    "advops_opp": 77, "advops_made": 78,
    "leadoff_opp": 81, "leadoff_made": 82,
    "pinchhit_opp": 83, "pinchhit_made": 84,

    "rbi_2out": 85,

    "wloaded_opp": 92, "wloaded_made": 93,
}

# Opponent-specific indices for pitching stats and psitsummary
MAP_U16_OPPONENT = {
    # hitting (duplicate at different index)
    "h_sh": 26,  # sh duplicate in opponent record
    # pitching stats
    "p_appear": 36,
    "p_win": 37,      # stores pitching.gs (games started) / appear for opponent record
    "p_loss": 38,     # stores pitching.gf (games finished)
    "p_cg": 39,       # stores pitching.cg (complete games)
    "p_sho_raw": 40,  # stores pitching.sho (shutouts)
    "p_sho": 41,      # stores pitching.cbo (combined shutouts)
    "p_bf": 42,
    "p_ab": 43,
    "p_2b": 44,       # stores pitching.win (actual wins)
    "p_loss2": 45,    # duplicate of gf
    "p_save": 46,     # stores pitching.save
    "p_ip_outs": 47,  # ip * 3
    "p_h": 48,
    "p_r": 49,
    "p_er": 50,
    "p_bb": 51,
    "p_k": 52,
    "p_kl": 53,
    "p_wp": 54,       # stores pitching.wp (wild pitches)
    "p_bk": 55,       # stores pitching.bk (balks)
    "p_hbp": 56,
    "p_wp_shifted": 57,  # wp * 256 (stored in high byte)
    "p_double": 58,
    "p_triple": 59,   # stores pitching.triple (triples allowed)
    "p_hr": 60,
    # psitsummary
    "ps_ground": 61,
    "ps_fly": 62,
    "p_pickoff": 63,  # stores psitsummary.picked (pitcher pickoffs)
    "p_sha": 65,      # sacrifice hits allowed
    "p_sfa": 66,      # sacrifice flies allowed
    "ps_leadoff_opp": 86,
    "ps_leadoff_made": 87,
    "ps_wrunners_opp": 88,
    "ps_wrunners_made": 89,
    "ps_vsleft_opp": 90,
    "ps_vsleft_made": 91,
    "ps_w2outs_opp": 94,
    "ps_w2outs_made": 95,
}

PTYPE_HITTER = 3
PTYPE_PITCHER = 1

# Class year base values for byte 22 (high bits)
# Covers TAS (class="FR") and PrestoSports (year="Fr." / "R-Fr." / "Gr.") formats
CLASS_BYTE = {
    "FR": 0x08, "SO": 0x10, "JR": 0x20, "SR": 0x40,
    "FR.": 0x08, "SO.": 0x10, "JR.": 0x20, "SR.": 0x40,
    "FRESHMAN": 0x08, "SOPHOMORE": 0x10, "JUNIOR": 0x20, "SENIOR": 0x40,
    "R-FR": 0x08, "R-SO": 0x10, "R-JR": 0x20, "R-SR": 0x40,
    "R-FR.": 0x08, "R-SO.": 0x10, "R-JR.": 0x20, "R-SR.": 0x40,
    "GR": 0x40, "GR.": 0x40, "GRADUATE": 0x40, "GRAD": 0x40,
}

# Bats/throws encoding for low bits of byte 22
# bit 0 = bats left, bit 1 = throws left, bit 2 = switch hitter
HANDS_BITS = {
    ("R", "R"): 0x00,
    ("L", "R"): 0x01,
    ("R", "L"): 0x02,
    ("L", "L"): 0x03,
    ("B", "R"): 0x04,
    ("B", "L"): 0x06,
}


# ---------------------------------------------------------------------------
# Format-specific dispatch
# ---------------------------------------------------------------------------

class FormatHandler(NamedTuple):
    is_pitcher: Callable[[ET.Element], bool]
    games_finished: Callable[[ET.Element], int]
    opponent_appear: Callable[[ET.Element, ET.Element | None], int]
    player_appeared: Callable[[ET.Element], bool]
    player_class: Callable[[ET.Element], str]
    player_hands: Callable[[ET.Element], int]


# -- pitcher detection --

def _is_pitcher_tas(p: ET.Element) -> bool:
    pos = (p.get("pos") or p.get("position") or "").strip().upper()
    return pos in ("P", "RHP", "LHP")


def _is_pitcher_presto(p: ET.Element) -> bool:
    pitching = p.find("pitching")
    return pitching is not None and int(pitching.get("appear") or 0) > 0


# -- games finished --

def _games_finished_tas(pitching: ET.Element) -> int:
    return int(pitching.get("gf") or 0)


def _games_finished_presto(pitching: ET.Element) -> int:
    return max(0, int(pitching.get("appear") or 0) - int(pitching.get("gs") or 0))


# -- opponent appear --

def _opponent_appear_tas(pitching: ET.Element, totals: ET.Element | None) -> int:
    return int(pitching.get("appear") or 0)


def _opponent_appear_presto(pitching: ET.Element, totals: ET.Element | None) -> int:
    return int(totals.get("gp") or 0) if totals is not None else 0


# -- player appeared (filter for active roster) --

def _player_appeared_tas(p: ET.Element) -> bool:
    return int(p.get("gp") or 0) > 0


def _player_appeared_presto(p: ET.Element) -> bool:
    if int(p.get("gp") or 0) > 0:
        return True
    pit = p.find("pitching")
    return pit is not None and int(pit.get("appear") or 0) > 0


# -- player class/year --

def _player_class_tas(p: ET.Element) -> str:
    return (p.get("class") or "").strip()


def _player_class_presto(p: ET.Element) -> str:
    return (p.get("year") or "").strip()


# -- player bats/throws handedness --

def _player_hands_tas(p: ET.Element) -> int:
    bats = (p.get("bats") or "R").strip().upper()
    throws = (p.get("throws") or "R").strip().upper()
    return HANDS_BITS.get((bats, throws), 0x00)


def _player_hands_presto(p: ET.Element) -> int:
    return 0x00  # PrestoSports has no bats/throws data; default R/R


TAS_HANDLER = FormatHandler(
    is_pitcher=_is_pitcher_tas,
    games_finished=_games_finished_tas,
    opponent_appear=_opponent_appear_tas,
    player_appeared=_player_appeared_tas,
    player_class=_player_class_tas,
    player_hands=_player_hands_tas,
)

PRESTO_HANDLER = FormatHandler(
    is_pitcher=_is_pitcher_presto,
    games_finished=_games_finished_presto,
    opponent_appear=_opponent_appear_presto,
    player_appeared=_player_appeared_presto,
    player_class=_player_class_presto,
    player_hands=_player_hands_presto,
)


def detect_format(root: ET.Element) -> FormatHandler:
    source = (root.get("source") or "").strip()
    if "PrestoSports" in source:
        return PRESTO_HANDLER
    return TAS_HANDLER


def pad_ascii(s: str, n: int) -> bytes:
    b = (s or "").encode("ascii", errors="ignore")[:n]
    return b + (b" " * (n - len(b)))


def clamp_u16(x) -> int:
    try:
        v = int(x)
    except Exception:
        return 0
    if v < 0:
        return 0
    if v > 65535:
        return 65535
    return v


def mmddyy_from_xml_date(date_str: str) -> str:
    # Tolerates "2/15/2026", "02/15/2026", "02/15/26"
    parts = (date_str or "").strip().split("/")
    if len(parts) != 3:
        return "01/01/00"
    m = int(parts[0])
    d = int(parts[1])
    y = int(parts[2])
    yy = y if y < 100 else (y % 100)
    return f"{m:02d}/{d:02d}/{yy:02d}"


def parse_pair(v: str) -> tuple[int, int]:
    # "made,opp"
    if not v:
        return (0, 0)
    parts = [p.strip() for p in v.split(",")]
    try:
        if len(parts) >= 2:
            return (int(parts[0]), int(parts[1]))
        return (int(parts[0]), 0)
    except ValueError:
        return (0, 0)


def _set_opp_stat(u16: list[int], field: str, value: int) -> None:
    """Set opponent-specific stat using MAP_U16_OPPONENT."""
    if value and (idx := MAP_U16_OPPONENT.get(field)) is not None:
        u16[idx] = clamp_u16(value)


def _parse_ip_to_outs(ip_str: str) -> int:
    """Convert IP string like '22.0' or '3.2' to total outs."""
    if not ip_str:
        return 0
    try:
        parts = ip_str.split(".")
        innings = int(parts[0])
        partial = int(parts[1]) if len(parts) > 1 else 0
        return innings * 3 + partial
    except (ValueError, IndexError):
        return 0


def _get_int(elem: ET.Element | None, key: str) -> int:
    if elem is None:
        return 0
    v = elem.get(key)
    if v is None:
        return 0
    try:
        return int(v)
    except ValueError:
        return 0


def _set_stat(u16: list[int], field: str, value: int) -> None:
    if value and (idx := MAP_U16.get(field)) is not None:
        u16[idx] = clamp_u16(value)


def _set_pair(u16: list[int], hs: ET.Element, xml_key: str, made_key: str, opp_key: str) -> None:
    made, opp = parse_pair(hs.get(xml_key) or "")
    if made and (idx := MAP_U16.get(made_key)) is not None:
        u16[idx] = clamp_u16(made)
    if opp and (idx := MAP_U16.get(opp_key)) is not None:
        u16[idx] = clamp_u16(opp)


def stats_from_opponent_elem(opponent: ET.Element | None, totals: ET.Element | None, fmt: FormatHandler) -> list[int]:
    """Extract stats from <opponent> element using MAP_U16 indices plus opponent-specific mappings."""
    u16 = [0] * U16_COUNT

    # gp/gs come from totals (opponent record shows team's games played)
    if totals is not None:
        _set_stat(u16, "gp", int(totals.get("gp") or 0))
        _set_stat(u16, "gs", int(totals.get("gp") or 0))  # gs = gp for opponent

    if opponent is None:
        return u16

    hitting = opponent.find("hitting")
    fielding = opponent.find("fielding")
    hs = opponent.find("hsitsummary")
    pitching = opponent.find("pitching")
    ps = opponent.find("psitsummary")

    # hitting
    _set_stat(u16, "ab", _get_int(hitting, "ab"))
    _set_stat(u16, "r", _get_int(hitting, "r"))
    _set_stat(u16, "h", _get_int(hitting, "h"))
    _set_stat(u16, "rbi", _get_int(hitting, "rbi"))
    _set_stat(u16, "double", _get_int(hitting, "double"))
    _set_stat(u16, "triple", _get_int(hitting, "triple"))
    _set_stat(u16, "hr", _get_int(hitting, "hr"))
    _set_stat(u16, "bb", _get_int(hitting, "bb"))
    _set_stat(u16, "sb", _get_int(hitting, "sb"))
    _set_stat(u16, "cs", _get_int(hitting, "cs"))
    _set_stat(u16, "hbp", _get_int(hitting, "hbp"))
    _set_stat(u16, "sh", _get_int(hitting, "sh"))
    _set_stat(u16, "sf", _get_int(hitting, "sf"))
    _set_stat(u16, "so", _get_int(hitting, "so"))
    _set_stat(u16, "kl", _get_int(hitting, "kl"))
    _set_stat(u16, "gdp", _get_int(hitting, "gdp"))
    _set_stat(u16, "hitdp", _get_int(hitting, "hitdp"))
    _set_stat(u16, "ibb", _get_int(hitting, "ibb"))
    _set_opp_stat(u16, "h_sh", _get_int(hitting, "sh"))  # sh at alternate index 26

    # fielding
    _set_stat(u16, "po", _get_int(fielding, "po"))
    _set_stat(u16, "a", _get_int(fielding, "a"))
    _set_stat(u16, "e", _get_int(fielding, "e"))
    _set_stat(u16, "pb", _get_int(fielding, "pb"))
    _set_stat(u16, "indp", _get_int(fielding, "indp"))
    _set_stat(u16, "csb", _get_int(fielding, "csb"))
    _set_stat(u16, "sba", _get_int(fielding, "sba"))
    _set_stat(u16, "ci", _get_int(fielding, "ci"))

    # hsitsummary
    _set_stat(u16, "rcherr", _get_int(hs, "rcherr"))
    _set_stat(u16, "rchfc", _get_int(hs, "rchfc"))
    _set_stat(u16, "ground", _get_int(hs, "ground"))
    _set_stat(u16, "fly", _get_int(hs, "fly"))
    _set_stat(u16, "adv", _get_int(hs, "adv"))
    _set_stat(u16, "lob", _get_int(hs, "lob"))

    if hs is not None:
        _set_pair(u16, hs, "w2outs", "w2outs_made", "w2outs_opp")
        _set_pair(u16, hs, "wrunners", "wrunners_made", "wrunners_opp")
        _set_pair(u16, hs, "wrbiops", "wrbiops_made", "wrbiops_opp")
        _set_pair(u16, hs, "vsleft", "vsleft_made", "vsleft_opp")
        _set_pair(u16, hs, "rbi3rd", "rbi3rd_made", "rbi3rd_opp")
        _set_pair(u16, hs, "advops", "advops_made", "advops_opp")
        _set_pair(u16, hs, "leadoff", "leadoff_made", "leadoff_opp")
        _set_pair(u16, hs, "wloaded", "wloaded_made", "wloaded_opp")
        _set_pair(u16, hs, "pinchhit", "pinchhit_made", "pinchhit_opp")
        _set_stat(u16, "rbi_2out", int(hs.get("rbi-2out") or 0))

    # pitching (opponent-specific indices)
    if pitching is not None:
        appear = fmt.opponent_appear(pitching, totals)
        _set_opp_stat(u16, "p_appear", appear)
        _set_opp_stat(u16, "p_win", appear)   # appear stored at idx37 for opponent
        _set_opp_stat(u16, "p_loss", _get_int(pitching, "loss"))
        _set_opp_stat(u16, "p_cg", _get_int(pitching, "cg"))
        _set_opp_stat(u16, "p_sho_raw", _get_int(pitching, "sho"))
        _set_opp_stat(u16, "p_sho", _get_int(pitching, "cbo"))
        _set_opp_stat(u16, "p_bf", _get_int(pitching, "bf"))
        _set_opp_stat(u16, "p_ab", _get_int(pitching, "ab"))
        _set_opp_stat(u16, "p_2b", _get_int(pitching, "win"))       # actual wins at idx44
        _set_opp_stat(u16, "p_loss2", _get_int(pitching, "loss"))
        _set_opp_stat(u16, "p_save", _get_int(pitching, "save"))
        _set_opp_stat(u16, "p_ip_outs", _parse_ip_to_outs(pitching.get("ip") or ""))
        _set_opp_stat(u16, "p_h", _get_int(pitching, "h"))
        _set_opp_stat(u16, "p_r", _get_int(pitching, "r"))
        _set_opp_stat(u16, "p_er", _get_int(pitching, "er"))
        _set_opp_stat(u16, "p_bb", _get_int(pitching, "bb"))
        _set_opp_stat(u16, "p_k", _get_int(pitching, "k"))
        _set_opp_stat(u16, "p_kl", _get_int(pitching, "kl"))
        _set_opp_stat(u16, "p_gdp", _get_int(pitching, "gdp"))
        _set_opp_stat(u16, "p_hbp", _get_int(pitching, "hbp"))

        # wp stored at idx54 (plain) and idx57 (shifted left 8 bits / high byte)
        wp = _get_int(pitching, "wp")
        _set_opp_stat(u16, "p_wp", wp)
        if wp and (idx := MAP_U16_OPPONENT.get("p_wp_shifted")) is not None:
            u16[idx] = clamp_u16(wp * 256)

        _set_opp_stat(u16, "p_bk", _get_int(pitching, "bk"))
        _set_opp_stat(u16, "p_double", _get_int(pitching, "double"))
        _set_opp_stat(u16, "p_triple", _get_int(pitching, "triple"))
        _set_opp_stat(u16, "p_hr", _get_int(pitching, "hr"))
        _set_opp_stat(u16, "p_sha", _get_int(pitching, "sha"))
        _set_opp_stat(u16, "p_sfa", _get_int(pitching, "sfa"))

    # psitsummary (opponent-specific indices)
    if ps is not None:
        _set_opp_stat(u16, "p_pickoff", _get_int(ps, "picked"))
        _set_opp_stat(u16, "ps_ground", _get_int(ps, "ground"))
        _set_opp_stat(u16, "ps_fly", _get_int(ps, "fly"))

        made, opp = parse_pair(ps.get("leadoff") or "")
        _set_opp_stat(u16, "ps_leadoff_opp", opp)
        _set_opp_stat(u16, "ps_leadoff_made", made)

        made, opp = parse_pair(ps.get("wrunners") or "")
        _set_opp_stat(u16, "ps_wrunners_opp", opp)
        _set_opp_stat(u16, "ps_wrunners_made", made)

        made, opp = parse_pair(ps.get("vsleft") or "")
        _set_opp_stat(u16, "ps_vsleft_opp", opp)
        _set_opp_stat(u16, "ps_vsleft_made", made)

        made, opp = parse_pair(ps.get("w2outs") or "")
        _set_opp_stat(u16, "ps_w2outs_opp", opp)
        _set_opp_stat(u16, "ps_w2outs_made", made)

    return u16


def build_header(
    team_name: str,
    team_id: str,
    mmddyy: str,
    player_count: int,
    totals: ET.Element | None,
    opponent: ET.Element | None,
    team: ET.Element | None = None,
    rec_size: int = REC_SIZE,
    fmt: FormatHandler = TAS_HANDLER,
) -> bytes:
    """
    Build 292-byte header including opponent pseudo-record.

    Layout:
      [0:20]   team name
      [21:29]  team id
      [30:38]  date MM/DD/YY
      [40:76]  metadata (player count, record size, wins/losses, conf record, fielding/pitching totals)
      [76:100] opponent record header ("Opponents", type=0x78)
      [100:292] opponent stats (96 u16 values)
    """
    h = bytearray(HEADER_SIZE)

    # Team info [0:40]
    h[0:20] = pad_ascii(team_name, 20)
    h[21:29] = pad_ascii(team_id, 8)
    h[30:38] = pad_ascii(mmddyy, 8)

    # Metadata [40:76]
    struct.pack_into("<H", h, 40, player_count)
    struct.pack_into("<H", h, 42, rec_size)
    struct.pack_into("<H", h, 44, int(totals.get("w") or 0) if totals is not None else 0)
    struct.pack_into("<H", h, 46, int(totals.get("l") or 0) if totals is not None else 0)

    # Conference record from team.confonly (e.g. "16-14-0")
    if team is not None:
        confonly = (team.get("confonly") or "").strip()
        if confonly:
            parts = confonly.split("-")
            if len(parts) >= 2:
                try:
                    struct.pack_into("<H", h, 50, int(parts[0]))
                    struct.pack_into("<H", h, 52, int(parts[1]))
                except ValueError:
                    pass

    totals_fielding = totals.find("fielding") if totals is not None else None
    if totals_fielding is not None:
        struct.pack_into("<H", h, 56, int(totals_fielding.get("indp") or 0))
        struct.pack_into("<H", h, 60, int(totals_fielding.get("sba") or 0))
        struct.pack_into("<H", h, 62, int(totals_fielding.get("csb") or 0))

    totals_pitching = totals.find("pitching") if totals is not None else None
    if totals_pitching is not None:
        struct.pack_into("<H", h, 64, int(totals_pitching.get("sho") or 0))
        struct.pack_into("<H", h, 66, int(totals_pitching.get("cbo") or 0))

    # Opponent pseudo-record header [76:100]
    h[76:84] = b"        "  # empty team id
    h[85:97] = pad_ascii("Opponents", 12)
    h[98] = 0x78  # opponent type flag

    # Opponent stats [100:292]
    opp_stats = stats_from_opponent_elem(opponent, totals, fmt)
    h[100:292] = struct.pack(U16_STRUCT_FMT, *opp_stats)

    return bytes(h)


def format_name(p: ET.Element) -> str:
    """Return player name as 'F. Lastname' fitted within 12 chars.

    Uses checkname (format "LASTNAME,FIRSTNAME" or "LASTNAME,FIRSTNAME MIDDLE")
    to identify first vs last name tokens. Handles double first names
    (Jake Henry Williams -> J. Williams), compound last names
    (Jelle van der Lelie -> J.van der Le), and long last names where the
    space after the dot is dropped to fit (Will McCausland -> W.McCausland).

    Fitting order (first <= 12 chars wins):
      1. "F. {last}"  with space
      2. "F.{last}"   without space
      3. truncate option 2 to 12 chars
    """
    v = (p.get("name") or "").strip()
    if not v:
        raise RuntimeError("player missing required @name attribute")
    tokens = v.split()
    if len(tokens) == 1:
        return tokens[0][:12]
    checkname = (p.get("checkname") or "").strip()
    if checkname and "," in checkname:
        first_ck = checkname.split(",", 1)[1].strip()
        first_token_count = max(1, len(first_ck.split()))
    else:
        first_token_count = 1
    initial = tokens[0][0].upper()
    last_tokens = tokens[first_token_count:] or tokens[1:]
    last = " ".join(last_tokens)
    for candidate in (f"{initial}. {last}", f"{initial}.{last}"):
        if len(candidate) <= 12:
            return candidate
    return f"{initial}.{last}"[:12]


def stats_from_player_elem(p: ET.Element, pitcher: bool, fmt: FormatHandler) -> list[int]:
    u16 = [0] * U16_COUNT

    hitting = p.find("hitting")
    fielding = p.find("fielding")
    hs = p.find("hsitsummary")
    pitching = p.find("pitching")

    # gp/gs: position players use XML values; pitchers always get 0/0
    if not pitcher:
        _set_stat(u16, "gp", int(p.get("gp") or 0))
        _set_stat(u16, "gs", int(p.get("gs") or 0))

    # hitting
    _set_stat(u16, "ab", _get_int(hitting, "ab"))
    _set_stat(u16, "r", _get_int(hitting, "r"))
    _set_stat(u16, "h", _get_int(hitting, "h"))
    _set_stat(u16, "rbi", _get_int(hitting, "rbi"))
    _set_stat(u16, "double", _get_int(hitting, "double"))
    _set_stat(u16, "triple", _get_int(hitting, "triple"))
    _set_stat(u16, "hr", _get_int(hitting, "hr"))
    _set_stat(u16, "bb", _get_int(hitting, "bb"))
    _set_stat(u16, "sb", _get_int(hitting, "sb"))
    _set_stat(u16, "cs", _get_int(hitting, "cs"))
    _set_stat(u16, "hbp", _get_int(hitting, "hbp"))
    _set_stat(u16, "sh", _get_int(hitting, "sh"))
    _set_stat(u16, "sf", _get_int(hitting, "sf"))
    _set_stat(u16, "so", _get_int(hitting, "so"))
    _set_stat(u16, "kl", _get_int(hitting, "kl"))
    _set_stat(u16, "gdp", _get_int(hitting, "gdp"))
    _set_stat(u16, "hitdp", _get_int(hitting, "hitdp"))
    _set_stat(u16, "ibb", _get_int(hitting, "ibb"))
    _set_stat(u16, "picked", _get_int(hitting, "picked"))

    # fielding
    _set_stat(u16, "po", _get_int(fielding, "po"))
    _set_stat(u16, "a", _get_int(fielding, "a"))
    _set_stat(u16, "e", _get_int(fielding, "e"))
    _set_stat(u16, "pb", _get_int(fielding, "pb"))
    _set_stat(u16, "indp", _get_int(fielding, "indp"))
    _set_stat(u16, "csb", _get_int(fielding, "csb"))
    _set_stat(u16, "sba", _get_int(fielding, "sba"))
    _set_stat(u16, "ci", _get_int(fielding, "ci"))

    # hsitsummary
    _set_stat(u16, "rcherr", _get_int(hs, "rcherr"))
    _set_stat(u16, "rchfc", _get_int(hs, "rchfc"))
    _set_stat(u16, "ground", _get_int(hs, "ground"))
    _set_stat(u16, "fly", _get_int(hs, "fly"))
    _set_stat(u16, "adv", _get_int(hs, "adv"))
    _set_stat(u16, "lob", _get_int(hs, "lob"))

    if hs is not None:
        _set_pair(u16, hs, "w2outs", "w2outs_made", "w2outs_opp")
        _set_pair(u16, hs, "wrunners", "wrunners_made", "wrunners_opp")
        _set_pair(u16, hs, "wrbiops", "wrbiops_made", "wrbiops_opp")
        _set_pair(u16, hs, "vsleft", "vsleft_made", "vsleft_opp")
        _set_pair(u16, hs, "rbi3rd", "rbi3rd_made", "rbi3rd_opp")
        _set_pair(u16, hs, "advops", "advops_made", "advops_opp")
        _set_pair(u16, hs, "leadoff", "leadoff_made", "leadoff_opp")
        _set_pair(u16, hs, "wloaded", "wloaded_made", "wloaded_opp")
        _set_pair(u16, hs, "pinchhit", "pinchhit_made", "pinchhit_opp")
        _set_stat(u16, "rbi_2out", int(hs.get("rbi-2out") or 0))

    # pitching stats (pitcher records only, same indices as opponent mapping)
    if pitcher and pitching is not None:
        _set_opp_stat(u16, "p_appear", _get_int(pitching, "appear"))
        _set_opp_stat(u16, "p_win", _get_int(pitching, "gs"))    # gs not win
        gf = fmt.games_finished(pitching)
        _set_opp_stat(u16, "p_loss", gf)
        _set_opp_stat(u16, "p_sho", _get_int(pitching, "cbo"))   # cbo not sho
        _set_opp_stat(u16, "p_2b", _get_int(pitching, "win"))    # actual wins
        _set_opp_stat(u16, "p_save", _get_int(pitching, "save"))
        _set_opp_stat(u16, "p_wp", _get_int(pitching, "wp"))
        _set_opp_stat(u16, "p_bk", _get_int(pitching, "bk"))
        _set_opp_stat(u16, "p_triple", _get_int(pitching, "triple"))
        _set_opp_stat(u16, "p_bf", _get_int(pitching, "bf"))
        _set_opp_stat(u16, "p_ab", _get_int(pitching, "ab"))
        _set_opp_stat(u16, "p_loss2", _get_int(pitching, "loss"))
        _set_opp_stat(u16, "p_ip_outs", _parse_ip_to_outs(pitching.get("ip") or ""))
        _set_opp_stat(u16, "p_h", _get_int(pitching, "h"))
        _set_opp_stat(u16, "p_r", _get_int(pitching, "r"))
        _set_opp_stat(u16, "p_er", _get_int(pitching, "er"))
        _set_opp_stat(u16, "p_bb", _get_int(pitching, "bb"))
        _set_opp_stat(u16, "p_k", _get_int(pitching, "k"))
        _set_opp_stat(u16, "p_kl", _get_int(pitching, "kl"))
        _set_opp_stat(u16, "p_gdp", _get_int(pitching, "gdp"))
        _set_opp_stat(u16, "p_hbp", _get_int(pitching, "hbp"))
        wp = _get_int(pitching, "wp")
        if wp and (idx := MAP_U16_OPPONENT.get("p_wp_shifted")) is not None:
            u16[idx] = clamp_u16(wp * 256)
        _set_opp_stat(u16, "p_double", _get_int(pitching, "double"))
        _set_opp_stat(u16, "p_hr", _get_int(pitching, "hr"))
        _set_opp_stat(u16, "p_sha", _get_int(pitching, "sha"))
        _set_opp_stat(u16, "p_sfa", _get_int(pitching, "sfa"))

        ps = p.find("psitsummary")
        if ps is not None:
            _set_opp_stat(u16, "p_pickoff", _get_int(ps, "picked"))
            _set_opp_stat(u16, "ps_ground", _get_int(ps, "ground"))
            _set_opp_stat(u16, "ps_fly", _get_int(ps, "fly"))
            made, opp = parse_pair(ps.get("leadoff") or "")
            _set_opp_stat(u16, "ps_leadoff_opp", opp)
            _set_opp_stat(u16, "ps_leadoff_made", made)
            made, opp = parse_pair(ps.get("wrunners") or "")
            _set_opp_stat(u16, "ps_wrunners_opp", opp)
            _set_opp_stat(u16, "ps_wrunners_made", made)
            made, opp = parse_pair(ps.get("vsleft") or "")
            _set_opp_stat(u16, "ps_vsleft_opp", opp)
            _set_opp_stat(u16, "ps_vsleft_made", made)
            made, opp = parse_pair(ps.get("w2outs") or "")
            _set_opp_stat(u16, "ps_w2outs_opp", opp)
            _set_opp_stat(u16, "ps_w2outs_made", made)

    return u16


def pack_player_record(team_id: str, name: str, pitcher: bool, u16_stats: list[int], player_class: str = "", type_byte: int | None = None, hands_bits: int = 0x00) -> bytes:
    # Layout: team_id(8) + \x00 + name(12, space-padded) + \x00 + class(1) + type(1) + stats(192)
    # Byte 22 encodes class year (high bits) | bats/throws handedness (low bits)
    # type_byte: supply team_gp for season files (b23 tracks last-game appearance).
    #            Defaults to pitcher/hitter flag (1/3) if not supplied.
    name_bytes = name.encode("ascii", errors="ignore")[:12]
    name_padded = name_bytes + b" " * (12 - len(name_bytes))
    class_byte = CLASS_BYTE.get(player_class.upper(), 0x20) | hands_bits
    if type_byte is None:
        type_byte = PTYPE_PITCHER if pitcher else PTYPE_HITTER
    rec = bytearray()
    rec += pad_ascii(team_id, 8)
    rec += b"\x00"
    rec += name_padded
    rec += b"\x00"
    rec += bytes([class_byte])
    rec += bytes([type_byte])
    rec += struct.pack(U16_STRUCT_FMT, *u16_stats)
    return bytes(rec)


def generate_cap(xml_path: Path) -> Path:
    root = ET.parse(xml_path).getroot()
    fmt = detect_format(root)

    cap_date = mmddyy_from_xml_date(root.get("date") or "")

    team = root.find(".//team")
    if team is None:
        raise RuntimeError("XML missing <team ...> element")

    team_name = (team.get("name") or "").strip()
    team_id = (team.get("id") or "").strip()
    if not team_id:
        # Fall back to XML filename (without extension) as team ID
        team_id = xml_path.stem
    if not team_name:
        raise RuntimeError("XML team element missing required name attribute")

    players = [p for p in root.findall(".//player") if fmt.player_appeared(p)]
    players.sort(key=lambda p: int(p.get("uni") or 999))

    totals = root.find(".//totals")
    opponent = root.find(".//opponent")

    recs = []
    names = [format_name(p) for p in players]
    header = build_header(team_name, team_id, cap_date, len(players), totals, opponent, team, REC_SIZE, fmt)

    team_gp = int(totals.get("gp") or 0) if totals is not None else 0

    for p, nm in zip(players, names):
        pit = fmt.is_pitcher(p)
        u16 = stats_from_player_elem(p, pit, fmt)
        player_class = fmt.player_class(p)
        hands_bits = fmt.player_hands(p)
        recs.append(pack_player_record(team_id, nm, pit, u16, player_class, team_gp, hands_bits))

    out_path = xml_path.with_suffix(".cap")
    out_path.write_bytes(header + b"".join(recs))
    return out_path


def _collect_xml_targets(argv: list[str]) -> list[Path]:
    """
    Drag-and-drop support:
    - If user drags one or more .xml onto the exe, Windows passes them as argv.
    - Also supports directories: if a dir is provided, process *.xml inside it.
    - If no argv targets, fall back to scanning current directory (original behavior).
    """
    if not argv:
        cwd = Path.cwd()
        return sorted([*cwd.glob("*.xml"), *cwd.glob("*.XML")])

    out: list[Path] = []
    for a in argv:
        p = Path(a)
        if p.is_dir():
            out.extend([*p.glob("*.xml"), *p.glob("*.XML")])
        else:
            if p.suffix.lower() == ".xml":
                out.append(p)

    uniq = sorted({p.resolve() for p in out})
    return uniq


def main() -> int:
    xmls = _collect_xml_targets(sys.argv[1:])
    if not xmls:
        print("No XML files found.")
        print("Tip: drag-and-drop one or more .xml files (or folders) onto cap_generator.exe")
        return 1

    total = len(xmls)
    failures = 0

    for i, x in enumerate(xmls, start=1):
        try:
            print(f"[{i}/{total}] Processing {x.name}...", flush=True)
            out = generate_cap(x)
            print(f"[{i}/{total}] OK  {x.name} -> {out.name} ({out.stat().st_size} bytes)")
        except Exception as e:
            failures += 1
            print(f"[{i}/{total}] FAIL {x.name}: {e}")

    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())