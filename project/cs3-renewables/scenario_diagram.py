"""CS3 single-line diagrams: regions, interconnections and the renewable plants of each scenario.

Reads the base diagram figures/ieee118_unifilar_regions.drawio (written by
`python preprocessing/single_line_diagram.py --layout regions`, where the blocks of the three
regions are moved apart; it is not modified) and writes a multi-page draw.io file,
figures/ieee118_cs3_scenarios.drawio, with:
  - page "Regions": one rectangle per region behind the busbars and the interconnection
    branches of regions A and C drawn thicker, in black;
  - one page per scenario in scenarios/<name>.csv: the same background plus a renewable plant
    symbol (wind turbine and solar panel, illustrative only: the scenarios do not set the
    technology) on every bus of the scenario, and a box with the buses and the bottleneck.
Every page is an A4 sheet (File > Page Setup shows A4): portrait by default, with the drawing
scaled to the page width and placed at the top (room below for a caption); --landscape centres it
on a landscape sheet. With the base drawn at --size large (default of --layout regions), bus numbers
print at about 7.7 pt on the full A4 width in portrait. Each page gets an overlap check (printed):
symbols / texts that overlap, and texts / symbols crossed by a line.

Regions (methodology guide, item 14; defined in preprocessing/single_line_diagram.py):
  A = 1-32, 113-115, 117      interconnection 15-33, 19-34, 30-38, 24-70, 24-72 (ids 43 44 53 108 110)
  C = 80-112                  interconnection 77-80 x2, 79-80, 68-81, 77-82   (ids 122 123 124 125 127)
  B = every other bus (33-79, 116, 118)
The script checks that the branches crossing the region borders are exactly those ten and that
the three region rectangles do not overlap.

Each overlay is its own draw.io layer ("Regions", "CS3 overlay", "Renewables"), so it can be
hidden in draw.io (View > Layers). Export each page from draw.io as PDF/SVG.
--preview DIR also draws each page as PNG with matplotlib (approximate: no transformer symbols,
no legend contents), to check the layout without draw.io.

Usage (from project/):
  python preprocessing/single_line_diagram.py --layout regions      # base diagram, once
  python cs3-renewables/scenario_diagram.py
  python cs3-renewables/scenario_diagram.py --preview cs3-renewables/results/diagram_preview
  python cs3-renewables/scenario_diagram.py --scenarios regional_c regional_a
  python cs3-renewables/scenario_diagram.py --landscape
"""

import argparse
import base64
import copy
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]                     # project/
sys.path.insert(0, str(ROOT / "preprocessing"))
import single_line_diagram as sld  # noqa: E402
from single_line_diagram import region  # noqa: E402

BASE = ROOT / "figures" / "ieee118_unifilar_regions.drawio"
OUT = ROOT / "figures" / "ieee118_cs3_scenarios.drawio"
SCEN_DIR = Path(__file__).resolve().parent / "scenarios"
BRANCHES = ROOT / "processed" / "matpower" / "branches.csv"

SCENARIOS = ["concentrated", "distributed", "regional_c", "regional_a", "near_control"]
INTERCONNECTION = {"A": [43, 44, 53, 108, 110], "C": [122, 123, 124, 125, 127]}

# What each scenario stands for (README / methodology guide, CS3 scenarios table)
SCENARIO_TEXT = {
    "concentrated": "Far south-east, buses 101-112 behind bus 100<br>Bottleneck: local "
                    "(only through bus 100), not the interconnection",
    "distributed": "Locations of Ruiz et al. (2012)<br>Bottleneck: radial buses 87 and 111 "
                   "(not switchable)",
    "regional_c": "Region C, meshed buses without a generator, outside 101-112<br>"
                  "Bottleneck: interconnection of region C (congestion)",
    "regional_a": "Region A, meshed buses without a generator<br>"
                  "Bottleneck: interconnection of region A (N-1 security)",
    "near_control": "Near the load (control)<br>Bottleneck: none (no curtailment up to 50%)",
}

REGION_STYLE = {   # fill, border / label colour
    "A": ("#EAF2FB", "#2471A3"),
    "B": ("#F4F6F6", "#7B7D7D"),
    "C": ("#FEF5E7", "#CA6F1E"),
}
REGION_PAD = 28                # rectangle margin around the bus boxes of a region
REGION_LABEL_H = 44            # band at the top of each rectangle for its name
INTER_COLOR = "#000000"        # interconnections: black (red would read as 345 kV)
INTER_W = 5
ICON_W, ICON_H = 46, 34        # renewable symbol (SVG units; drawn at REN_W x REN_H)
REN_W, REN_H = ICON_W, ICON_H
REN_GAP = 6                    # stub between bar and symbol
REN_STROKE = "#7D6608"
A4_W, A4_H = 827, 1169         # draw.io A4 portrait page (px at 100 %)
PAGE_MARGIN = 40               # drawing units, around the content


