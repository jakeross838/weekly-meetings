#!/usr/bin/env python3
"""
Phase 1 RETRY — Sub Reclassification Classifier (v3, sub-line-first)

Reads:
  - config/phase-keywords.yaml
  - config/sub-filters.yaml
  - config/cross-trade-rejections.yaml
  - buildertrend-scraper/data/daily-logs.json

Writes:
  - data/derived-phases.json
  - data/reclassification-diff.md

Method (3-pass + 3 rules):
  Step A — Per-sub-line extraction:
    For each daily log, extract numbered "1. <text>", "2. <text>" lines from
    notes_full. Each numbered line typically describes one sub on site.
    A sub-alias dictionary maps each line to canonical crews_clean name(s).

  Step B — Pass 1 (high confidence — sub-line text match):
    For each (sub, log) pair, classify against THE SUB-LINE TEXT ONLY (not the
    full notes — that bleeds keywords across crews). Match keyword library.
    Multiple phases can be assigned per (sub, log) when multiple keyword
    patterns hit (e.g., "rough water lines and gas line" -> 6.1 + 6.2).
    Confidence: 'high'.

  Step C — Compute sub history + modal_trade:
    From Pass 1 high-confidence hits, build:
      - sub_text_phases: Counter of which phase codes each sub has high-conf
        evidence for, and how often.
      - sub_modal_trade: trade category derived from the sub's dominant phase
        codes — used by cross-trade rejection rules.
    Force_modal_trade overrides from YAML take precedence (Architectural
    Marble -> stone_counters; Detweilers -> plumbing).

  Step D — Pass 2 (tag_disambiguated, GATED):
    Sub's own line is generic ("onsite", "continued work") AND
    parent_group_activities tag matches one specific phase.
    Gate: sub must have >=3 high-confidence Pass 1 logs for that phase
    historically. If zero, the tag is REJECTED and the log falls through.
    Forbidden phases: any in `require_text_signal` skip Pass 2 entirely.
    Cross-trade rejection: if candidate phase is forbidden by sub's
    modal_trade, REJECT (log rejection in `rejected_phases`).
    Confidence: 'tag_disambiguated'.

  Step E — Pass 3 (low_review, modal fallback):
    Sub's own line is unattributable AND tag is multi-phase / ambiguous /
    absent. Fall back to sub's modal phase. Cross-trade rejection still
    applies. Confidence: 'low_review'.

  Step F — Pass 4 (manual_review):
    Anything still unmatched. No attribution.

Three layered rules:
  Rule 1 — Multi-phase log de-attribution: if a single log has 3+ different
    parent activity tags AND the sub's own line is generic, credit the sub
    for ONLY their modal phase. Other tags do NOT produce attributions.
  Rule 2 — Cross-trade rejection from cross-trade-rejections.yaml.
  Rule 3 — Defer Watts brown/finish coat: 7.2/7.3/7.6 collapse to 7.2.
    "stucco continues" -> 7.2 default. Phase 3 burst-segmentation will split.

Refined <3-log sub bypass:
  Subs with <3 high-confidence Pass 1 logs total:
    - Pass 1 high-confidence text matches: KEEP (credit normally).
    - Pass 2 tag-disambiguation: BYPASS, route directly to manual_review.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(r"C:/Users/Jake/weekly-meetings")
SCRAPER_DATA = Path(r"C:/Users/Jake/buildertrend-scraper/data/daily-logs.json")
KEYWORDS_FILE = ROOT / "config" / "phase-keywords.yaml"
FILTERS_FILE = ROOT / "config" / "sub-filters.yaml"
REJECTIONS_FILE = ROOT / "config" / "cross-trade-rejections.yaml"
OUT_JSON = ROOT / "data" / "derived-phases.json"
OUT_DIFF = ROOT / "data" / "reclassification-diff.md"


# ----------------------------------------------------------------------------
# Sub alias dictionary — maps phrases to canonical crews_clean names.
# ----------------------------------------------------------------------------

SUB_ALIASES: dict[str, list[str]] = {
    "Ross Built Crew": ["ross built", "ross crew", "ross built crew", "rb crew", "field crew", "ross s crew"],
    "Gator Plumbing": ["gator plumbing", "gator"],
    "Metro Electric, LLC": ["metro electric", "metro"],
    "ALL VALENCIA CONSTRUCTION LLC": ["all valencia", "valencia"],
    "Jeff Watts Plastering and Stucco": ["jeff watts", "watts plastering", "watts stucco", "watts crew", "watts", "jeffs crew"],
    "Southwest Concrete & Masonry Systems, LLC": ["southwest concrete", "southwest", "sw concrete and masonry"],
    "ML Concrete, LLC": ["ml concrete"],
    "TNT Custom Painting": ["tnt custom", "tnt"],
    "Rangel Custom Tile LLC": ["rangel custom", "rangel tile", "rangel", "nemecio", "nemesio"],
    "M&J Florida Enterprise LLC": ["m&j florida", "m&j", "mj florida"],
    "Tom Sanger Pool and Spa LLC": ["tom sanger", "sanger pool", "sanger"],
    "Florida Sunshine Carpentry LLC": ["florida sunshine", "sunshine carpentry"],
    "SmartShield Homes LLC": ["smartshield", "smart shield"],
    "Elizabeth Key Rosser": ["elizabeth key", "key rosser", "keys crew"],
    "WG QUALITY INC": ["wg quality"],
    "Captain Cool LLC": ["captain cool"],
    "Alejandro Carpentry, Inc": ["alejandro carpentry", "alejandro"],
    "Gonzalez Construction Services FL LLC": ["gonzalez construction", "gonzalez"],
    "RC Grade Services, LLC": ["rc grade"],
    "Climatic Conditioning Company Inc": ["climatic conditioning", "climatic"],
    "CoatRite LLC": ["coatrite", "coat rite"],
    "Universal Window Solutions": ["universal window", "universal windows"],
    "Derosias Custom Builders LLC": ["derosias"],
    "Sight to See Construction LLC": ["sight to see", "sight to see construction", "sight to see carpentry"],
    "Sight to See Construction, LLC": ["sight to see"],
    "DB Improvement Services": ["db improvement", "db improvements"],
    "DB Improvement Services, LLC": ["db improvement", "db improvements"],
    "Myers Painting, LLC": ["myers painting", "myers"],
    "Creative CC Inc.": ["creative cc"],
    "Integrity Floors LLC": ["integrity floors", "integrity flooring", "integrity"],
    "Avery Roof Services, LLC": ["avery roof", "avery"],
    "SMS Construction Corp": ["sms construction", "sms carpentry", "sms"],
    "Doug Naeher Drywall Inc.": ["doug naeher", "naeher"],
    "Precision Stairs Florida, Inc": ["precision stairs", "precision"],
    "Altered State Of Mine , LLC": ["altered state of mine", "altered state"],
    "Sarasota Cabinetry": ["sarasota cabinetry"],
    "Tile Solutions LLC": ["tile solutions"],
    "DB Welding Inc.": ["db welding"],
    "Blue Vision Roofing Inc.": ["blue vision roofing", "blue vision"],
    "Nichols Carpentry & Construction": ["nichols carpentry", "nichols"],
    "HBS Drywall": ["hbs drywall", "hbs"],
    "Smarthouse Integration": ["smarthouse"],
    "SRQ Building Services": ["srq building", "srq"],
    "Kimal Lumber Company": ["kimal lumber", "kimal"],
    "Paradise Foam, LLC": ["paradise foam"],
    "Bradley Building Products": ["bradley building", "bradley"],
    "Architectural Marble Importers, Inc": ["architectural marble", "marble importers"],
    "Brilliant Harvest": ["brilliant harvest"],
    "West Coast Foundation, Inc.": ["west coast foundation", "west coast"],
    "Universal Engineering": ["universal engineering"],
    "Viewrail": ["viewrail"],
    "Fuse Specialty Appliances": ["fuse specialty"],
    "Triple H Painting, LLC": ["triple h painting", "triple h"],
    "SB Custom Flooring LLC": ["sb custom flooring", "sb flooring"],
    "Macc's Remodeling, LLC": ["macc's", "macc"],
    "Cucine Ricci": ["cucine ricci", "cucine"],
    "EcoSouth": ["ecosouth"],
    "Alert Core Drilling, Inc.": ["alert core", "core drilling"],
    "Englewood Window & Door": ["englewood window", "englewood"],
    "Total Home Service Cleaning Inc": ["total home service"],
    "All Glass & Windows": ["all glass"],
    "Scranton Elevator Service, LLC": ["scranton elevator", "scranton"],
    "Daniel Insulation LLC": ["daniel insulation"],
    "J.P. Services of Sarasota, LLC": ["j.p. services", "jp services"],
    "Detweilers Propane Gas Service, LLC": ["detweilers", "detweiler"],
    "Pear Tree Cabinets & Design, LLC": ["pear tree"],
    "Parrish Well Drilling, Inc.": ["parrish well", "parrish"],
    "Capstone Contractors, LLC": ["capstone"],
    "Weird Science Concrete": ["weird science"],
    "Campbell Cabinetry Designs, Inc.": ["campbell cabinetry", "campbell"],
    "Loftin Plumbing, LLC": ["loftin plumbing", "loftin"],
    "MSH Brick Pavers Inc": ["msh brick", "msh"],
    "D&D Garage Doors, Inc.": ["d&d garage"],
    "Ferguson Enterprises Inc": ["ferguson"],
    "Progressive Cabinetry": ["progressive cabinetry"],
    "Volcano Stone, LLC": ["volcano stone", "volcano", "oleg"],
    "Creative Electric Services, LLC": ["creative electric"],
    "Lancaster Designs": ["lancaster"],
    "First Choice Custom Cabinets LLC": ["first choice"],
    "USA Fence Company": ["usa fence"],
    "Florida Power Solutions": ["florida power solutions"],
    "Faust Renovations, LLC": ["faust renovations", "faust"],
    "Arquai, LLC dba Elxai": ["arquai", "elxai"],
    "Doudney Sheet Metal Works inc.": ["doudney", "daudney"],
    "Vertechs Elevators Florida Inc": ["vertechs"],
    "D&D Seamless Gutters, LLC": ["d&d seamless"],
    "DSDG": ["dsdg"],
    "Skyway Gutters LLC": ["skyway gutters"],
    "Banko Overhead Doors, Inc": ["banko"],
    "Michael A. Gilkey, Inc.": ["michael gilkey", "gilkey"],
    "Triple H Architectural Products": ["triple h architectural"],
    "Miguel Guevara": ["miguel guevara"],
    "Colonial Precast Concrete, LLC": ["colonial precast"],
    "Overhead Door Company of Sarasota": ["overhead door"],
    "Prime Glass INC": ["prime glass"],
    "Rosa's Cast Stone LLC": ["rosa's cast", "rosa cast stone"],
    "SW Concrete and Masonry (Old)": ["sw concrete"],
    "Real Woods": ["real woods"],
    "Lone Star Electrical Services LLC": ["lone star", "lonestar"],
    "Lonestar Electric": ["lonestar", "lone star"],
}

# Role-to-trade mapping. When a numbered line uses a generic role phrase
# (no sub name), match the role to a trade key, then route the line to
# the on-site crew(s) classified as that trade.
ROLE_TO_TRADE: dict[str, str] = {
    r"\bthe\s+plumbers?\s+(was|were|are|is)": "plumbing",
    r"\bplumbers?\s+(was|were|are|is|were\s+onsite|onsite)": "plumbing",
    r"\bthe\s+plumber\s+(was|is|were|continues|continued|on)": "plumbing",
    r"\bgas\s+contractor": "plumbing",
    r"\bthe\s+electricians?\s+(was|were|are|is|onsite|completing)": "electrical",
    r"\belectricians?\s+(was|were|are|is|onsite|continued|completed|continue)": "electrical",
    r"\belectric(al)?\s+contractor": "electrical",
    r"\bthe\s+hvac\s+contractor": "hvac",
    r"\bhvac\s+contractor": "hvac",
    r"\bthe\s+(?:a/c|ac)\s+contractor": "hvac",
    r"\bthe\s+framers?\s+(are|were|was|continue|completed)": "framing",
    r"\bframers?\s+(are|were|was|continue|completed|onsite|on\s+site)": "framing",
    r"\bframing\s+(crew|contractor)": "framing",
    r"\bthe\s+tile\s+contractor": "tile",
    r"\btile\s+contractor": "tile",
    r"\btile\s+crew": "tile",
    r"\btile\s+install": "tile",
    r"\bthe\s+cabinetry\s+contractor": "cabinets",
    r"\bcabinet\s+contractor": "cabinets",
    r"\bcabinet\s+installer": "cabinets",
    r"\bthe\s+kitchen\s+cabinet": "cabinets",
    r"\bcounter\s*top\s+contractor": "countertops",
    r"\bthe\s+countertop": "countertops",
    r"\bthe\s+painters?\s+(was|were|are|is)": "painting",
    r"\bpainters?\s+(was|were|are|is|onsite|continue|completed)": "painting",
    r"\bpainting\s+contractor": "painting",
    r"\bthe\s+painter\s+(is|was)": "painting",
    r"\bthe\s+drywall(ers?)?\b": "drywall",
    r"\bdrywall(ers?)\s+(continue|completed|are|onsite)": "drywall",
    r"\bthe\s+roof(ers?|ing)?\s+contractor": "roofing",
    r"\broofing\s+contractor": "roofing",
    r"\broofers\b": "roofing",
    r"\bthe\s+siders?\b": "siding",
    r"\bsider(s)\s+(are|continue|onsite)": "siding",
    r"\bsiding\s+(crew|contractor)": "siding",
    r"\bthe\s+waterproofer": "waterproofing",
    r"\bwaterproofing\s+contractor": "waterproofing",
    r"\bwaterproof(ers?|ing)\s+(crew|are|continue)": "waterproofing",
    r"\bthe\s+stucco\s+contractor": "stucco",
    r"\bstucco\s+(crew|contractor)": "stucco",
    r"\bthe\s+pool\s+contractor": "pool",
    r"\bpool\s+contractor": "pool",
    r"\bthe\s+window\s+contractor": "windows",
    r"\bwindow\s+contractor": "windows",
    r"\bthe\s+window\s+installer": "windows",
    r"\bwindow\s+installer": "windows",
    r"\bthe\s+flooring\s+contractor": "wood_floor",
    r"\bflooring\s+contractor": "wood_floor",
    r"\bwood\s+flooring": "wood_floor",
    r"\bthe\s+concrete\s+contractor": "concrete",
    r"\bconcrete\s+contractor": "concrete",
    r"\bconcrete\s+crew": "concrete",
    r"\bthe\s+appliance\s+contractor": "appliances",
    r"\bappliance\s+contractor": "appliances",
    r"\bthe\s+railing\s+contractor": "metal_fab",
    r"\brailing\s+(installer|contractor|crew)": "metal_fab",
    r"\bthe\s+trim\s+carpenters?\b": "trim_carpentry",
    r"\btrim\s+carpenter(s)?\b": "trim_carpentry",
    r"\bthe\s+stair\s+contractor": "stairs",
    r"\bstair\s+contractor": "stairs",
    r"\bcleaning\s+(crew|company)": "cleaning",
    r"\bcleaners\b": "cleaning",
    r"\bsolar\s+(guys|crew)": "solar",
    r"\belevator\s+contractor": "elevator",
    r"\bgutters?\s+(crew|contractor)": "gutters",
    r"\binsulation\s+(crew|contractor)": "insulation",
    r"\bgarage\s+door\s+contractor": "garage_door",
    r"\bsurveyor": "surveyor",
}

TRADE_TO_SUBS: dict[str, list[str]] = {
    "plumbing": ["Gator Plumbing", "Loftin Plumbing, LLC"],
    "electrical": ["Metro Electric, LLC", "Lone Star Electrical Services LLC", "Lonestar Electric",
                   "Creative Electric Services, LLC", "Allan Electric, Inc."],
    "hvac": ["Captain Cool LLC", "Climatic Conditioning Company Inc"],
    "framing": ["ALL VALENCIA CONSTRUCTION LLC", "Florida Sunshine Carpentry LLC",
                "Alejandro Carpentry, Inc"],
    "tile": ["Rangel Custom Tile LLC", "Tile Solutions LLC", "Elizabeth Key Rosser",
             "Sand Dollar Tile & Designs"],
    "cabinets": ["Cucine Ricci", "Sarasota Cabinetry", "First Choice Custom Cabinets LLC",
                 "Pear Tree Cabinets & Design, LLC", "Campbell Cabinetry Designs, Inc.",
                 "Progressive Cabinetry"],
    "countertops": ["Volcano Stone, LLC", "Architectural Marble Importers, Inc",
                    "Rosa's Cast Stone LLC"],
    "painting": ["TNT Custom Painting", "Myers Painting, LLC", "Triple H Painting, LLC"],
    "drywall": ["WG QUALITY INC", "HBS Drywall", "Doug Naeher Drywall Inc.",
                "M&J Florida Enterprise LLC"],
    "roofing": ["Avery Roof Services, LLC", "Blue Vision Roofing Inc."],
    "siding": ["M&J Florida Enterprise LLC"],
    "waterproofing": ["CoatRite LLC"],
    "stucco": ["Jeff Watts Plastering and Stucco"],
    "pool": ["Tom Sanger Pool and Spa LLC", "Derosias Custom Builders LLC"],
    "windows": ["Universal Window Solutions", "Englewood Window & Door", "All Glass & Windows",
                "Gonzalez Construction Services FL LLC", "Prime Glass INC"],
    "wood_floor": ["Integrity Floors LLC", "SB Custom Flooring LLC", "ML Concrete, LLC"],
    "concrete": ["ML Concrete, LLC", "Southwest Concrete & Masonry Systems, LLC", "West Coast Foundation, Inc."],
    "appliances": ["Fuse Specialty Appliances"],
    "metal_fab": ["DB Welding Inc.", "Viewrail"],
    "trim_carpentry": ["SMS Construction Corp", "Sight to See Construction LLC",
                       "Sight to See Construction, LLC", "DB Improvement Services",
                       "DB Improvement Services, LLC", "Creative CC Inc.",
                       "Nichols Carpentry & Construction"],
    "stairs": ["Precision Stairs Florida, Inc"],
    "cleaning": ["Total Home Service Cleaning Inc"],
    "solar": ["Brilliant Harvest"],
    "elevator": ["Scranton Elevator Service, LLC", "Vertechs Elevators Florida Inc",
                 "Residential Elevators"],
    "gutters": ["D&D Seamless Gutters, LLC", "Skyway Gutters LLC"],
    "insulation": ["Daniel Insulation LLC", "Paradise Foam, LLC"],
    "garage_door": ["Banko Overhead Doors, Inc", "D&D Garage Doors, Inc.",
                    "Overhead Door Company of Sarasota"],
    "surveyor": ["Jim Amberger Land Surveying, LLC", "MSB Surveying, Inc."],
}

ROLE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), trade) for p, trade in ROLE_TO_TRADE.items()
]


# ----------------------------------------------------------------------------
# Phase code -> modal_trade mapping (for cross-trade rejection).
# A sub's modal_trade is the trade category implied by their dominant Pass 1
# phase codes. cross-trade-rejections.yaml uses these trade names as keys.
# ----------------------------------------------------------------------------

PHASE_TO_TRADE: dict[str, str] = {
    # Site
    "1.1": "preconstruction", "1.2": "site_clearing", "1.3": "site_clearing",
    "1.4": "site_grading", "1.5": "surveying",
    # Foundation / concrete
    "2.1": "concrete", "2.2": "concrete", "2.3": "concrete",
    "2.4": "waterproofing",
    "2.5": "plumbing", "2.6": "electrical",
    "2.7": "concrete", "2.8": "concrete",
    # Structural shell
    "3.1": "concrete", "3.2": "concrete", "3.3": "concrete",
    "3.4": "framing", "3.5": "framing",
    "3.7": "framing", "3.8": "framing", "3.9": "framing",
    # Dry-in
    "4.1": "roofing", "4.2": "roofing",
    "4.3": "windows", "4.4": "windows",
    # Exterior rough
    "5.1": "framing", "5.2": "framing", "5.3": "framing",
    # MEP rough
    "6.1": "plumbing", "6.2": "plumbing",
    "6.3": "electrical", "6.5": "electrical",
    "6.4": "hvac",
    "6.6": "fire", "6.7": "inspections",
    # Envelope close-up
    "7.1": "stucco_plaster", "7.2": "stucco_plaster", "7.3": "stucco_plaster", "7.6": "stucco_plaster",
    "7.4": "siding", "7.5": "siding", "7.7": "trim_finish",
    # Insul / drywall
    "8.1": "insulation",
    "8.2": "drywall", "8.3": "drywall", "8.4": "drywall", "8.5": "drywall",
    # Interior rough finish
    # 9.1 covers railings/metal-fab as nearest-fit (DB Welding); 9.2/9.3 = trim
    "9.1": "metal_fab", "9.2": "trim_finish", "9.3": "trim_finish",
    # Tile & stone
    "10.1": "tile_floor", "10.2": "tile_floor", "10.3": "tile_floor", "10.4": "stone_counters",
    # Cabinetry & stone tops
    "11.1": "cabinetry", "11.2": "stone_counters", "11.3": "stone_counters", "11.4": "stone_counters",
    # Interior paint
    "12.1": "paint", "12.2": "paint", "12.3": "paint",
    # MEP trim
    "13.1": "plumbing", "13.2": "plumbing",
    "13.3": "electrical", "13.5": "electrical",
    "13.4": "hvac",
    "13.6": "appliances",
    # Exterior finish
    "14.1": "paint",
    "14.2": "trim_finish",
    "14.3": "concrete", "14.4": "concrete",
    "14.5": "pool_spa", "14.6": "pool_spa", "14.7": "pool_spa", "14.8": "pool_spa",
    "14.9": "fencing", "14.10": "landscape", "14.11": "landscape",
    # Closeout
    "15.1": "punch", "15.2": "punch", "15.3": "cleaning", "15.4": "inspections",
    "15.5": "preconstruction", "15.6": "preconstruction",
}


def build_alias_lookup() -> list[tuple[re.Pattern, str]]:
    """Compile alias regexes; longest aliases first so 'jeff watts' matches before 'watts'."""
    pairs = []
    for canonical, aliases in SUB_ALIASES.items():
        for a in aliases:
            pairs.append((a.lower(), canonical))
    pairs.sort(key=lambda x: -len(x[0]))
    out = []
    for alias, canonical in pairs:
        pattern = r'\b' + re.escape(alias).replace(r'\ ', r'\s+') + r'\b'
        out.append((re.compile(pattern, re.IGNORECASE), canonical))
    return out


ALIAS_LOOKUP = build_alias_lookup()


def extract_numbered_lines(notes: str) -> list[str]:
    """Pull '1. <text>', '1) <text>', '1 <text>' style lines from notes.
    Some BT logs have inconsistent numbering ('1.', '2 Metro' with no period).
    The pattern catches digit + (period|paren|space) followed by content."""
    out = []
    lines = notes.split("\n")
    cur_text: list[str] = []
    in_numbered = False
    for line in lines:
        # Accept "1.", "1)", or "1 " (digit followed by period/paren/space + alpha char)
        # The trailing alpha char is required to avoid matching things like timestamps.
        m = re.match(r"^\s*(\d+)[\.\)]\s*(.*)$", line)
        if not m:
            # Try "1 [Capital letter]" form (e.g., "2 Metro worked on...")
            # Require at least one alpha char so we don't grab timestamps "10 30"
            m_loose = re.match(r"^\s*(\d{1,2})\s+([A-Za-z][A-Za-z0-9 ].*)$", line)
            if m_loose:
                # Avoid years (4-digit), avoid "1 Inspection" header words below
                num = int(m_loose.group(1))
                if num <= 30:  # reasonable line number range
                    rest = m_loose.group(2)
                    if not re.match(r"^(Inspection|Delivery|Other Notable|Discussion|Total|Absent|Activity|Daily|Deliveries|Inspections|Discussions)", rest, re.I):
                        m = m_loose
        if m:
            if cur_text:
                out.append(" ".join(cur_text).strip())
            cur_text = [m.group(2)]
            in_numbered = True
        elif in_numbered:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^(Inspection|Delivery|Other Notable|Notable Discussion|Discussion|Total Work Force|Number of Crews|Absent|Activity Summary|Daily Manpower|Jobsite Activity|Deliveries|Inspections|Discussions/Events)", stripped, re.I):
                if cur_text:
                    out.append(" ".join(cur_text).strip())
                cur_text = []
                in_numbered = False
            else:
                cur_text.append(stripped)
    if cur_text:
        out.append(" ".join(cur_text).strip())
    return out


def line_to_subs(line: str, present_subs: set[str]) -> tuple[list[str], str]:
    """Return (sub_list, attribution_method): 'name' | 'role' | 'none'."""
    matched = set()
    line_low = line.lower()
    for rx, canonical in ALIAS_LOOKUP:
        if canonical in present_subs and rx.search(line_low):
            matched.add(canonical)
    if matched:
        return list(matched), "name"

    for rx, trade in ROLE_PATTERNS:
        if rx.search(line_low):
            candidates = TRADE_TO_SUBS.get(trade, [])
            on_site = [c for c in candidates if c in present_subs]
            for s in on_site:
                matched.add(s)
    if matched:
        return list(matched), "role"

    return [], "none"


def is_generic_line(text: str) -> bool:
    """True if the text is too generic to attribute on its own — needs tag disambiguation."""
    if not text or len(text.strip()) < 8:
        return True
    t = text.lower().strip()
    generic_phrases = [
        "onsite", "on site", "on-site", "continued work", "continued",
        "follow up", "follow-up", "followup", "continues to be onsite",
        "is back", "are back", "was back", "were back", "is onsite",
        "are onsite", "was onsite", "were onsite", "punch", "monitoring",
        "checking", "general work", "site visit", "walk through",
    ]
    # Short enough or matches one of these patterns
    if len(t) < 30:
        for p in generic_phrases:
            if p in t:
                return True
    return False


def load_filters() -> set[str]:
    with open(FILTERS_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    filtered = set()
    for bucket in ("hard_delete", "external_entities", "inspection_authorities"):
        for entry in cfg.get(bucket, []):
            filtered.add(entry["name"])
    return filtered


def load_keywords() -> list[dict]:
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    phases = cfg.get("phases", [])
    for p in phases:
        patterns = p.get("keywords", []) or []
        p["_compiled"] = [(pat, re.compile(pat, re.IGNORECASE)) for pat in patterns]
    return phases


def load_rejections() -> dict:
    """Load cross-trade rejection YAML. Expand phase_groups within rejections + allowlists."""
    with open(REJECTIONS_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    groups = {k: [str(c) for c in v] for k, v in (cfg.get("phase_groups") or {}).items()}

    def expand(items: list) -> set[str]:
        out: set[str] = set()
        for it in items or []:
            s = str(it).strip()
            # Strip trailing comments/spaces — items come from YAML with sometimes inline " 1.4    # Site Grading"
            # handled by yaml parser already; defensive split on space here:
            s_token = s.split()[0] if s else s
            if s_token in groups:
                for code in groups[s_token]:
                    out.add(str(code))
            else:
                # Check if it's an inline comment-stripped phase code
                out.add(s_token)
        return out

    expanded_modal = {}
    for trade, rules in (cfg.get("modal_trade_rejections") or {}).items():
        forbidden = rules.get("forbidden") or []
        expanded_modal[trade] = expand(forbidden)

    expanded_allowlist = {}
    conditional_codes_map: dict[str, dict[str, list[str]]] = {}
    for sub, rules in (cfg.get("multi_trade_allowlist") or {}).items():
        if rules is None:
            expanded_allowlist[sub] = {"allow_all": False, "phases": set()}
            continue
        if rules.get("allow_all"):
            expanded_allowlist[sub] = {"allow_all": True, "phases": set()}
        else:
            allow = rules.get("allow") or []
            expanded_allowlist[sub] = {"allow_all": False, "phases": expand(allow)}
        # conditional codes
        cc = rules.get("conditional_codes") or []
        if cc:
            for entry in cc:
                code = str(entry.get("code"))
                kws = entry.get("require_keyword") or []
                conditional_codes_map.setdefault(sub, {})[code] = [k.lower() for k in kws]

    force_modal = {}
    for sub, rules in (cfg.get("force_modal_trade") or {}).items():
        if rules and rules.get("modal"):
            force_modal[sub] = rules["modal"]

    require_text_signal = set(str(c) for c in (cfg.get("require_text_signal") or []))

    return {
        "phase_groups": groups,
        "modal_trade_rejections": expanded_modal,
        "multi_trade_allowlist": expanded_allowlist,
        "conditional_codes": conditional_codes_map,
        "force_modal_trade": force_modal,
        "require_text_signal": require_text_signal,
    }


def match_phase_for_text(text: str, phases: list[dict]) -> list[dict]:
    """Return list of phase matches for given text, sorted by specificity."""
    matches = []
    for p in phases:
        kw_hits = []
        max_hit_len = 0
        for raw_pat, rx in p["_compiled"]:
            for m in rx.finditer(text):
                hit = m.group(0)
                kw_hits.append(hit)
                if len(hit) > max_hit_len:
                    max_hit_len = len(hit)
        if kw_hits:
            matches.append({
                "code": p["code"],
                "name": p["name"],
                "stage": p.get("stage"),
                "matched_keywords": list(dict.fromkeys(kw_hits))[:5],
                "score": max_hit_len,
                "source": "text",
            })
    matches.sort(key=lambda m: -m["score"])
    return matches


def match_phase_for_tags(tags: list[str], phases: list[dict]) -> list[dict]:
    """Return phase matches based on parent_group_activities tag_hints.
    NOTE: This returns ALL hints, including multi-phase tags. Caller filters to single-phase."""
    matches = []
    for p in phases:
        tag_hints = p.get("tag_hints", []) or []
        if not tag_hints:
            continue
        hits = [t for t in tags if t in tag_hints]
        if hits:
            matches.append({
                "code": p["code"],
                "name": p["name"],
                "stage": p.get("stage"),
                "matched_keywords": [f"tag:{h}" for h in hits],
                "score": 1,
                "source": "tag_hint",
            })
    return matches


def derive_modal_trade(sub: str, sub_text_phases: dict, force_modal: dict) -> str:
    """Compute the sub's modal_trade category from their dominant Pass 1 phases.
    force_modal_trade takes precedence."""
    if sub in force_modal:
        return force_modal[sub]
    cnt = sub_text_phases.get(sub, Counter())
    if not cnt:
        return ""
    # Aggregate counts by trade category
    trade_cnt: Counter = Counter()
    for code, n in cnt.items():
        trade = PHASE_TO_TRADE.get(code, "")
        if trade:
            trade_cnt[trade] += n
    if not trade_cnt:
        return ""
    return trade_cnt.most_common(1)[0][0]


def is_phase_forbidden(modal_trade: str, candidate_phase: str, sub: str,
                       rejections: dict) -> bool:
    """True if the candidate phase is forbidden for this sub's modal_trade,
    after applying multi_trade_allowlist overrides."""
    if not modal_trade:
        return False
    forbidden = rejections["modal_trade_rejections"].get(modal_trade, set())
    if str(candidate_phase) not in forbidden:
        return False
    # Forbidden — but check allowlist
    allow = rejections["multi_trade_allowlist"].get(sub)
    if allow:
        if allow.get("allow_all"):
            return False
        if str(candidate_phase) in allow.get("phases", set()):
            return False
    return True


def conditional_code_satisfied(sub: str, candidate_phase: str, line_text: str,
                               rejections: dict) -> bool:
    """For conditional_codes (e.g., Sanger 5.1/14.2 require 'deck' keyword),
    return True only if the line text matches a required keyword."""
    sub_cc = rejections["conditional_codes"].get(sub) or {}
    kws = sub_cc.get(str(candidate_phase))
    if not kws:
        return True  # no condition, allow
    text_low = (line_text or "").lower()
    for kw in kws:
        if kw in text_low:
            return True
    return False


def main():
    print(f"[Phase 1 RETRY Classifier v3] Loading inputs...", flush=True)
    filters = load_filters()
    phases = load_keywords()
    rejections = load_rejections()
    print(f"  filters:       {len(filters)} entries to drop")
    print(f"  phases:        {len(phases)} phase codes loaded")
    print(f"  modal_rules:   {len(rejections['modal_trade_rejections'])} modal_trade groups")
    print(f"  allowlist:     {len(rejections['multi_trade_allowlist'])} multi-trade subs")
    print(f"  force_modal:   {len(rejections['force_modal_trade'])} subs with forced modal")
    print(f"  require_text:  {len(rejections['require_text_signal'])} phases")

    with open(SCRAPER_DATA, "r", encoding="utf-8") as f:
        scraper = json.load(f)
    print(f"  scraper:       {scraper.get('totalLogs', '?')} total logs")

    # ---------- Build per-(log, sub) records ----------
    records = []
    line_match_counts: Counter = Counter()
    for job_name, logs in scraper["byJob"].items():
        for log in logs:
            log_id = log.get("logId")
            crews = [c for c in (log.get("crews_clean") or []) if c not in filters]
            if not crews:
                continue
            present_subs = set(crews)
            notes = log.get("notes_full") or log.get("notes") or ""
            tags = log.get("parent_group_activities") or []
            activity_field = log.get("activity") or ""
            other_notable = log.get("other_notable_activities") or ""

            num_lines = extract_numbered_lines(notes)
            sub_to_lines: dict[str, list[str]] = defaultdict(list)
            unmatched_lines = []
            for line in num_lines:
                subs_in_line, method = line_to_subs(line, present_subs)
                if subs_in_line:
                    for s in subs_in_line:
                        sub_to_lines[s].append(line)
                    line_match_counts[f"matched_{method}"] += 1
                else:
                    unmatched_lines.append(line)
                    line_match_counts["matched_none"] += 1
            line_match_counts["lines_total"] += len(num_lines)

            # If only ONE crew on the log, all unmatched lines belong to that crew.
            if len(crews) == 1:
                only_sub = crews[0]
                for line in unmatched_lines:
                    sub_to_lines[only_sub].append(line)
                if not num_lines:
                    sub_to_lines[only_sub].append(notes)

            for sub in crews:
                lines_for_sub = sub_to_lines.get(sub, [])
                rec_text = " \n ".join(lines_for_sub)
                rec = {
                    "logId": log_id,
                    "job": job_name,
                    "date": log.get("date"),
                    "sub": sub,
                    "activity": activity_field,
                    "parent_group_activities": tags,
                    "rec_text": rec_text,
                    "had_sub_line": len(lines_for_sub) > 0,
                    "notes_sample": (lines_for_sub[0] if lines_for_sub else (notes[:160].replace("\n", " ")))[:160],
                    "num_distinct_tags": len(set(tags)),
                }
                records.append(rec)

    print(f"  records:       {len(records)} (sub, log) pairs after filtering")
    total_lines = line_match_counts.get("lines_total", 0)
    if total_lines:
        m_name = line_match_counts.get("matched_name", 0)
        m_role = line_match_counts.get("matched_role", 0)
        m_none = line_match_counts.get("matched_none", 0)
        print(f"  line attribution: total={total_lines}  by_name={m_name} ({m_name/total_lines*100:.1f}%)"
              f"  by_role={m_role} ({m_role/total_lines*100:.1f}%)  unmatched={m_none} ({m_none/total_lines*100:.1f}%)")

    # ---------- Pass 1: text-based classification on sub-line text ----------
    print("\n[Pass 1] High-confidence text matches against per-sub-line text...")
    pass1_matches: list[list[dict]] = []
    for rec in records:
        if rec["had_sub_line"] and rec["rec_text"]:
            text_matches = match_phase_for_text(rec["rec_text"], phases)
            if text_matches:
                top_score = text_matches[0]["score"]
                kept = [m for m in text_matches if m["score"] >= max(4, int(top_score * 0.6))]
                pass1_matches.append(kept)
            else:
                pass1_matches.append([])
        else:
            pass1_matches.append([])
    p1_hits = sum(1 for m in pass1_matches if m)
    print(f"  Pass 1 high-confidence hits: {p1_hits}/{len(records)} = {p1_hits/len(records)*100:.1f}%")

    # ---------- Build sub history from Pass 1 ----------
    sub_text_phases: dict = defaultdict(Counter)
    sub_high_conf_total: Counter = Counter()
    for rec, matches in zip(records, pass1_matches):
        if matches:
            sub_high_conf_total[rec["sub"]] += 1
            for m in matches:
                sub_text_phases[rec["sub"]][m["code"]] += 1

    # Compute each sub's modal_trade
    all_subs = set(rec["sub"] for rec in records)
    sub_modal_trade: dict[str, str] = {}
    for sub in all_subs:
        sub_modal_trade[sub] = derive_modal_trade(sub, sub_text_phases, rejections["force_modal_trade"])

    # Modal phase per sub (used for modal fallback + Rule 1)
    sub_modal_phase: dict[str, str] = {}
    for sub, cnt in sub_text_phases.items():
        if cnt:
            sub_modal_phase[sub] = cnt.most_common(1)[0][0]

    # Print modal_trade summary for top subs
    print("\n  Modal-trade map for top 15 subs by Pass 1 high-conf logs:")
    for sub, n in sub_high_conf_total.most_common(15):
        mt = sub_modal_trade.get(sub, "?")
        modal_phase = sub_modal_phase.get(sub, "?")
        forced = " (forced)" if sub in rejections["force_modal_trade"] else ""
        print(f"    {sub[:50]:50s}  high-conf={n:4d}  modal_trade={mt}{forced}  modal_phase={modal_phase}")

    # ---------- Pass 2 + Pass 3 + Rule 1 + Rule 2 ----------
    print("\n[Pass 2] Tag-disambiguated (gated by Pass 1 history >= 3)...")
    print("[Pass 3] Modal fallback (low_review)...")

    final_results: list[dict] = []
    rejection_log: list[tuple] = []      # for verification audit
    confidence_counter: Counter = Counter()
    rejection_matrix: Counter = Counter()  # (modal_trade, rejected_phase) -> count

    REQUIRE_TEXT_SIGNAL = rejections["require_text_signal"]

    for rec, matches in zip(records, pass1_matches):
        rejected_phases: list[dict] = []
        sub = rec["sub"]
        modal_trade = sub_modal_trade.get(sub, "")
        sub_history = sub_text_phases.get(sub, Counter())
        sub_total_high = sub_high_conf_total.get(sub, 0)

        # ---- Apply cross-trade rejection to Pass 1 matches ----
        # Pass 1 are HIGH text-match hits. Rule 2 still applies (cross-trade
        # rejection is hard — physically impossible). require_text_signal
        # applies at Pass 2, not Pass 1 (Pass 1 IS the text signal).
        kept_pass1 = []
        for m in matches:
            cand = str(m["code"])
            # Cross-trade rejection (Rule 2)
            if is_phase_forbidden(modal_trade, cand, sub, rejections):
                rejection_log.append((sub, cand, m.get("name"), "pass1_text", "cross_trade"))
                rejection_matrix[(modal_trade, cand)] += 1
                rejected_phases.append({
                    "code": cand,
                    "name": m.get("name"),
                    "would_be_pass": "pass1_text",
                    "reason": f"cross_trade_rejection (modal_trade={modal_trade})",
                })
                continue
            # Conditional codes (e.g., Sanger 5.1/14.2 needs "deck" keyword in line)
            if not conditional_code_satisfied(sub, cand, rec["rec_text"], rejections):
                rejection_log.append((sub, cand, m.get("name"), "pass1_text", "conditional_keyword"))
                rejected_phases.append({
                    "code": cand,
                    "name": m.get("name"),
                    "would_be_pass": "pass1_text",
                    "reason": "conditional_code_keyword_not_present",
                })
                continue
            kept_pass1.append(m)

        if kept_pass1:
            # Pass 1 high-confidence
            codes = []
            kws = []
            for m in kept_pass1:
                if m["code"] not in codes:
                    codes.append(m["code"])
                for kw in m["matched_keywords"]:
                    kws.append(f'{m["code"]}::{kw}')
            confidence = "high"
            src = "text"
        else:
            # Pass 2 / Pass 3 / Pass 4 logic begins.
            # First: <3-log sub bypass — these subs skip Pass 2 entirely and route
            # straight to manual_review (we keep their Pass 1 hits if any, but
            # those are already exhausted at this point).
            tag_matches_raw = match_phase_for_tags(rec["parent_group_activities"], phases)
            tags = rec["parent_group_activities"] or []
            num_distinct_tags = len(set(tags))
            line_text = rec["rec_text"] or ""
            line_is_generic = is_generic_line(line_text) or not rec["had_sub_line"]

            # Rule 1 — Multi-phase log de-attribution: if 3+ tags AND line is generic,
            # only attribute the sub's modal phase.
            rule1_applies = (num_distinct_tags >= 3 and line_is_generic)

            chose = None
            chose_source = None
            chose_reason = ""

            # Pass 2: Tag-disambiguated. Requires:
            #   - line is generic
            #   - tag points to ONE specific phase (not multi-phase)
            #   - sub has >=3 high-conf Pass 1 logs for that phase
            #   - candidate phase NOT in require_text_signal
            #   - NOT cross-trade forbidden (after allowlist)
            #   - sub has >=3 high-conf Pass 1 logs total (otherwise bypass)
            if (line_is_generic and not rule1_applies and tag_matches_raw and
                    sub_total_high >= 3):
                # Candidate phases from tags (single-phase tags only)
                # Resolve tag uniqueness — tag must hint at exactly one phase
                # We treat tag_matches_raw as candidates; pick the most-supported one.
                # Each entry has 'code'. Filter by:
                #   1. require_text_signal — exclude
                #   2. cross-trade rejection — exclude
                #   3. conditional codes — exclude if keyword not present
                #   4. sub history >= 3 for this phase
                tag_candidates = []
                for tm in tag_matches_raw:
                    cand = str(tm["code"])
                    if cand in REQUIRE_TEXT_SIGNAL:
                        rejection_log.append((sub, cand, tm.get("name"), "pass2_tag", "require_text_signal"))
                        rejected_phases.append({
                            "code": cand, "name": tm.get("name"),
                            "would_be_pass": "pass2_tag",
                            "reason": "require_text_signal_skip"
                        })
                        continue
                    if is_phase_forbidden(modal_trade, cand, sub, rejections):
                        rejection_log.append((sub, cand, tm.get("name"), "pass2_tag", "cross_trade"))
                        rejection_matrix[(modal_trade, cand)] += 1
                        rejected_phases.append({
                            "code": cand, "name": tm.get("name"),
                            "would_be_pass": "pass2_tag",
                            "reason": f"cross_trade_rejection (modal_trade={modal_trade})"
                        })
                        continue
                    if not conditional_code_satisfied(sub, cand, line_text, rejections):
                        rejection_log.append((sub, cand, tm.get("name"), "pass2_tag", "conditional_keyword"))
                        rejected_phases.append({
                            "code": cand, "name": tm.get("name"),
                            "would_be_pass": "pass2_tag",
                            "reason": "conditional_code_keyword_not_present"
                        })
                        continue
                    sub_phase_count = sub_history.get(cand, 0)
                    if sub_phase_count < 3:
                        rejection_log.append((sub, cand, tm.get("name"), "pass2_tag", "no_history"))
                        rejected_phases.append({
                            "code": cand, "name": tm.get("name"),
                            "would_be_pass": "pass2_tag",
                            "reason": f"no_history (sub has {sub_phase_count} Pass1 logs for this phase, need >=3)"
                        })
                        continue
                    tag_candidates.append((tm, sub_phase_count))

                if tag_candidates:
                    # Pick the candidate with the most history (most-supported)
                    tag_candidates.sort(key=lambda x: -x[1])
                    best_tm, best_n = tag_candidates[0]
                    chose = best_tm
                    chose_source = "tag_disambiguated"
                    chose_reason = f"tag={best_tm['matched_keywords'][0]} sub_history={best_n}"

            elif rule1_applies and sub_total_high >= 3 and sub in sub_modal_phase:
                # Rule 1 — credit modal phase only
                modal = sub_modal_phase.get(sub)
                if modal:
                    # Cross-trade check on modal still applies
                    if not is_phase_forbidden(modal_trade, modal, sub, rejections):
                        if conditional_code_satisfied(sub, modal, line_text, rejections):
                            phase_name = next((p["name"] for p in phases if p["code"] == modal), "?")
                            chose = {
                                "code": modal, "name": phase_name,
                                "matched_keywords": [f"rule1_modal::{modal}"],
                                "source": "rule1_modal",
                            }
                            chose_source = "low_review"
                            chose_reason = "rule1_multi_phase_log_modal_only"

            if chose is None:
                # Pass 3: low_review modal fallback. Requires:
                #   - sub has >=3 Pass 1 high-conf logs (statistical basis for modal)
                #   - cross-trade check passes
                # Per kickoff: tag-absent IS a valid low_review trigger. The sub's modal
                # phase is a defensible default when they're confirmed on-site (in
                # crews_clean) and we have enough Pass 1 history to know what they do.
                if sub_total_high >= 3 and sub in sub_modal_phase:
                    modal = sub_modal_phase[sub]
                    # Cross-trade check
                    if is_phase_forbidden(modal_trade, modal, sub, rejections):
                        rejection_log.append((sub, modal, None, "pass3_modal", "cross_trade"))
                        rejection_matrix[(modal_trade, modal)] += 1
                        rejected_phases.append({
                            "code": modal, "name": None,
                            "would_be_pass": "pass3_modal",
                            "reason": f"cross_trade_rejection (modal_trade={modal_trade})"
                        })
                    elif not conditional_code_satisfied(sub, modal, line_text, rejections):
                        rejected_phases.append({
                            "code": modal, "name": None,
                            "would_be_pass": "pass3_modal",
                            "reason": "conditional_code_keyword_not_present"
                        })
                    else:
                        phase_name = next((p["name"] for p in phases if p["code"] == modal), "?")
                        chose = {
                            "code": modal, "name": phase_name,
                            "matched_keywords": [f"pass3_modal::{modal}"],
                            "source": "pass3_modal",
                        }
                        chose_source = "low_review"
                        chose_reason = f"modal_fallback (sub_history dominant={modal})"

            if chose:
                codes = [chose["code"]]
                kws = [f'{chose["code"]}::{kw}' for kw in chose["matched_keywords"]]
                confidence = chose_source
                src = chose_source
            else:
                codes = []
                kws = []
                confidence = "manual_review"
                src = None

        confidence_counter[confidence] += 1
        final_results.append({
            "logId": rec["logId"],
            "job": rec["job"],
            "date": rec["date"],
            "sub": sub,
            "activity": rec["activity"],
            "parent_group_activities": rec["parent_group_activities"],
            "derived_phase_codes": codes,
            "classification_confidence": confidence,
            "matched_keywords": kws,
            "rejected_phases": rejected_phases,
            "match_source": src,
            "had_sub_line": rec["had_sub_line"],
            "notes_sample": rec["notes_sample"],
            "modal_trade": modal_trade,
        })

    total = len(records)
    print(f"\n[Final] total={total}")
    for k in ("high", "tag_disambiguated", "low_review", "manual_review"):
        n = confidence_counter.get(k, 0)
        print(f"  {k:20s}: {n} ({n/total*100:.2f}%)")

    # ---------- Write derived-phases.json ----------
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": "2026-04-29",
        "source_logs": str(SCRAPER_DATA),
        "total_records": total,
        "summary": {k: confidence_counter.get(k, 0)
                    for k in ("high", "tag_disambiguated", "low_review", "manual_review")},
        "summary_pct": {k: round(confidence_counter.get(k, 0) / total * 100, 2)
                        for k in ("high", "tag_disambiguated", "low_review", "manual_review")},
        "records": final_results,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {OUT_JSON}")

    # ---------- Build per-sub diff ----------
    print("\n[Diff] Building per-sub markdown report...")
    sub_records: dict = defaultdict(list)
    for r in final_results:
        sub_records[r["sub"]].append(r)

    phase_lookup = {p["code"]: p["name"] for p in phases}

    md = []
    md.append("# Sub Reclassification Diff (Phase 1 RETRY)")
    md.append("")
    md.append(f"**Source:** `{SCRAPER_DATA}`  ")
    md.append(f"**Total (sub × log) records after filtering:** {total}  ")
    for k in ("high", "tag_disambiguated", "low_review", "manual_review"):
        n = confidence_counter.get(k, 0)
        md.append(f"**{k}:** {n} ({n/total*100:.2f}%)  ")
    md.append("")
    md.append(f"_Note:_ Phase 1 RETRY uses a 3-pass classifier (sub-line text first, then gated tag disambiguation, then modal fallback). The sub's own line text is the primary source of truth; parent_group_activities tags ONLY disambiguate when the sub has >=3 high-confidence Pass 1 logs for that phase historically. Cross-trade rejections from `config/cross-trade-rejections.yaml` override Pass 2.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Per-Sub Reclassification (grouped by sub, top-5 retags by volume)")
    md.append("")

    sorted_subs = sorted(sub_records.items(), key=lambda x: -len(x[1]))

    for sub, recs in sorted_subs:
        if len(recs) < 3:
            continue
        old_tag_counter: Counter = Counter()
        new_phase_counter: Counter = Counter()
        derivation_samples: dict = defaultdict(list)
        unclassified = 0
        for r in recs:
            for t in r["parent_group_activities"]:
                old_tag_counter[t] += 1
            if r["classification_confidence"] == "manual_review":
                unclassified += 1
            for code in r["derived_phase_codes"]:
                new_phase_counter[code] += 1
                if len(derivation_samples[code]) < 1:
                    derivation_samples[code].append(r["notes_sample"][:120])

        md.append(f"### {sub}")
        md.append("")
        md.append(f"- Logs total: {len(recs)}")
        old_tags_str = ", ".join(f"{t} ({n})" for t, n in old_tag_counter.most_common(3)) or "(none)"
        md.append(f"- Old top tags: {old_tags_str}")
        md.append(f"- Logs in manual_review: {unclassified}")
        md.append(f"- Modal trade (after retry): {sub_modal_trade.get(sub, 'n/a')}")
        md.append("- Top retags (by volume):")
        if not new_phase_counter:
            md.append("    - (no derived phases)")
        else:
            for code, n in new_phase_counter.most_common(5):
                phase_name = phase_lookup.get(code, "?")
                sample = derivation_samples[code][0] if derivation_samples[code] else "(no sample)"
                md.append(f"    - {n:4d} logs  →  **{code} {phase_name}**")
                md.append(f"                   Sample: \"{sample}...\"")
        md.append("")

    # Summary table
    md.append("---")
    md.append("")
    md.append("## Summary table — top 20 phase codes by volume after reclassification")
    md.append("")
    md.append("| Phase code | Name | Logs |")
    md.append("|---|---|---|")
    all_phase_volume: Counter = Counter()
    for r in final_results:
        for c in r["derived_phase_codes"]:
            all_phase_volume[c] += 1
    for code, n in all_phase_volume.most_common(20):
        md.append(f"| {code} | {phase_lookup.get(code, '?')} | {n} |")
    md.append("")

    # Five must-be-zero spot checks
    md.append("---")
    md.append("")
    md.append("## 5 Must-Be-Zero Spot Checks (cross-trade rejection)")
    md.append("")
    must_zero = [
        ("Gator Plumbing", "6.3", "Electrical Rough"),
        ("Metro Electric, LLC", "7.2", "Stucco Scratch Coat"),
        ("Rangel Custom Tile LLC", "1.4", "Site Grading & Pad Prep"),
        ("CoatRite LLC", "14.8", "Pool Equipment & Startup"),
    ]
    for sub_name, code, label in must_zero:
        recs = sub_records.get(sub_name, [])
        n = sum(1 for r in recs if code in r["derived_phase_codes"])
        verdict = "✓ confirmed-0" if n == 0 else f"✗ FAIL: {n} attributions"
        md.append(f"- **{sub_name} → {code} {label}**: {verdict}")
    # Ross Built / 8.3 — must be retagged or in manual_review (not in derived phases for the safety rails sample)
    rb_83 = [r for r in sub_records.get("Ross Built Crew", []) if "8.3" in r["derived_phase_codes"]]
    md.append(f"- **Ross Built Crew → 8.3 Drywall Tape**: {len(rb_83)} attributions remain (was 21 in first run).")
    # Show samples to verify safety rails one specifically
    rb_safety = [r for r in sub_records.get("Ross Built Crew", []) if "safety rail" in (r["notes_sample"] or "").lower() or "safety rails" in (r["notes_sample"] or "").lower()]
    md.append(f"- Ross Built 'safety rails' sample(s): {len(rb_safety)} found. Confidence on those: " + ", ".join(set(r["classification_confidence"] for r in rb_safety)) if rb_safety else "- Ross Built 'safety rails' sample: 0 records explicitly mention 'safety rails' — verified retagged or absorbed.")
    md.append("")

    # Six multi-trade preservation spot checks
    md.append("## 6 Must-Still-Show Multi-Trade Spot Checks")
    md.append("")
    multi_trade = [
        ("ML Concrete, LLC", ["2.1", "2.2", "2.3", "2.7", "2.8", "3.1", "3.3"], "5+ distinct phases"),
        ("DB Welding Inc.", ["3.3", "9.1", "11.1", "13.6"], "metal_fab + stairs + at least 1 more"),
        ("M&J Florida Enterprise LLC", ["7.4", "3.4", "7.5"], "siding + framing + exterior_ceilings"),
        ("Metro Electric, LLC", ["6.3", "13.3", "6.5", "13.5"], "6.3 + 13.3 + low_voltage"),
        ("Gator Plumbing", ["6.1", "13.1", "6.2", "13.2"], "6.1 + 13.1 + gas"),
        ("Rangel Custom Tile LLC", ["10.2", "10.3"], "interior_tile + wood_flooring"),
    ]
    for sub_name, expected_codes, expected_desc in multi_trade:
        recs = sub_records.get(sub_name, [])
        new_phase_counter = Counter()
        for r in recs:
            for c in r["derived_phase_codes"]:
                new_phase_counter[c] += 1
        present_codes = [c for c in expected_codes if new_phase_counter.get(c, 0) > 0]
        missing_codes = [c for c in expected_codes if new_phase_counter.get(c, 0) == 0]
        if sub_name == "ML Concrete, LLC":
            verdict = "✓ confirmed" if len(present_codes) >= 5 else (
                "⚠ partial" if len(present_codes) >= 3 else "✗ over-rejected"
            )
        else:
            verdict = "✓ confirmed" if not missing_codes else (
                "⚠ partial" if len(present_codes) >= max(2, len(expected_codes) - 1) else "✗ over-rejected"
            )
        md.append(f"### {sub_name} — {verdict}")
        md.append(f"- Expected: {expected_desc}")
        md.append(f"- Present: {', '.join(f'{c}({new_phase_counter[c]})' for c in present_codes) or '(none)'}")
        if missing_codes:
            md.append(f"- Missing: {', '.join(missing_codes)}")
        md.append("")

    # Ten original spot checks
    md.append("## 10 Original Spot-Check Sub Verdicts")
    md.append("")
    spot_checks = [
        ("CoatRite LLC", "Waterproofing (NOT Masonry); 2.4 + 10.1"),
        ("ML Concrete, LLC", "Pilings, foundation, slabs, masonry walls, CIP beams"),
        ("Jeff Watts Plastering and Stucco", "7.2/7.3/7.6 stucco scratch+brown+finish (collapsed in Phase 1; Phase 3 splits)"),
        ("Metro Electric, LLC", "6.3 + 13.3 + 6.5 (rough + trim + LV)"),
        ("Gator Plumbing", "6.1 + 13.1 + 6.2 (top-out + trim + gas)"),
        ("Ross Built Crew", "Multi-phase per log (never one trade)"),
        ("DB Welding Inc.", "Metal fab + stair railings + custom hoods (3.3 / 9.1 / 13.6)"),
        ("Rangel Custom Tile LLC", "10.2 + 10.3 (tile + wood flooring)"),
        ("M&J Florida Enterprise LLC", "Siding + framing + exterior ceilings"),
        ("ALL VALENCIA CONSTRUCTION LLC", "Framing + windows + siding"),
    ]
    for sub_name, expected in spot_checks:
        recs = sub_records.get(sub_name, [])
        new_phase_counter = Counter()
        for r in recs:
            for c in r["derived_phase_codes"]:
                new_phase_counter[c] += 1
        top5 = new_phase_counter.most_common(5)
        top5_str = ", ".join(f"{code} ({n})" for code, n in top5) or "(no matches)"
        md.append(f"### {sub_name}")
        md.append(f"- Expected: {expected}")
        md.append(f"- Logs: {len(recs)}")
        md.append(f"- Top derived phases: {top5_str}")
        for code, n in top5[:3]:
            samples = [r["notes_sample"][:140] for r in recs if code in r["derived_phase_codes"]][:2]
            for s in samples:
                md.append(f"  - {code} sample: \"{s}\"")
        md.append("")

    # Detweilers + Architectural Marble explicit
    md.append("---")
    md.append("")
    md.append("## Forced-modal-trade verifications")
    md.append("")
    detw = sub_records.get("Detweilers Propane Gas Service, LLC", [])
    detw_elec_codes = {"6.3", "13.3", "6.5", "13.5", "2.6"}
    detw_elec_count = sum(1 for r in detw for c in r["derived_phase_codes"] if c in detw_elec_codes)
    md.append(f"- **Detweilers Propane Gas Service, LLC → all_electrical attributions:** {detw_elec_count} (must be 0)")
    am = sub_records.get("Architectural Marble Importers, Inc", [])
    am_pool_codes = {"14.5", "14.6", "14.7", "14.8"}
    am_pool_count = sum(1 for r in am for c in r["derived_phase_codes"] if c in am_pool_codes)
    md.append(f"- **Architectural Marble Importers, Inc → all_pool attributions:** {am_pool_count} (must be 0)")
    md.append("")

    with open(OUT_DIFF, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Wrote {OUT_DIFF}")

    # ---------- Top 10 unmatched terms in manual_review ----------
    print("\n[Manual review] Top 10 unmatched terms (boilerplate header tokens filtered):")
    # Drop the BT log header boilerplate so we surface real gaps
    boilerplate = {
        "activity", "summary", "company", "trade", "name", "members", "performed",
        "daily", "manpower", "number", "force", "absent", "list", "scheduled",
        "show", "did", "but", "logs", "log", "log:",
        "inspection", "delivery", "notable", "discussion", "events", "deliveries",
        "inspections", "discussions", "other", "total", "activities", "log",
    }
    manual_text_terms: Counter = Counter()
    for r in final_results:
        if r["classification_confidence"] != "manual_review":
            continue
        text = r.get("notes_sample") or ""
        for w in re.findall(r"[A-Za-z][A-Za-z\-/]{2,}", text.lower()):
            if w in {"the", "and", "for", "with", "are", "was", "were", "will",
                     "all", "any", "this", "that", "from", "have", "has", "had",
                     "their", "they", "them", "his", "her", "its", "our", "out",
                     "into", "which", "who", "what", "where", "when", "why", "how",
                     "been", "being", "site", "onsite", "log", "logs", "today",
                     "yesterday", "tomorrow", "weekend", "monday", "tuesday",
                     "wednesday", "thursday", "friday", "saturday", "sunday",
                     "crew", "crews", "work", "workers", "worked", "working",
                     "continue", "continues", "continued", "back", "after",
                     "before", "during", "while", "more", "less", "than", "also",
                     "still", "just", "some", "another"}:
                continue
            if w in boilerplate:
                continue
            manual_text_terms[w] += 1

    top10_unmatched = manual_text_terms.most_common(10)
    for w, n in top10_unmatched:
        print(f"    {w:20s} {n}")

    # ---------- Cross-trade rejection matrix ----------
    print("\n[Cross-trade rejection matrix] (modal_trade, rejected_phase) -> count:")
    for (mt, ph), n in rejection_matrix.most_common(20):
        print(f"    {mt:20s} {ph:6s} {n}")

    # Stash cross-trade rejection summary so verification can read from JSON
    # Append it to the JSON payload for verification consumption
    payload["rejection_matrix"] = [
        {"modal_trade": mt, "rejected_phase": ph, "count": n}
        for (mt, ph), n in rejection_matrix.most_common()
    ]
    payload["unmatched_top_terms"] = [
        {"term": w, "count": n} for w, n in top10_unmatched
    ]
    payload["sub_modal_trade_map"] = sub_modal_trade
    payload["sub_high_conf_total"] = dict(sub_high_conf_total)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


if __name__ == "__main__":
    main()
