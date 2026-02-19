# CAP Generator

Converts TAS Baseball/Softball season statistics XML files into binary `.CAP` files.

> **Disclaimer:** This software was created with AI code generation assistance. No ownership rights are claimed and no rights are granted. Use at your own risk. The authors are not liable for any incorrect, incomplete, or corrupted data produced by this software, nor for any loss of data resulting from its use. See [LICENSE](LICENSE) for full terms.

## Requirements

- Python 3.10 or later

No external dependencies required (uses only Python standard library).

### Installing Python

**Windows:**
1. Download Python from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer
3. Check "Add Python to PATH" during installation
4. Click "Install Now"

**Mac:**
1. Download Python from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer package
3. Follow the installation prompts

Alternatively, install via Homebrew:
```bash
brew install python
```

## Preparing XML Files

Before running the generator, ensure your XML files are properly configured:

1. **Verify the Team ID** - Check that the `<team id="XXX">` attribute in the XML matches the team ID that TAS expects.

2. **Rename the XML file** - The XML filename should match the team ID (e.g., `ASU.xml` for a team with `id="ASU"`). The generated CAP file will use the same name (e.g., `ASU.cap`).

If the team ID is missing from the XML, the script will use the filename as the team ID.

## Usage

### Run from command line

```bash
# Process all XML files in the current directory
python cap_generator.py

# Process specific files
python cap_generator.py team1.xml team2.xml

# Process all XML files in a directory
python cap_generator.py /path/to/stats/
```

## Binary Format

### Header (292 bytes)

| Offset | Size | Description |
|--------|------|-------------|
| 0-19 | 20 | Team name (ASCII, space-padded) |
| 20 | 1 | Null separator |
| 21-28 | 8 | Team ID (ASCII, space-padded) |
| 29 | 1 | Null separator |
| 30-37 | 8 | Date (MM/DD/YY format) |
| 38-39 | 2 | Padding (zeroes) |
| 40-41 | 2 | Player count (uint16 LE) |
| 42-43 | 2 | Record size (uint16 LE, always 216) |
| 44-45 | 2 | Wins (uint16 LE) |
| 46-47 | 2 | Losses (uint16 LE) |
| 48-49 | 2 | Unknown |
| 50-51 | 2 | Conference wins (uint16 LE) |
| 52-53 | 2 | Conference losses (uint16 LE) |
| 54-55 | 2 | Unknown |
| 56-57 | 2 | Fielding INDP — induced double plays (uint16 LE) |
| 58-59 | 2 | Unknown |
| 60-61 | 2 | Fielding SBA — stolen base attempts (uint16 LE) |
| 62-63 | 2 | Fielding CSB — caught stealing by (uint16 LE) |
| 64-65 | 2 | Pitching SHO — shutouts (uint16 LE) |
| 66-67 | 2 | Pitching CBO — combined shutouts (uint16 LE) |
| 68-75 | 8 | Padding (zeroes) |
| 76-99 | 24 | Opponent pseudo-record header (name="Opponents", type=0x78) |
| 100-291 | 192 | Opponent stats (96 x uint16 LE) |

### Player Record (216 bytes)

| Offset | Size | Description |
|--------|------|-------------|
| 0-7 | 8 | Team ID (ASCII, space-padded) |
| 8 | 1 | Null separator |
| 9-20 | 12 | Player name (ASCII, space-padded) |
| 21 | 1 | Null separator |
| 22 | 1 | Class/handedness byte (see below) |
| 23 | 1 | Last game appeared in (game number, not pitcher/hitter flag) |
| 24-215 | 192 | Stats (96 x uint16 little-endian) |

#### Byte 22: Class Year + Bats/Throws Encoding

Byte 22 encodes the player's class year in the high bits and batting/throwing handedness in the low bits. The value is `CLASS | HANDS`.

**Class year (high bits):**

| Value | Class |
|-------|-------|
| 0x08 | Freshman |
| 0x10 | Sophomore |
| 0x20 | Junior |
| 0x40 | Senior / Graduate |

