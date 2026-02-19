#!/usr/bin/env python3
# cap_decoder.py
# Decode .CAP binary files into human-readable text.
#
# Usage:
#   python cap_decoder.py file1.cap file2.cap ...
#   python cap_decoder.py                          # decodes all .cap in cwd

import struct
import sys
from pathlib import Path

HEADER_SIZE = 292
REC_SIZE = 216
U16_COUNT = 96

MAP_U16 = {
    "gp": 0, "gs": 1, "ab": 2, "r": 3, "h": 4, "rbi": 5,
    "double": 6, "triple": 7, "hr": 8, "bb": 9, "sb": 10, "cs": 11,
    "hbp": 12, "sh": 13, "sf": 14, "so": 16, "kl": 17, "gdp": 18, "hitdp": 19,
    "ibb": 21, "rcherr": 22, "rchfc": 23, "ground": 24, "fly": 25,
    "picked": 26, "po": 27, "a": 28, "e": 29, "pb": 30, "indp": 31,
    "csb": 33, "sba": 34, "ci": 35,
    "w2outs_opp": 67, "w2outs_made": 68, "wrunners_opp": 69, "wrunners_made": 70,
    "wrbiops_opp": 71, "wrbiops_made": 72, "vsleft_opp": 73, "vsleft_made": 74,
    "rbi3rd_opp": 75, "rbi3rd_made": 76, "advops_opp": 77, "advops_made": 78,
    "adv": 79, "lob": 80, "leadoff_opp": 81, "leadoff_made": 82,
    "pinchhit_opp": 83, "pinchhit_made": 84, "rbi_2out": 85,
    "wloaded_opp": 92, "wloaded_made": 93,
}

MAP_U16_OPPONENT = {
    "h_sh(opp)": 26,
    "p_appear": 36, "p_win/gs": 37, "p_loss/gf": 38, "p_cg": 39,
    "p_sho_raw": 40, "p_sho/cbo": 41, "p_bf": 42, "p_ab": 43,
    "p_2b/win": 44, "p_loss2": 45, "p_save": 46, "p_ip_outs": 47,
    "p_h": 48, "p_r": 49, "p_er": 50, "p_bb": 51, "p_k": 52, "p_kl": 53,
    "p_wp": 54, "p_bk": 55, "p_hbp": 56, "p_wp_shifted": 57,
    "p_double": 58, "p_triple": 59, "p_hr": 60,
    "ps_ground": 61, "ps_fly": 62, "p_pickoff": 63,
    "p_sha": 65, "p_sfa": 66,
    "ps_leadoff_opp": 86, "ps_leadoff_made": 87,
    "ps_wrunners_opp": 88, "ps_wrunners_made": 89,
    "ps_vsleft_opp": 90, "ps_vsleft_made": 91,
    "ps_w2outs_opp": 94, "ps_w2outs_made": 95,
}

CLASS_BYTE_REV = {0x08: "FR", 0x10: "SO", 0x20: "JR", 0x40: "SR"}

# Build index -> label list
_IDX_LABELS = {}
for _name, _idx in MAP_U16.items():
    _IDX_LABELS.setdefault(_idx, []).append(_name)
for _name, _idx in MAP_U16_OPPONENT.items():
    _IDX_LABELS.setdefault(_idx, []).append(_name)


def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def _ascii(data, start, end):
    return data[start:end].rstrip(b" \x00").decode("ascii", errors="replace")


def _label(idx):
    labels = _IDX_LABELS.get(idx, [])
    return ", ".join(labels) if labels else f"(unmapped:{idx})"


