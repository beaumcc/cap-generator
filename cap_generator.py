#!/usr/bin/env python3
# cap_generator.py
# Generate .CAP files from season stat XML files.
#
# Drag-and-drop support (Windows):
#   - Drag one or more .xml files (or folders) onto cap_generator.exe
#   - Those paths arrive as argv; we process them instead of scanning CWD
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
#   [9:21]   player name (12 bytes) -> EXACTLY player@name (trim, truncate, preserve capitalization)
#   [21]     0x00
#   [22]     0x20
#   [23]     type flag (3 hitter, 1 pitcher)
#   [24:216] 96 * uint16 little-endian stats

import sys
import struct
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

    # fielding
    "po": 27, "a": 28, "e": 29, "pb": 30, "indp": 31, "csb": 33,
    "sba": 34,

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
    "p_win": 37,
    "p_loss": 38,
    "p_bf": 42,
    "p_ab": 43,
    "p_loss2": 45,  # duplicate loss or save?
    "p_ip_outs": 47,  # ip * 3
    "p_h": 48,
    "p_r": 49,
    "p_er": 50,
    "p_bb": 51,
    "p_k": 52,
    "p_kl": 53,
    "p_gdp": 54,
    "p_hbp": 56,
    "p_wp_shifted": 57,  # wp * 256 (stored in high byte)
    "p_double": 58,
    "p_hr": 60,
    # psitsummary
    "ps_ground": 61,
    "ps_fly": 62,
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


def stats_from_opponent_elem(opponent: ET.Element | None, totals: ET.Element | None) -> list[int]:
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
    _set_opp_stat(u16, "h_sh", _get_int(hitting, "sh"))  # sh at alternate index 26

    # fielding
    _set_stat(u16, "po", _get_int(fielding, "po"))
    _set_stat(u16, "a", _get_int(fielding, "a"))
    _set_stat(u16, "e", _get_int(fielding, "e"))
    _set_stat(u16, "pb", _get_int(fielding, "pb"))
    _set_stat(u16, "indp", _get_int(fielding, "indp"))
    _set_stat(u16, "csb", _get_int(fielding, "csb"))
    _set_stat(u16, "sba", _get_int(fielding, "sba"))

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
        _set_opp_stat(u16, "p_appear", _get_int(pitching, "appear"))
        _set_opp_stat(u16, "p_win", _get_int(pitching, "appear"))   # duplicate appear
        _set_opp_stat(u16, "p_loss", _get_int(pitching, "appear"))  # duplicate appear
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

        # wp is stored shifted left by 8 bits (in high byte of u16[57])
        wp = _get_int(pitching, "wp")
        if wp and (idx := MAP_U16_OPPONENT.get("p_wp_shifted")) is not None:
            u16[idx] = clamp_u16(wp * 256)

        _set_opp_stat(u16, "p_double", _get_int(pitching, "double"))
        _set_opp_stat(u16, "p_hr", _get_int(pitching, "hr"))

    # psitsummary (opponent-specific indices)
    if ps is not None:
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
) -> bytes:
    """
    Build 292-byte header including opponent pseudo-record.

    Layout:
      [0:20]   team name
      [21:29]  team id
      [30:38]  date MM/DD/YY
      [40:76]  metadata (player count, record size, gp, fielding totals)
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
    struct.pack_into("<H", h, 42, REC_SIZE)
    struct.pack_into("<H", h, 44, int(totals.get("gp") or 0) if totals is not None else 0)

    totals_fielding = totals.find("fielding") if totals is not None else None
    if totals_fielding is not None:
        struct.pack_into("<H", h, 56, int(totals_fielding.get("indp") or 0))
        struct.pack_into("<H", h, 62, int(totals_fielding.get("csb") or 0))

    # Opponent pseudo-record header [76:100]
    h[76:84] = b"        "  # empty team id
    h[85:97] = pad_ascii("Opponents", 12)
    h[98] = 0x78  # opponent type flag

    # Opponent stats [100:292]
    opp_stats = stats_from_opponent_elem(opponent, totals)
    h[100:292] = struct.pack(U16_STRUCT_FMT, *opp_stats)

    return bytes(h)


def is_pitcher(p: ET.Element) -> bool:
    pos = (p.get("pos") or p.get("position") or "").strip().upper()
    return pos == "P" or (p.find("pitching") is not None)


def short_name_12(p: ET.Element) -> str:
    v = (p.get("name") or "").strip()
    if not v:
        raise RuntimeError("player missing required @name attribute")
    return v[:12]


def stats_from_player_elem(p: ET.Element, pitcher: bool) -> list[int]:
    u16 = [0] * U16_COUNT

    hitting = p.find("hitting")
    fielding = p.find("fielding")
    hs = p.find("hsitsummary")

    # pitchers often have gp/gs = 0
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

    # fielding
    _set_stat(u16, "po", _get_int(fielding, "po"))
    _set_stat(u16, "a", _get_int(fielding, "a"))
    _set_stat(u16, "e", _get_int(fielding, "e"))
    _set_stat(u16, "pb", _get_int(fielding, "pb"))
    _set_stat(u16, "indp", _get_int(fielding, "indp"))
    _set_stat(u16, "csb", _get_int(fielding, "csb"))
    _set_stat(u16, "sba", _get_int(fielding, "sba"))

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

    return u16


def pack_player_record(team_id: str, short_name: str, pitcher: bool, u16_stats: list[int]) -> bytes:
    rec = bytearray(REC_TEMPLATE)

    rec[0:8] = pad_ascii(team_id, 8)
    rec[0x08] = 0x00
    rec[0x09:0x15] = pad_ascii(short_name, 12)
    rec[0x15] = 0x00
    rec[0x16] = 0x20
    rec[0x17] = PTYPE_PITCHER if pitcher else PTYPE_HITTER

    rec[U16_START:U16_START + 2 * U16_COUNT] = struct.pack(U16_STRUCT_FMT, *u16_stats)
    return bytes(rec)


def generate_cap(xml_path: Path) -> Path:
    root = ET.parse(xml_path).getroot()

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

    players = [p for p in root.findall(".//player") if int(p.get("gp") or 0) > 0]
    players.sort(key=lambda p: int(p.get("uni") or 999))

    # Build header with opponent pseudo-record
    totals = root.find(".//totals")
    opponent = root.find(".//opponent")
    header = build_header(team_name, team_id, cap_date, len(players), totals, opponent)

    recs = []
    for p in players:
        nm = short_name_12(p)
        pit = is_pitcher(p)
        u16 = stats_from_player_elem(p, pit)
        recs.append(pack_player_record(team_id, nm, pit, u16))

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