# ---------------------------------------------------------------------- renewable icon
def renewable_icon():
    """Wind turbine + solar panel on a light badge (SVG data URI, draw.io convention)."""
    blade = ('<path d="M15 12 Q17 7 15 1.2 Q13.4 7 15 12 Z" fill="#FFFFFF" stroke="#5D6D7E" '
             'stroke-width="0.9" transform="rotate({a} 15 12)"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ICON_W}" height="{ICON_H}" '
        f'viewBox="0 0 {ICON_W} {ICON_H}">'
        f'<rect x="0.75" y="0.75" width="{ICON_W - 1.5}" height="{ICON_H - 1.5}" rx="6" '
        f'fill="#FEF9E7" stroke="{REN_STROKE}" stroke-width="1.5"/>'
        '<path d="M13.6 31 L14.4 13 L15.6 13 L16.4 31 Z" fill="#5D6D7E"/>'
        + "".join(blade.format(a=a) for a in (0, 120, 240))
        + '<circle cx="15" cy="12" r="1.8" fill="#5D6D7E"/>'
        '<line x1="33" y1="26" x2="33" y2="31" stroke="#5D6D7E" stroke-width="1.6"/>'
        '<path d="M22 26 L44 26 L40 14 L26 14 Z" fill="#2E86C1" stroke="#1B4F72" '
        'stroke-width="1"/>'
        '<path d="M29.3 26 L30.7 14 M36.7 26 L35.3 14 M24 20 L42 20" stroke="#FFFFFF" '
        'stroke-width="0.9"/>'
        '</svg>')
    return "data:image/svg+xml," + base64.b64encode(svg.encode()).decode()


REN_IMG = renewable_icon()
REN_STYLE = f"shape=image;image={REN_IMG};imageAspect=0;html=1;"


# ------------------------------------------------------------------------- base geometry
def index(root):
    cells = {}
    for el in root:
        c = el if el.tag == "mxCell" else el.find("mxCell")
        cells[el.get("id")] = (el, c)
    return cells


# base-diagram constants, set from the size factor stored in the base file (set_size)
F = 1.0
BAR_H = GEN_D = GEN_GAP = LABEL_W = LOAD_H = LOAD_LABEL_H = None


def set_size(f):
    """Take the base drawing's symbol sizes and scale this script's own symbols and fonts."""
    global F, BAR_H, GEN_D, GEN_GAP, LABEL_W, LOAD_H, LOAD_LABEL_H
    global REN_W, REN_H, REN_GAP, REGION_PAD, REGION_LABEL_H, INTER_W
    name = next(k for k, (sf, _) in sld.SIZES.items() if sf == f)
    sld.apply_size(name)
    F = f
    BAR_H, GEN_D, GEN_GAP = sld.BAR_H, sld.GEN_D, sld.GEN_GAP
    LABEL_W, LOAD_H, LOAD_LABEL_H = sld.LABEL_W, sld.LOAD_H, sld.LOAD_LABEL_H
    REN_W, REN_H = round(ICON_W * f * 0.8), round(ICON_H * f * 0.8)
    REN_GAP = round(6 * f)
    REGION_PAD, REGION_LABEL_H = round(sld.REGION_PAD * f), round(sld.REGION_LABEL_H * f)
    INTER_W = round(5 * (1 + (f - 1) / 2))
    return name


def fs(px):
    """Font / box size scaled by the size factor."""
    return round(px * F)


def fl(px):
    """Legend size: scaled like the base legend (half the size factor)."""
    return round(px * sld.legend_factor())


def read_base():
    if not BASE.exists():
        sys.exit(f"{BASE} not found: run  python preprocessing/single_line_diagram.py "
                 "--layout regions  first")
    mxfile = ET.parse(BASE).getroot()
    size = set_size(float(mxfile.get("sizeFactor", 1)))
    model = mxfile.find("diagram/mxGraphModel")
    return model, index(model.find("root")), size