def decode_cap(path):
    data = Path(path).read_bytes()
    sep = "=" * 80
    lines = []
    out = lines.append

    out(f"\n{sep}")
    out(f"FILE: {path}")
    out(f"Total size: {len(data)} bytes")
    out(sep)

    # Header
    out(f"\n--- HEADER (bytes 0-291) ---")
    out(f'  [0:20]   Team Name     : "{_ascii(data, 0, 20)}"')
    out(f"  [20]     Separator     : 0x{data[20]:02X}")
    out(f'  [21:29]  Team ID       : "{_ascii(data, 21, 29)}"')
    out(f"  [29]     Separator     : 0x{data[29]:02X}")
    out(f'  [30:38]  Date          : "{_ascii(data, 30, 38)}"')
    out(f"  [38:40]  Padding       : {data[38:40].hex()}")
    out(f"  [40:42]  Player Count  : {_u16(data, 40)}")
    out(f"  [42:44]  Record Size   : {_u16(data, 42)}")
    out(f"  [44:46]  Wins          : {_u16(data, 44)}")
    out(f"  [46:48]  Losses        : {_u16(data, 46)}")
    out(f"  [48:50]  Unknown       : {_u16(data, 48)}")
    out(f"  [50:52]  Conf Wins     : {_u16(data, 50)}")
    out(f"  [52:54]  Conf Losses   : {_u16(data, 52)}")
    out(f"  [54:56]  Unknown       : {_u16(data, 54)}")
    out(f"  [56:58]  Field INDP    : {_u16(data, 56)}")
    out(f"  [58:60]  Unknown       : {_u16(data, 58)}")
    out(f"  [60:62]  Field SBA     : {_u16(data, 60)}")
    out(f"  [62:64]  Field CSB     : {_u16(data, 62)}")
    out(f"  [64:66]  Pitch SHO     : {_u16(data, 64)}")
    out(f"  [66:68]  Pitch CBO     : {_u16(data, 66)}")
    out(f"  [68:76]  Remaining     : {data[68:76].hex()}")

    # Opponent pseudo-record
    out(f"\n  --- Opponent Record [76:292] ---")
    out(f'  [76:84]  Opp Team ID   : "{_ascii(data, 76, 84)}"')
    out(f'  [85:97]  Opp Name      : "{_ascii(data, 85, 97)}"')
    out(f"  [98]     Type Flag     : 0x{data[98]:02X}")

    opp_stats = struct.unpack_from("<" + "H" * U16_COUNT, data, 100)
    out(f"\n  Opponent u16 stats:")
    for i, val in enumerate(opp_stats):
        label = _label(i)
        marker = " <--" if val != 0 else ""
        out(f"    u16[{i:2d}] = {val:5d}  {label}{marker}")

    # Player records
    num_recs = (len(data) - HEADER_SIZE) // REC_SIZE
    out(f"\n--- PLAYER RECORDS ({num_recs} players) ---")

    for r in range(num_recs):
        offset = HEADER_SIZE + r * REC_SIZE
        rec = data[offset:offset + REC_SIZE]

        p_name = rec[9:21].rstrip(b" \x00").decode("ascii", errors="replace")
        class_byte = rec[22]
        class_str = CLASS_BYTE_REV.get(class_byte, f"0x{class_byte:02X}")
        type_byte = rec[23]
        type_str = {1: "PITCHER", 3: "HITTER"}.get(type_byte, f"type={type_byte}")

        stats = struct.unpack_from("<" + "H" * U16_COUNT, rec, 24)

        out(f'\n  #{r+1:2d} "{p_name}"  {type_str}  class={class_str}')
        for i, val in enumerate(stats):
            label = _label(i)
            marker = " <--" if val != 0 else ""
            out(f"      u16[{i:2d}] = {val:5d}  {label}{marker}")

    return "\n".join(lines)


def main():
    targets = [Path(a) for a in sys.argv[1:] if a.lower().endswith(".cap")]
    if not targets:
        targets = sorted(Path.cwd().glob("*.cap"))
    if not targets:
        print("No .cap files found.")
        return 1

    for t in targets:
        txt_path = t.with_suffix(".txt")
        txt_path.write_text(decode_cap(t) + "\n")
        print(f"{t.name} -> {txt_path.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
