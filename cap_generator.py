#!/usr/bin/env python3
# cap_generator.py
# Generate .CAP files from season stat XML files in the current directory.
#
# Header: 292 bytes (team name/id/date + constant tail copied from OM.CAP format)
# Body:   N * 216-byte player records (N = number of <player> nodes)
#
# Player record (216 bytes):
#   [0:8]    team id (ASCII, space padded)
#   [8]      0x00
#   [9:21]   player name (12 bytes) -> First initial + last name (e.g., "T. Bissetta")
#   [21]     0x00
#   [22]     0x20
#   [23]     type flag (3 hitter, 1 pitcher)
#   [24:216] 96 * uint16 little-endian stats (unknown fields left 0)

from __future__ import annotations

import struct
from pathlib import Path
import xml.etree.ElementTree as ET

HEADER_SIZE = 292
REC_SIZE = 216

U16_START = 0x18
U16_COUNT = 96

# Constant tail from OM.CAP header bytes [40:292]
HEADER_TAIL = bytes.fromhex(
    "1900d800030000000000000000000000020000000000020000000000000000000000000020202020"
    "20202020004f70706f6e656e7473202020007800030003005c000600160004000600000002000600"
    "0000020000000100020000002300090002000200000000000200030016000e000100420018000400"
    "01000400000000000500000003000300030000000000000079005e0000000300000042001f001d00"
    "1c0016001600080003000000050000030700000005001500130000000000000000001b0005002800"
    "05001a00010027000800080002002d0010000900140019000b0001000000000016000a003a001500"
    "3b001300010000001c000700"
)
assert len(HEADER_TAIL) == 252