def geometry(cells):
    """Busbars, their boxes (bar + number + generator + load) and branch polylines."""
    bars, has_gen, has_load = {}, set(), set()
    for cid, (_, cell) in cells.items():
        g = cell.find("mxGeometry") if cell is not None else None
        if cid.startswith("bus_"):
            bars[int(cid[4:])] = tuple(float(g.get(k)) for k in ("x", "y", "width"))
        elif cid.startswith("gen_"):
            has_gen.add(int(cell.get("parent")[4:]))
        elif cid.startswith("load_"):
            has_load.add(int(cid[5:]))

    boxes = {}
    for b, (x, y, w) in bars.items():
        up = GEN_GAP + GEN_D if b in has_gen else 0
        down = BAR_H + (GEN_GAP + LOAD_H + LOAD_LABEL_H if b in has_load else 0)
        boxes[b] = (x - LABEL_W, y - up, x + w, y + down)

    lines = {}
    for cid, (_, cell) in cells.items():
        if not cid.startswith("br_"):
            continue
        st = dict(kv.split("=", 1) for kv in cell.get("style").strip(";").split(";") if "=" in kv)
        s, t = int(cell.get("source")[4:]), int(cell.get("target")[4:])

        def end(bus, fx, fy):
            x, y, w = bars[bus]
            return x + float(fx) * w, y + float(fy) * BAR_H

        pts = [end(s, st["exitX"], st["exitY"])]
        pts += [(float(p.get("x")), float(p.get("y")))
                for p in cell.findall("mxGeometry/Array/mxPoint")]
        pts.append(end(t, st["entryX"], st["entryY"]))
        lines[int(cid[3:])] = (s, t, pts)
    return bars, boxes, has_gen, has_load, lines


def check_interconnection(lines):
    """The branches crossing a region border must be exactly the declared interconnections."""
    br = pd.read_csv(BRANCHES).set_index("branch_id")
    crossing = sorted(int(i) for i, r in br.iterrows() if region(r.from_bus) != region(r.to_bus))
    declared = sorted(INTERCONNECTION["A"] + INTERCONNECTION["C"])
    assert crossing == declared, f"border branches {crossing} != declared {declared}"
    assert set(declared) <= set(lines)
    return br


def region_rects(bars, boxes):
    rects = {}
    for rg in "ABC":
        bs = [b for b in bars if region(b) == rg]
        rects[rg] = (min(boxes[b][0] for b in bs) - REGION_PAD,
                     min(boxes[b][1] for b in bs) - REGION_PAD - REGION_LABEL_H,
                     max(boxes[b][2] for b in bs) + REGION_PAD,
                     max(boxes[b][3] for b in bs) + REGION_PAD)
    for i, a in enumerate("ABC"):
        for b in "ABC"[i + 1:]:
            ra, rb = rects[a], rects[b]
            assert not (min(ra[2], rb[2]) > max(ra[0], rb[0])
                        and min(ra[3], rb[3]) > max(ra[1], rb[1])), \
                f"region rectangles {a} and {b} overlap: {ra} {rb}"
    return rects


# --------------------------------------------------------------------- renewable symbol
def _hit(seg, box):
    (x0, y0), (x1, y1) = seg
    bx0, by0, bx1, by1 = box
    return (min(max(x0, x1), bx1) - max(min(x0, x1), bx0) > 0
            and min(max(y0, y1), by1) - max(min(y0, y1), by0) > 0)