**Bats/throws (low bits, OR'd with class):**

| Bits | Bats | Throws | Example (Junior) |
|------|------|--------|------------------|
| 0x00 | R | R | 0x20 |
| 0x01 | L | R | 0x21 |
| 0x02 | R | L | 0x22 |
| 0x03 | L | L | 0x23 |
| 0x04 | B (switch) | R | 0x24 |
| 0x06 | B (switch) | L | 0x26 |

TAS XML provides `bats` and `throws` attributes, so the full byte is encoded. PrestoSports lacks these attributes, so the low bits default to 0x00 (R/R).

#### Position

Player position (OF, INF, C, RHP, LHP, etc.) is **not** encoded in the CAP format. The only positional distinction is pitcher vs hitter, which determines which u16 stat slots are populated. Pitchers use the pitching stat indices (36-66, 86-95); hitters do not.

## Stat Mapping Reference

Stats are stored as 96 consecutive uint16 (2-byte) little-endian values starting at byte offset 24 in each player record.

**Byte offset formula:** `24 + (index × 2)`

### Core Batting Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 0 | 24 | `gp` | Games Played |
| 1 | 26 | `gs` | Games Started |
| 2 | 28 | `ab` | At Bats |
| 3 | 30 | `r` | Runs |
| 4 | 32 | `h` | Hits |
| 5 | 34 | `rbi` | Runs Batted In |
| 6 | 36 | `double` | Doubles |
| 7 | 38 | `triple` | Triples |
| 8 | 40 | `hr` | Home Runs |
| 9 | 42 | `bb` | Walks |
| 10 | 44 | `sb` | Stolen Bases |
| 11 | 46 | `cs` | Caught Stealing |
| 12 | 48 | `hbp` | Hit By Pitch |
| 13 | 50 | `sh` | Sacrifice Hits |
| 14 | 52 | `sf` | Sacrifice Flies |
| 15 | 54 | | *(unmapped)* |
| 16 | 56 | `so` | Strikeouts |
| 17 | 58 | `kl` | Strikeouts Looking |
| 18 | 60 | `gdp` | Ground into Double Play |
| 19 | 62 | `hitdp` | Hit into Double Play |
| 20 | 64 | | *(unmapped)* |
| 21 | 66 | `ibb` | Intentional Walks |

### Fielding Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 26 | 76 | `picked` | Picked Off (hitter) / SH duplicate (opponent) |
| 27 | 78 | `po` | Putouts |
| 28 | 80 | `a` | Assists |
| 29 | 82 | `e` | Errors |
| 30 | 84 | `pb` | Passed Balls |
| 31 | 86 | `indp` | Induced Double Plays |
| 32 | 88 | | *(unmapped)* |
| 33 | 90 | `csb` | Caught Stealing By |
| 34 | 92 | `sba` | Stolen Base Attempts |
| 35 | 94 | `ci` | Catcher's Interference |

### Hitting Situational Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 22 | 68 | `rcherr` | Reached on Error |
| 23 | 70 | `rchfc` | Reached on Fielder's Choice |
| 24 | 72 | `ground` | Ground Balls |
| 25 | 74 | `fly` | Fly Balls |
| 79 | 182 | `adv` | Advances |
| 80 | 184 | `lob` | Left on Base |
| 85 | 194 | `rbi-2out` | RBI with 2 Outs |

### Hitting Situational Pair Stats

Pair stats are parsed from XML format `"made,opp"`.

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 67 | 158 | `w2outs` (opp) | With 2 Outs - Opportunities |
| 68 | 160 | `w2outs` (made) | With 2 Outs - Made |
| 69 | 162 | `wrunners` (opp) | With Runners - Opportunities |
| 70 | 164 | `wrunners` (made) | With Runners - Made |
| 71 | 166 | `wrbiops` (opp) | RBI Opportunities - Total |
| 72 | 168 | `wrbiops` (made) | RBI Opportunities - Made |
| 73 | 170 | `vsleft` (opp) | Vs Left - Opportunities |
| 74 | 172 | `vsleft` (made) | Vs Left - Made |
| 75 | 174 | `rbi3rd` (opp) | RBI from 3rd - Opportunities |
| 76 | 176 | `rbi3rd` (made) | RBI from 3rd - Made |
| 77 | 178 | `advops` (opp) | Advance Opportunities - Total |
| 78 | 180 | `advops` (made) | Advance Opportunities - Made |
| 81 | 186 | `leadoff` (opp) | Leadoff - Opportunities |
| 82 | 188 | `leadoff` (made) | Leadoff - Made |
| 83 | 190 | `pinchhit` (opp) | Pinch Hit - Opportunities |
| 84 | 192 | `pinchhit` (made) | Pinch Hit - Made |
| 92 | 208 | `wloaded` (opp) | Bases Loaded - Opportunities |
| 93 | 210 | `wloaded` (made) | Bases Loaded - Made |

### Pitching Stats (Pitchers & Opponent Record)

For individual pitcher records, some indices have different meanings than the opponent record (noted below).

| Index | Byte Offset | Opponent Record | Individual Pitcher |
|-------|-------------|-----------------|---------------------|
| 36 | 96 | Appearances | Appearances |
| 37 | 98 | Appearances (dup) | Games Started |
| 38 | 100 | Losses | Games Finished |
| 39 | 102 | Complete Games | — |
| 40 | 104 | Shutouts | — |
| 41 | 106 | Combined Shutouts | Combined Shutouts |
| 42 | 108 | Batters Faced | Batters Faced |
| 43 | 110 | At Bats Against | At Bats Against |
| 44 | 112 | Wins | Wins |
| 45 | 114 | Losses (dup) | Losses |
| 46 | 116 | Saves | Saves |
| 47 | 118 | IP (as outs: IP × 3) | IP (as outs: IP × 3) |
| 48 | 120 | Hits Allowed | Hits Allowed |
| 49 | 122 | Runs Allowed | Runs Allowed |
| 50 | 124 | Earned Runs | Earned Runs |
| 51 | 126 | Walks | Walks |
| 52 | 128 | Strikeouts | Strikeouts |
| 53 | 130 | Strikeouts Looking | Strikeouts Looking |
| 54 | 132 | Wild Pitches | Wild Pitches |
| 55 | 134 | Balks | Balks |
| 56 | 136 | Hit Batters | Hit Batters |
| 57 | 138 | WP × 256 (high byte) | WP × 256 (high byte) |
| 58 | 140 | Doubles Allowed | Doubles Allowed |
| 59 | 142 | Triples Allowed | Triples Allowed |
| 60 | 144 | Home Runs Allowed | Home Runs Allowed |
| 63 | 150 | Pickoffs | Pickoffs |
| 65 | 154 | Sacrifice Hits Allowed | Sacrifice Hits Allowed |
| 66 | 156 | Sacrifice Flies Allowed | Sacrifice Flies Allowed |

Note: u16[57] is a redundant copy of wild pitches stored as `wp << 8` (the wp count in the high byte of the uint16). This is a TAS internal format quirk.

### Pitching Situational Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 61 | 146 | `ground` | Ground Balls |
| 62 | 148 | `fly` | Fly Balls |
| 86 | 196 | `leadoff` (opp) | Leadoff - Opportunities |
| 87 | 198 | `leadoff` (made) | Leadoff - Made |
| 88 | 200 | `wrunners` (opp) | With Runners - Opportunities |
| 89 | 202 | `wrunners` (made) | With Runners - Made |
| 90 | 204 | `vsleft` (opp) | Vs Left - Opportunities |
| 91 | 206 | `vsleft` (made) | Vs Left - Made |
| 94 | 212 | `w2outs` (opp) | With 2 Outs - Opportunities |
| 95 | 214 | `w2outs` (made) | With 2 Outs - Made |