# Proven u16 index mapping (everything else stays 0)
MAP_U16 = {
    # core batting counts
    "gp": 0, "gs": 1,
    "ab": 2, "r": 3, "h": 4, "rbi": 5,
    "double": 6, "triple": 7, "hr": 8,
    "bb": 9, "sb": 10, "hbp": 12,
    "so": 16, "kl": 17, "gdp": 18, "hitdp": 19,

    # fielding
    "po": 27, "a": 28, "e": 29, "pb": 30, "indp": 31, "csb": 33,

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

    "rbi_2out": 85,

    "wloaded_opp": 92, "wloaded_made": 93,
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
    if len(parts) >= 2:
        return (clamp_u16(parts[0]), clamp_u16(parts[1]))
    return (clamp_u16(parts[0]), 0)


def build_header(team_name: str, team_id: str, mmddyy: str) -> bytes:
    """
    Header layout (292 bytes):
      [0:20]  team name
      [20]    0x00
      [21:29] team id
      [29]    0x00
      [30:38] date MM/DD/YY
      [38:40] 0x00 0x00
      [40:292] constant tail
    """
    h = bytearray(HEADER_SIZE)
    h[0:20] = pad_ascii(team_name, 20)
    h[20] = 0x00
    h[21:29] = pad_ascii(team_id, 8)
    h[29] = 0x00
    h[30:38] = pad_ascii(mmddyy, 8)
    h[38:40] = b"\x00\x00"
    h[40:292] = HEADER_TAIL
    return bytes(h)


def is_pitcher(p: ET.Element) -> bool:
    pos = (p.get("pos") or p.get("position") or "").strip().upper()
    return pos == "P" or (p.find("pitching") is not None)


def short_name_12(p: ET.Element) -> str:
    """Convert full name to abbreviated format: "Tristan Bissetta" -> "T. Bissetta"."""
    name = (p.get("name") or "").strip()
    if not name:
        raise RuntimeError("player missing required @name attribute")
    parts = name.split()
    if len(parts) >= 2:
        abbrev = f"{parts[0][0]}. {parts[-1]}"
    else:
        abbrev = name
    return abbrev[:12]


def stats_from_player_elem(p: ET.Element, pitcher: bool) -> list[int]:
    u16 = [0] * U16_COUNT

    def setf(field: str, value: int):
        idx = MAP_U16.get(field)
        if idx is not None:
            u16[idx] = clamp_u16(value)

    def get_int(elem: ET.Element | None, key: str) -> int:
        if elem is None:
            return 0
        v = elem.get(key)
        return clamp_u16(v) if v is not None else 0

    hitting = p.find("hitting")
    fielding = p.find("fielding")
    hs = p.find("hsitsummary")

    # Keep the CAP behavior you saw: pitchers often have gp/gs = 0
    if not pitcher:
        setf("gp", clamp_u16(p.get("gp") or 0))
        setf("gs", clamp_u16(p.get("gs") or 0))

    # hitting
    setf("ab", get_int(hitting, "ab"))
    setf("r", get_int(hitting, "r"))
    setf("h", get_int(hitting, "h"))
    setf("rbi", get_int(hitting, "rbi"))
    setf("double", get_int(hitting, "double"))
    setf("triple", get_int(hitting, "triple"))
    setf("hr", get_int(hitting, "hr"))
    setf("bb", get_int(hitting, "bb"))
    setf("sb", get_int(hitting, "sb"))
    setf("hbp", get_int(hitting, "hbp"))
    setf("so", get_int(hitting, "so"))
    setf("kl", get_int(hitting, "kl"))
    setf("gdp", get_int(hitting, "gdp"))
    setf("hitdp", get_int(hitting, "hitdp"))

    # fielding
    setf("po", get_int(fielding, "po"))
    setf("a", get_int(fielding, "a"))
    setf("e", get_int(fielding, "e"))
    setf("pb", get_int(fielding, "pb"))
    setf("indp", get_int(fielding, "indp"))
    setf("csb", get_int(fielding, "csb"))

    # hsitsummary
    setf("rcherr", get_int(hs, "rcherr"))
    setf("rchfc", get_int(hs, "rchfc"))
    setf("ground", get_int(hs, "ground"))
    setf("fly", get_int(hs, "fly"))
    setf("adv", get_int(hs, "adv"))
    setf("lob", get_int(hs, "lob"))

    def set_pair(xml_key: str, made_key: str, opp_key: str):
        if hs is None:
            return
        made, opp = parse_pair(hs.get(xml_key) or "")
        setf(made_key, made)
        setf(opp_key, opp)

    set_pair("w2outs", "w2outs_made", "w2outs_opp")
    set_pair("wrunners", "wrunners_made", "wrunners_opp")
    set_pair("wrbiops", "wrbiops_made", "wrbiops_opp")
    set_pair("vsleft", "vsleft_made", "vsleft_opp")
    set_pair("rbi3rd", "rbi3rd_made", "rbi3rd_opp")
    set_pair("advops", "advops_made", "advops_opp")
    set_pair("leadoff", "leadoff_made", "leadoff_opp")
    set_pair("wloaded", "wloaded_made", "wloaded_opp")

    if hs is not None:
        setf("rbi_2out", clamp_u16(hs.get("rbi-2out") or 0))

    return u16


def pack_player_record(team_id: str, short_name: str, pitcher: bool, u16_stats: list[int]) -> bytes:
    rec = bytearray(b"\x00" * REC_SIZE)

    rec[0:8] = pad_ascii(team_id, 8)
    rec[0x08] = 0x00
    rec[0x09:0x15] = pad_ascii(short_name, 12)
    rec[0x15] = 0x00
    rec[0x16] = 0x20
    rec[0x17] = PTYPE_PITCHER if pitcher else PTYPE_HITTER

    u16 = [0] * U16_COUNT
    for i in range(min(U16_COUNT, len(u16_stats))):
        u16[i] = clamp_u16(u16_stats[i])

    rec[U16_START:U16_START + 2 * U16_COUNT] = struct.pack("<" + "H" * U16_COUNT, *u16)
    return bytes(rec)


def generate_cap(xml_path: Path) -> Path:
    root = ET.parse(xml_path).getroot()

    cap_date = mmddyy_from_xml_date(root.get("date") or "")

    team = root.find(".//team")
    if team is None:
        raise RuntimeError("XML missing <team ...> element")

    team_name = (team.get("name") or "").strip()
    team_id = (team.get("id") or "").strip()
    if not team_name or not team_id:
        raise RuntimeError("XML team element missing required name/id attributes")

    header = build_header(team_name, team_id, cap_date)

    players = [p for p in root.findall(".//player") if int(p.get("gp") or 0) > 0]
    players.sort(key=lambda p: int(p.get("uni") or 999))
    recs = []
    for p in players:
        nm = short_name_12(p)
        pit = is_pitcher(p)
        u16 = stats_from_player_elem(p, pit)
        recs.append(pack_player_record(team_id, nm, pit, u16))

    out_path = xml_path.with_suffix(".cap")
    out_path.write_bytes(header + b"".join(recs))
    return out_path


def main() -> int:
    here = Path.cwd()
    xmls = sorted(p for p in here.iterdir() if p.is_file() and p.suffix.lower() == ".xml")
    if not xmls:
        print("No XML files found in current directory.")
        return 1

    for x in xmls:
        try:
            out = generate_cap(x)
            print(f"OK: {x.name} -> {out.name} ({out.stat().st_size} bytes)")
        except Exception as e:
            print(f"FAIL: {x.name}: {e}")
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())