def place_symbol(bus, bars, items, lines, taken):
    """Free spot for the renewable symbol next to a bar: (x, y relative to the bar, side).
    The box includes the stub to the bar; cost = overlaps with any drawn item (100 each) and
    line crossings (10 each)."""
    x, y, w = bars[bus]
    obstacles = [bx for name, kind, bx, owner in items
                 if not (kind == "bar" and owner == bus)] + taken
    segs = [(p, q) for _, _, pts in lines.values() for p, q in zip(pts, pts[1:])]

    cands = []
    for gap in (REN_GAP, 3 * REN_GAP, 6 * REN_GAP):
        for side, ry in (("top", -gap - REN_H), ("bottom", BAR_H + gap)):
            for k in range(13):                          # 0, 1/12, ..., 1 along the bar
                frac = (0.85, 0.15, 0.5)[k] if k < 3 else (k - 3) / 9
                cands.append((frac * w - REN_W / 2, ry, side))
        cands.append((w + gap, (BAR_H - REN_H) / 2, "right"))
        cands.append((-gap - REN_W, (BAR_H - REN_H) / 2, "left"))
    best = None
    for i, (rx, ry, side) in enumerate(cands):
        x0, y0, x1, y1 = x + rx, y + ry, x + rx + REN_W, y + ry + REN_H
        if side == "top":
            y1 = y - 1                                   # down to the bar (stub)
        elif side == "bottom":
            y0 = y + BAR_H + 1
        elif side == "right":
            x0 = x + w + 1
        else:
            x1 = x - 1
        box = (x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        diag = ((box[0], box[1]), (box[2], box[3]))
        cost = (100 * sum(_hit(diag, o) for o in obstacles)
                + 10 * sum(_hit(sg, box) for sg in segs) + 0.1 * i)
        if best is None or cost < best[0]:
            best = (cost, rx, ry, side, box)
    taken.append(best[4])
    return best[1:4]


# ----------------------------------------------------------------------------- overlays
def style(**kw):
    return ";".join(k if v == "" else f"{k}={v}" for k, v in kw.items()) + ";"


def cell(root, cid, value, st, parent, x, y, w, h, tooltip=None, at=None):
    if tooltip:
        holder = ET.Element("object", id=cid, label=value, tooltip=tooltip)
        c = ET.SubElement(holder, "mxCell", style=st, parent=parent, vertex="1")
    else:
        holder = c = ET.Element("mxCell", id=cid, value=value, style=st, parent=parent,
                                vertex="1")
    ET.SubElement(c, "mxGeometry", x=f"{x:.1f}", y=f"{y:.1f}", width=f"{w:.1f}",
                  height=f"{h:.1f}", **{"as": "geometry"})
    if at is None:
        root.append(holder)
    else:
        root.insert(at, holder)
    return c


def translate(root, dx, dy):
    """Shift every top-level cell (parent '1') of the base drawing."""
    for el in root:
        c = el if el.tag == "mxCell" else el.find("mxCell")
        if c is None or c.get("parent") != "1":
            continue
        g = c.find("mxGeometry")
        if g is None:
            continue
        if c.get("edge") == "1":
            for p in g.findall("Array/mxPoint"):
                p.set("x", f"{float(p.get('x')) + dx:.1f}")
                p.set("y", f"{float(p.get('y')) + dy:.1f}")
        else:
            g.set("x", f"{float(g.get('x')) + dx:.1f}")
            g.set("y", f"{float(g.get('y')) + dy:.1f}")


def build_page(base_model, base_cells, scenario=None, ren_buses=(), landscape=False):
    model = copy.deepcopy(base_model)
    root = model.find("root")
    bars, boxes, _, _, lines = geometry(base_cells)
    rects = region_rects(bars, boxes)

    # --- legend positions (base legend + CS3 legend + scenario box), below region A ---
    lg = root.find(".//mxCell[@id='legend']/mxGeometry")
    # all legends go in the free corner below region A, left of region C
    leg_x, leg_y = rects["A"][0], rects["A"][3] + 40
    lg.set("x", f"{leg_x:.1f}")
    lg.set("y", f"{leg_y:.1f}")
    lw_base = float(lg.get("width"))
    rows = [("A", "Region A (1-32, 113-115, 117)"), ("B", "Region B (33-79, 116, 118)"),
            ("C", "Region C (80-112)"), ("inter", "Interconnection (A and C)")]
    if scenario:
        rows.append(("ren", "Renewable plant (illustrative)"))
    row, lw = max(fl(40), REN_H + 10), fl(430)
    lh = fl(44) + len(rows) * row + 8
    cs3_x, cs3_y = leg_x + lw_base + 30, leg_y
    box_h = fl(170)
    box_x, box_w = leg_x, cs3_x + lw - leg_x
    box_y = leg_y + max(lh, float(lg.get("height"))) + 20
    if cs3_x + lw > rects["C"][0] - 10:
        print(f"  WARNING: legends ({cs3_x + lw:.0f}) reach region C ({rects['C'][0]:.0f})")

    # --- page: content bounding box -> A4 portrait, content at the top, centred ---
    x0 = min(r[0] for r in rects.values()) - 10
    y0 = min(r[1] for r in rects.values()) - 10
    x1 = max(max(r[2] for r in rects.values()), cs3_x + lw) + 10
    y1 = max(max(r[3] for r in rects.values()), box_y + (box_h if scenario else 0),
             leg_y + float(lg.get("height"))) + 10
    cw, ch = x1 - x0 + 2 * PAGE_MARGIN, y1 - y0 + 2 * PAGE_MARGIN
    pw0, ph0 = (A4_H, A4_W) if landscape else (A4_W, A4_H)
    scale = max(cw / pw0, ch / ph0)
    page_w, page_h = pw0 * scale, ph0 * scale
    dx = (page_w - (x1 - x0)) / 2 - x0                  # centred horizontally
    dy = (page_h - (y1 - y0)) / 2 - y0 if landscape else PAGE_MARGIN - y0   # portrait: top
    translate(root, dx, dy)
    model.set("pageWidth", str(pw0))
    model.set("pageHeight", str(ph0))
    model.set("pageScale", f"{scale:.4f}")
    rects = {k: (a + dx, b + dy, c + dx, d + dy) for k, (a, b, c, d) in rects.items()}
    bars = {b: (x + dx, y + dy, w) for b, (x, y, w) in bars.items()}
    boxes = {b: (a + dx, c + dy, e + dx, f + dy) for b, (a, c, e, f) in boxes.items()}
    lines = {k: (s, t, [(px + dx, py + dy) for px, py in pts]) for k, (s, t, pts) in lines.items()}
    cs3_x, cs3_y, box_x, box_y = cs3_x + dx, cs3_y + dy, box_x + dx, box_y + dy

    # --- Regions layer, drawn below the network (inserted before layer "1") ---
    at = list(root).index(root.find("mxCell[@id='1']"))
    root.insert(at, ET.Element("mxCell", id="layer_regions", value="Regions", parent="0"))
    for k, rg in enumerate("ABC"):
        fill, col = REGION_STYLE[rg]
        rx0, ry0, rx1, ry1 = rects[rg]
        cell(root, f"region_{rg}", f"Region {rg}",
             style(rounded="1", arcSize="3", absoluteArcSize="1", html="1", fillColor=fill,
                   strokeColor=col, strokeWidth="2", verticalAlign="top", align="left",
                   spacingLeft="14", spacingTop="4", fontSize=fs(30), fontStyle="1",
                   fontColor=col),
             "layer_regions", rx0, ry0, rx1 - rx0, ry1 - ry0, at=at + 1 + k)

    # --- interconnection branches: same cell and route, black and thicker ---
    for ids in INTERCONNECTION.values():
        for bid in ids:
            c = index(root)[f"br_{bid}"][1]
            st = re.sub(r"strokeColor=[^;]+", f"strokeColor={INTER_COLOR}", c.get("style"))
            c.set("style", re.sub(r"strokeWidth=[^;]+", f"strokeWidth={INTER_W}", st))

    # --- top layer: CS3 legend, renewables, scenario box ---
    root.append(ET.Element("mxCell", id="layer_cs3", value="CS3 overlay", parent="0"))
    if scenario:
        root.append(ET.Element("mxCell", id="layer_ren", value="Renewables", parent="0"))
        taken = []
        items, _ = drawn_items(model)
        for b in ren_buses:
            rx, ry, side = place_symbol(b, bars, items, lines, taken)
            x, y, w = bars[b]
            cell(root, f"ren_{b}", "", REN_STYLE, "layer_ren", x + rx, y + ry, REN_W, REN_H,
                 tooltip=f"Renewable plant @ bus {b} (scenario {scenario}, equal share)")
            stub = style(html="1", fillColor="#5D6D7E", strokeColor="none")
            if side == "left":
                cell(root, f"renstub_{b}", "", stub, "layer_ren",
                     x + rx + REN_W, y + BAR_H / 2 - 1, -rx - REN_W, 2)
            elif side == "top":
                cell(root, f"renstub_{b}", "", stub, "layer_ren",
                     x + rx + REN_W / 2 - 1, y + ry + REN_H, 2, -ry - REN_H)
            elif side == "bottom":
                cell(root, f"renstub_{b}", "", stub, "layer_ren",
                     x + rx + REN_W / 2 - 1, y + BAR_H, 2, ry - BAR_H)
            else:
                cell(root, f"renstub_{b}", "", stub, "layer_ren",
                     x + w, y + BAR_H / 2 - 1, rx - w, 2)

    cell(root, "legend_cs3", "<b>CS3</b>",
         style(rounded="1", html="1", fillColor="#FFFFFF", strokeColor="#BDC3C7",
               verticalAlign="top", align="left", spacingLeft="12", spacingTop="6",
               fontSize=fl(20), arcSize="4"), "layer_cs3", cs3_x, cs3_y, lw, lh)
    text = style(text="", html="1", align="left", verticalAlign="middle", fontSize=fl(18))
    yy = fl(44)
    for k, (kind, label) in enumerate(rows):
        if kind in REGION_STYLE:
            cell(root, f"lgc_s{k}", "", style(rounded="1", html="1",
                                              fillColor=REGION_STYLE[kind][0],
                                              strokeColor=REGION_STYLE[kind][1],
                                              strokeWidth="2"),
                 "legend_cs3", 14, yy + 4, fl(70), row - 14)
        elif kind == "inter":
            cell(root, f"lgc_s{k}", "", style(html="1", fillColor=INTER_COLOR,
                                              strokeColor="none"),
                 "legend_cs3", 14, yy + (row - 6) / 2 - INTER_W / 2, fl(70), INTER_W)
        else:
            cell(root, f"lgc_s{k}", "", REN_STYLE, "legend_cs3",
                 14 + fl(35) - REN_W / 2, yy + (row - 6 - REN_H) / 2, REN_W, REN_H)
        cell(root, f"lgc_t{k}", label, text, "legend_cs3", fl(100), yy, lw - fl(100) - 8, row - 6)
        yy += row

    if scenario:
        buses_txt = ", ".join(str(b) for b in ren_buses)
        cell(root, "scenario_box",
             f"<b>Scenario: {scenario}</b><br>{len(ren_buses)} plants (equal split): "
             f"{buses_txt}<br>{SCENARIO_TEXT.get(scenario, '')}",
             style(rounded="1", html="1", whiteSpace="wrap", fillColor="#FFFFFF",
                   strokeColor=REN_STROKE, strokeWidth="2", verticalAlign="top", align="left",
                   spacingLeft="12", spacingTop="8", spacingRight="12", fontSize=fl(18),
                   arcSize="4"),
             "layer_cs3", box_x, box_y, box_w, box_h)
    return model, page_w, page_h


# ------------------------------------------------------------------------ overlap check
def _style_get(st, key):
    m = re.search(rf"(?:^|;){key}=([^;]+)", st or "")
    return m.group(1) if m else None


def _text_box(txt, font, x_right=None, x_center=None, y_mid=None, y_top=None, bold=False):
    w = len(txt) * font * (0.62 if bold else 0.56)
    h = font * 1.15
    x0 = x_right - w if x_right is not None else x_center - w / 2
    y0 = y_mid - h / 2 if y_mid is not None else y_top
    return (x0, y0, x0 + w, y0 + h)


def _polyline_mid(pts):
    segs = list(zip(pts, pts[1:]))
    lens = [abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in segs]
    half, acc = sum(lens) / 2, 0.0
    for (p, q), ln in zip(segs, lens):
        if acc + ln >= half and ln > 0:
            t = (half - acc) / ln
            return p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
        acc += ln
    return pts[0]


def drawn_items(model):
    """Every symbol and text of a page as (name, kind, box, owner bus or None)."""
    root = model.find("root")
    cells = index(root)
    bars, _, _, _, lines = geometry(cells)
    items = []
    for b, (x, y, w) in bars.items():
        items.append((f"bar {b}", "bar", (x, y, x + w, y + BAR_H), b))
        pos = _style_get(cells[f"bus_{b}"][1].get("style"), "lblPos") or "left"
        items.append((f"number {b}", "text", sld.number_box(pos, x, y, w, str(b)), b))
    for cid, (el, c) in cells.items():
        if c is None or c.get("vertex") != "1" or c.find("mxGeometry") is None:
            continue
        g = c.find("mxGeometry")
        if g.get("relative") == "1" or g.get("width") is None:
            continue
        p = c.get("parent")
        ox = oy = 0.0
        if p in cells and cells[p][1] is not None and cells[p][1].get("vertex") == "1"                 and cells[p][1].find("mxGeometry").get("x") is not None:
            pg = cells[p][1].find("mxGeometry")
            ox, oy = float(pg.get("x")), float(pg.get("y"))
        x, y = ox + float(g.get("x")), oy + float(g.get("y"))
        w, h = float(g.get("width")), float(g.get("height"))
        owner = int(p[4:]) if p and p.startswith("bus_") else None
        if cid.startswith("gen_"):
            items.append((cid, "symbol", (x, y, x + w, y + h), owner))
        elif cid.startswith("load_"):
            items.append((cid, "symbol", (x, y, x + w, y + h), owner))
            val = el.get("label") if el.tag == "object" else c.get("value")
            pos = _style_get(c.get("style"), "lblPos") or "below"
            items.append((f"{cid} value", "text",
                          sld.load_value_box(pos, (x, y, x + w, y + h), val), owner))
        elif cid.startswith("ren_"):
            items.append((cid, "symbol", (x, y, x + w, y + h), int(cid[4:])))
        elif cid in ("legend", "legend_cs3", "scenario_box"):
            items.append((cid, "box", (x, y, x + w, y + h), None))
        elif cid.startswith("region_"):
            tw = len(c.get("value")) * fs(30) * 0.62
            items.append((f"{cid} label", "text",
                          (x + 14, y + 4, x + 14 + tw, y + 4 + fs(30) * 1.15), None))
    for cid, (el, c) in cells.items():
        if cid.startswith("tr_"):
            bid = int(cid[3:])
            t = (float(c.find("mxGeometry").get("x")) + 1) / 2
            items.append((cid, "symbol", sld.trafo_box(lines[bid][2], t)[0], f"br{bid}"))
    return items, lines


def check_overlaps(model, tol=1.0):
    """Pairs of symbols / texts that overlap, and texts / symbols crossed by a branch."""
    items, lines = drawn_items(model)

    def inter(a, b):
        return (min(a[2], b[2]) - max(a[0], b[0]) > tol
                and min(a[3], b[3]) - max(a[1], b[1]) > tol)

    clashes = []
    for i, (na, ka, ba, oa) in enumerate(items):
        for nb, kb, bb, ob in items[i + 1:]:
            if ka == "box" and kb == "box":
                continue
            if oa is not None and oa == ob and ("bar" in (ka, kb) or nb == f"{na} value"):
                continue                     # own bar / own load value touch by design
            if inter(ba, bb):
                clashes.append(f"{na} x {nb}")
    crossed = []
    for na, ka, ba, oa in items:
        if ka not in ("text", "symbol", "box"):
            continue
        for bid, (s, t, pts) in lines.items():
            if na.startswith("tr_") and oa == f"br{bid}":
                continue                     # a transformer sits on its own branch
            if oa in (s, t) and ka == "symbol" and not na.startswith("ren_"):
                continue                     # own stubs
            for p, q in zip(pts, pts[1:]):
                seg = (min(p[0], q[0]) - 0.5, min(p[1], q[1]) - 0.5,
                       max(p[0], q[0]) + 0.5, max(p[1], q[1]) + 0.5)
                if inter(ba, seg):
                    crossed.append(f"{na} / branch {bid}")
                    break
    return clashes, crossed


# ------------------------------------------------------------------------------ preview
def preview(model, page_w, page_h, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    root = model.find("root")
    cells = index(root)
    bars, _, _, _, lines = geometry(cells)
    fig, ax = plt.subplots(figsize=(8.27, 8.27 * page_h / page_w), dpi=150)
    pt = 8.27 * 72 / page_w           # drawing px -> printed pt on the A4 width (true size)
    ax.add_patch(Rectangle((0, 0), page_w, page_h, fill=False, ec="#999999", lw=0.5))

    def absxy(c):
        g = c.find("mxGeometry")
        x, y = float(g.get("x")), float(g.get("y"))
        p = c.get("parent")
        if p in cells and cells[p][1] is not None and cells[p][1].get("vertex") == "1":
            px, py = absxy(cells[p][1])
            x, y = x + px, y + py
        return x, y

    def get(st, key):
        m = re.search(rf"{key}=([^;]+)", st or "")
        return None if not m or m.group(1) == "none" else m.group(1)

    for cid, (el, c) in cells.items():
        if (c is None or c.find("mxGeometry") is None or c.get("edge") == "1"
                or c.find("mxGeometry").get("relative") == "1"):
            continue
        st = c.get("style") or ""
        x, y = absxy(c)
        g = c.find("mxGeometry")
        w, h = float(g.get("width")), float(g.get("height"))
        if cid.startswith("region_") or cid in ("legend", "legend_cs3", "scenario_box"):
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=10",
                                        fc=get(st, "fillColor"), ec=get(st, "strokeColor"),
                                        lw=1, zorder=0 if cid.startswith("region_") else 4))
            if cid.startswith("region_"):
                ax.text(x + 14, y + 8, c.get("value"), ha="left", va="top", fontsize=fs(30) * pt,
                        fontweight="bold", color=get(st, "fontColor"), zorder=1)
            elif cid == "scenario_box":
                ax.text(x + 10, y + 10, re.sub(r"<[^>]+>", "\n", c.get("value")
                                               ).replace("\n\n", "\n"),
                        ha="left", va="top", fontsize=fs(18) * pt, zorder=5)
    for bid, (s, t, pts) in lines.items():
        st = cells[f"br_{bid}"][1].get("style")
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=get(st, "strokeColor"),
                lw=float(get(st, "strokeWidth")) * 0.3, zorder=1)
    for b, (x, y, w) in bars.items():
        col = get(cells[f"bus_{b}"][1].get("style"), "fillColor")
        ax.add_patch(Rectangle((x, y), w, BAR_H, fc=col, ec=col, zorder=2))
    for name, kind, (x0, y0, x1, y1), owner in drawn_items(model)[0]:
        if name.startswith("number "):             # where the generator put it (lblPos)
            col = get(cells[f"bus_{owner}"][1].get("style"), "fillColor")
            ax.text(x1, (y0 + y1) / 2, name[7:], ha="right", va="center",
                    fontsize=sld.FONT_BUS * pt, color=col, fontweight="bold", zorder=3)
        elif name.endswith(" value"):
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, cells[name[:-6]][0].get("label"),
                    ha="center", va="center", fontsize=sld.FONT_LOAD * pt, color="#5D6D7E",
                    zorder=3)
    for cid, (el, c) in cells.items():
        if c is None or c.find("mxGeometry") is None:
            continue
        g = c.find("mxGeometry")
        if g.get("width") is None or g.get("relative") == "1":
            continue
        x, y = absxy(c)
        w, h = float(g.get("width")), float(g.get("height"))
        if cid.startswith("gen_"):
            ax.add_patch(plt.Circle((x + w / 2, y + h / 2), w / 2,
                                    fc=get(c.get("style"), "fillColor"), ec="#1E8449", lw=0.4,
                                    zorder=3))
        elif cid.startswith("load_"):
            ax.add_patch(plt.Polygon([(x, y), (x + w, y), (x + w / 2, y + h)], fc="#5D6D7E",
                                     zorder=3))
        elif cid.startswith("ren_") or (cid.startswith("lgc_s")
                                        and "image=" in (c.get("style") or "")):
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=5",
                                        fc="#FEF9E7", ec=REN_STROKE, lw=0.6, zorder=5))
            k = w / ICON_W
            ax.plot([x + 15 * k, x + 15 * k], [y + 12 * k, y + 31 * k], color="#5D6D7E",
                    lw=0.6, zorder=6)
            ax.add_patch(plt.Polygon([(x + 22 * k, y + 26 * k), (x + 44 * k, y + 26 * k),
                                      (x + 40 * k, y + 14 * k), (x + 26 * k, y + 14 * k)],
                                     fc="#2E86C1", zorder=6))
        elif cid.startswith("renstub_"):
            ax.add_patch(Rectangle((x, y), w, h, fc="#5D6D7E", ec="none", zorder=4))
    ax.set_xlim(0, page_w)
    ax.set_ylim(page_h, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="CS3 single-line diagrams: regions, interconnections and the renewable "
                    "plants of each scenario (draw.io, one A4 page each).",
        epilog="Needs the base diagram first:\n"
               "  python preprocessing/single_line_diagram.py --layout regions\n"
               "Pages: 'Regions' + one per scenario. Output: figures/ieee118_cs3_scenarios.drawio"
               "\n(figures/ieee118_unifilar_regions.drawio is only read).\n\nExamples:\n"
               "  python cs3-renewables/scenario_diagram.py\n"
               "  python cs3-renewables/scenario_diagram.py --preview "
               "cs3-renewables/results/diagram_preview\n"
               "  python cs3-renewables/scenario_diagram.py --scenarios regional_c regional_a\n"
               "  python cs3-renewables/scenario_diagram.py --landscape",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", nargs="+", default=SCENARIOS,
                    help=f"scenarios to draw, one page each (default: {' '.join(SCENARIOS)})")
    ap.add_argument("--out", type=Path, default=OUT, help=f"output .drawio (default: {OUT})")
    ap.add_argument("--landscape", action="store_true",
                    help="A4 landscape pages, drawing centred (default: A4 portrait, drawing at "
                         "the top with room for a caption below)")
    ap.add_argument("--preview", type=Path, default=None,
                    help="also write one approximate PNG per page to this folder (matplotlib)")
    args = ap.parse_args()

    base_model, base_cells, size = read_base()
    bars, boxes, _, _, lines = geometry(base_cells)
    br = check_interconnection(lines)
    rects = region_rects(bars, boxes)
    print(f"Base diagram: {BASE.relative_to(ROOT)} ({len(bars)} buses, {len(lines)} branches, "
          f"size '{size}': fonts/symbols x{F:g})")
    for rg in "ABC":
        n = sum(region(b) == rg for b in bars)
        r = rects[rg]
        print(f"  region {rg}: {n} buses, rectangle {r[2] - r[0]:.0f} x {r[3] - r[1]:.0f} px")
    print("  region rectangles do not overlap")
    for rg, ids in INTERCONNECTION.items():
        names = ", ".join(br.loc[i, "label"] for i in ids)
        cap = (br.loc[ids, "rate_pu"] * 100).sum()
        print(f"  interconnection {rg}: {names} (ids {ids}, {cap:.0f} MW)")

    pages = [("Regions", None, [])]
    for sc in args.scenarios:
        ren = pd.read_csv(SCEN_DIR / f"{sc}.csv")["bus"].astype(int).tolist()
        missing = [b for b in ren if b not in bars]
        assert not missing, f"{sc}: buses {missing} not in the diagram"
        pages.append((sc, sc, ren))

    if args.preview:
        args.preview.mkdir(parents=True, exist_ok=True)
    mxfile = ET.Element("mxfile", host="app.diagrams.net")
    for k, (name, sc, ren) in enumerate(pages):
        model, pw, ph = build_page(base_model, base_cells, scenario=sc, ren_buses=ren,
                                   landscape=args.landscape)
        d = ET.SubElement(mxfile, "diagram", id=f"cs3_{k}", name=name)
        d.append(model)
        by_region = {rg: [b for b in ren if region(b) == rg] for rg in "ABC"}
        detail = "; ".join(f"{rg}: {v}" for rg, v in by_region.items() if v)
        print(f"Page {k + 1} '{name}'" + (f": {len(ren)} renewable buses ({detail})" if sc else "")
              + f" | A4 {'landscape' if args.landscape else 'portrait'}, scale {float(model.get('pageScale')):.2f} "
                f"({pw:.0f} x {ph:.0f} drawing px)")
        clashes, crossed = check_overlaps(model)
        print(f"  overlap check: {len(clashes)} symbol/text overlaps"
              + (f" {clashes}" if clashes else "")
              + f", {len(crossed)} texts/symbols crossed by a line"
              + (f" {crossed}" if crossed else ""))
        if args.preview:
            png = args.preview / f"{k}_{name}.png"
            preview(model, pw, ph, png)
            print(f"  preview -> {png}")

    ET.indent(mxfile)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(mxfile).write(args.out, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
