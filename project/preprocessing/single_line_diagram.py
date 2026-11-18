"""Generate an IEEE 118-bus single-line diagram in draw.io format.

Uses exactly the data the SC-DCOPF / OTS-SC-DCOPF notebooks use:
- processed/matpower/{gens,loads,branches,system_meta}.csv (written by pre-processing.ipynb:
  in-service elements only, synchronous condensers with Pmax == 0 dropped, c1 by row position);
- data/matpower/{bus,branch}_data_118-bus.csv only for what the processed files do not carry
  (BASE_KV, bus type, TAP/SHIFT), matched to branch_id with the same status == 1 filter.

Layout: bus positions follow the classic IEEE 118-bus one-line drawing, transcribed by hand
into preprocessing/ieee118_bus_positions.csv (x, y and bar length in reference-image pixels; edit
that file to move a bus). Busbars are horizontal bars, branches are orthogonal (Manhattan)
connectors that leave a bar from its top or bottom edge, towards the other bus.

Cell ids are stable (bus_<n>, br_<branch_id>, gen_<gen_id>, load_<n>), so per-case
highlighting can later be applied to this same file by id.

--layout regions moves the blocks of the three CS3 regions apart so that each one fits in its own
rectangle (internal layout of each region unchanged): region A stays on the left, region B is
shifted right, region C is shifted right and down, below region B. Regions (methodology guide):
A = 1-32, 113-115, 117; C = 80-112; B = all other buses.

Output: figures/ieee118_unifilar.drawio (classic) or figures/ieee118_unifilar_regions.drawio
Run from anywhere:
  python preprocessing/single_line_diagram.py
  python preprocessing/single_line_diagram.py --layout regions
"""

import argparse
import base64
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]          # project/
RAW = ROOT / "data" / "matpower"
PROC = ROOT / "processed" / "matpower"
POSITIONS = Path(__file__).resolve().parent / "ieee118_bus_positions.csv"
OUT = ROOT / "figures" / "ieee118_unifilar.drawio"
OUT_REGIONS = ROOT / "figures" / "ieee118_unifilar_regions.drawio"

# CS3 regions (methodology guide, item 14); B = every other bus
REGION_A = set(range(1, 33)) | {113, 114, 115, 117}
REGION_C = set(range(80, 113))
REGION_GAP = 40                 # gap between region blocks (reference-image px; vertical: x SIZE,
                                # since generators and loads above / below the bars grow with it)


# region rectangles drawn by cs3-renewables/scenario_diagram.py (x SIZE): margin around the
# bus boxes and a band on top for the name; the blocks are kept this far apart
REGION_PAD, REGION_LABEL_H, REGION_SPACE = 28, 44, 30
# --layout regions only: buses moved by hand (reference px) because a long vertical branch leg
# ran through them: 118 (leg of 69-75), 98 (80-97), 116 (68-81), 100 (103-104). Checked with the overlap check
# of cs3-renewables/scenario_diagram.py.
REGION_NUDGE = {118: (20, 0), 98: (25, 0), 116: (-25, 0), 103: (30, 0)}
SEPARATE_REGIONS = False        # set by main() for --layout regions


def region(bus):
    return "A" if bus in REGION_A else "C" if bus in REGION_C else "B"


def separate_regions(xy, lengths, has_gen, has_load):
    """Shift region B right of A and region C right of A and below B, on the final bus boxes,
    so that the three region rectangles (with margin and name band) do not overlap."""
    pad, band = REGION_PAD * SIZE, REGION_LABEL_H * SIZE
    def ext(rg):
        bx = [bus_box(b, xy, lengths, has_gen, has_load) for b in xy if region(b) == rg]
        return (min(v[0] for v in bx), min(v[1] for v in bx),
                max(v[2] for v in bx), max(v[3] for v in bx))
    a, b = ext("A"), ext("B")
    c = ext("C")
    dx = max(0.0, a[2] + 2 * pad + REGION_SPACE - min(b[0], c[0]))
    for bus in xy:
        if region(bus) != "A":
            xy[bus][0] += dx
    b, c = ext("B"), ext("C")
    dy = max(0.0, b[3] + 2 * pad + band + REGION_SPACE - c[1])
    for bus in xy:
        if region(bus) == "C":
            xy[bus][1] += dy
    print(f"Regions kept apart on the final boxes: B and C +{dx:.0f} px right, "
          f"C +{dy:.0f} px down")

# --- drawing parameters ---
# Sized for a printed page: the whole drawing is ~2500 px wide, so on a landscape A4 text
# block (~24 cm) a 20 px label prints at ~7 pt. Export from draw.io as PDF/SVG (vector).
SCALE_X = 4.0                   # reference-image px -> draw.io px (positions)
SCALE_Y = 4.6
SCALE_LEN = 3.0                 # reference-image px -> draw.io px (bar length)
MARGIN = 60
BAR_H = 10                      # busbar thickness
MIN_BAR = 70                    # minimum busbar length
SLOT = 20                       # min spacing between attachments on the same bar side
END_PAD = 10                    # keep attachments this far from the bar ends
GEN_D = 26                      # generator circle diameter
GEN_GAP = 10                    # stub length between bar and generator / load
LOAD_W, LOAD_H = 18, 14
TRAFO_W, TRAFO_H = 34, 20
SAME_ROW = 45                   # |dy| (draw.io px) under which two buses count as one row
LINE_W = 2                      # branch stroke width
FONT_BUS = 20                   # bus number
FONT_LOAD = 17                  # load value (MW)
FONT_GEN = 18                   # '~' inside the generator
LABEL_W = 42                    # room reserved left of a bar for its number
CLEARANCE = 14                  # min gap between the boxes of two buses
LOAD_LABEL_H = 20               # room reserved below a load triangle for its value
SIZE = 1.0                      # symbol / font factor (set by apply_size)
TIDY = False                    # place texts and transformer symbols on free spots (large size)

# --size large (default of --layout regions): fonts and symbols x2 and the drawing stretched
# vertically, so that on an A4 sheet in portrait the bus numbers print at ~7 pt (normal: ~4 pt)
SIZES = {"normal": (1.0, 4.6), "large": (2.0, 6.9)}       # (symbol factor, SCALE_Y)


def legend_factor():
    """Legend boxes and text scale by half the symbol factor (x1.5 for 'large')."""
    return 1 + (SIZE - 1) / 2


def apply_size(name):
    """Scale fonts, symbols and the vertical spacing (module constants) for a size profile."""
    global SIZE, SCALE_Y, BAR_H, GEN_D, GEN_GAP, LOAD_W, LOAD_H, TRAFO_W, TRAFO_H, LINE_W
    global FONT_BUS, FONT_LOAD, FONT_GEN, LABEL_W, LOAD_LABEL_H, SLOT, TIDY
    f, SCALE_Y = SIZES[name]
    SIZE = f
    TIDY = f != 1
    BAR_H = round(10 * (1 + (f - 1) / 2))            # bars and lines grow by half the factor
    LINE_W = 2 * (1 + (f - 1) / 2)
    LINE_W = int(LINE_W) if LINE_W == int(LINE_W) else round(LINE_W, 1)
    GEN_D, GEN_GAP = round(26 * f), round(10 * (1 + (f - 1) / 2))
    LOAD_W, LOAD_H = round(18 * f), round(14 * f)
    TRAFO_W, TRAFO_H = round(34 * f), round(20 * f)
    FONT_BUS, FONT_LOAD, FONT_GEN = round(20 * f), round(17 * f), round(18 * f)
    LABEL_W, LOAD_LABEL_H = round(42 * f), round(20 * f)
    SLOT = round(20 * min(f, 1.3))

KV_COLORS = {138.0: "#1F4E79", 345.0: "#C0392B", 161.0: "#D68910"}
KV_OTHER = "#7D3C98"
LINE_COLOR = "#7F8C8D"
TRAFO_COLOR = "#2C3E50"
LOAD_COLOR = "#5D6D7E"


# ----------------------------------------------------------------------------- data
def load_data():
    gens = pd.read_csv(PROC / "gens.csv")
    loads = pd.read_csv(PROC / "loads.csv")
    branches = pd.read_csv(PROC / "branches.csv")
    meta = pd.read_csv(PROC / "system_meta.csv").set_index("key")["value"]
    base_mva = float(meta["base_mva"])
    slack_bus = int(meta["slack_bus"])

    bus_raw = pd.read_csv(RAW / "bus_data_118-bus.csv")
    br_raw = pd.read_csv(RAW / "branch_data_118-bus.csv")

    # Same filter as pre-processing.ipynb, so row i <-> branch_id i
    br_raw = br_raw[br_raw["status"] == 1].reset_index(drop=True)
    assert len(br_raw) == len(branches)
    assert (br_raw["fbus"].astype(int).values == branches["from_bus"].values).all()
    assert (br_raw["tbus"].astype(int).values == branches["to_bus"].values).all()
    branches["is_trafo"] = (br_raw["ratio"] != 0) | (br_raw["angle"] != 0)
    branches["tap"] = br_raw["ratio"].values
    branches["rate_mw"] = branches["rate_pu"] * base_mva

    buses = bus_raw[["bus_i", "type", "baseKV"]].rename(columns={"bus_i": "bus"})
    buses["bus"] = buses["bus"].astype(int)
    buses = buses.merge(loads, on="bus", how="left")
    buses["pd_mw"] = buses["pd_pu"] * base_mva
    assert buses.loc[buses["type"] == 3, "bus"].tolist() == [slack_bus]

    gens["pmin_mw"] = gens["pmin_pu"] * base_mva
    gens["pmax_mw"] = gens["pmax_pu"] * base_mva
    return buses, gens, branches, slack_bus


def region_shift(p):
    """Move region B right of A, and region C right of A and below B (reference px)."""
    p = p.astype({"x": float, "y": float})
    half = p["length"] * SCALE_LEN / SCALE_X / 2           # bar half-length in reference px
    label = LABEL_W / SCALE_X                              # bus number left of the bar
    p["x0"], p["x1"] = p["x"] - half - label, p["x"] + half
    p["r"] = p["bus"].map(region)
    a, bc = p[p["r"] == "A"], p[p["r"] != "A"]
    dx = a["x1"].max() + REGION_GAP - bc["x0"].min()
    b, c = p[p["r"] == "B"], p[p["r"] == "C"]
    dy = b["y"].max() - c["y"].min() + REGION_GAP * SIZE
    p.loc[p["r"] != "A", "x"] += dx
    p.loc[p["r"] == "C", "y"] += dy
    for bus, (nx, ny) in REGION_NUDGE.items():
        p.loc[p["bus"] == bus, "x"] += nx
        p.loc[p["bus"] == bus, "y"] += ny
    print(f"Layout 'regions': B and C shifted right by {dx:.1f}, C shifted down by {dy:.1f} "
          f"(reference px)")
    return p


def load_positions(buses, layout="classic"):
    p = pd.read_csv(POSITIONS)
    missing = set(buses["bus"]) - set(p["bus"])
    assert not missing, f"Buses without a position in {POSITIONS.name}: {sorted(missing)}"
    if layout == "regions":
        p = region_shift(p)
    return {int(r.bus): (r.x * SCALE_X + MARGIN, r.y * SCALE_Y + MARGIN, r.length * SCALE_LEN)
            for r in p.itertuples(index=False)}


# ------------------------------------------------------------------- attachment slots
def spread(desired, left, right, widths=None):
    """Place sorted desired x positions inside [left, right]: consecutive items at least SLOT
    apart, or (w_i + w_j) / 2 apart when widths are given (tidy mode)."""
    n = len(desired)
    widths = widths or [SLOT] * n
    gap = [max(SLOT, (widths[i] + widths[i + 1]) / 2) for i in range(n - 1)]
    lo = [left + max(0, widths[i] / 2 - END_PAD) for i in range(n)]
    hi = [right - max(0, widths[i] / 2 - END_PAD) for i in range(n)]
    pos = []
    for i, d in enumerate(desired):
        pos.append(max(d, lo[i], pos[-1] + gap[i - 1] if pos else lo[i]))
    for i in range(n - 1, -1, -1):
        upper = hi[i] if i == n - 1 else pos[i + 1] - gap[i]
        pos[i] = min(pos[i], upper)
    return pos


def item_width(key, pd_mw, trafos=()):
    """Room an attachment needs along its bar (tidy mode): generators, loads with their value
    and transformer legs are wider than a plain branch end."""
    if not TIDY:
        return SLOT
    if key[0] == "br":
        return TRAFO_H + 10 if key[1] in trafos else SLOT
    if key[0] == "gen":
        return GEN_D + 8
    return max(LOAD_W, text_size(f"{pd_mw[key[1]]:g}", FONT_LOAD)[0]) + 8


def other_bus(key, bus, branches):
    _, bid, end = key
    r = branches.loc[bid]
    return int(r["to_bus"] if end == "src" else r["from_bus"])


def bus_box(b, xy, lengths, has_gen, has_load):
    """Bounding box of a bus including its number, generator above and load below."""
    x, y = xy[b]
    half = lengths[b] / 2
    up = BAR_H / 2 + (GEN_GAP + GEN_D if b in has_gen else 0)
    down = BAR_H / 2 + (GEN_GAP + LOAD_H + LOAD_LABEL_H if b in has_load else 0)
    if TIDY:                                # the number is taller than a bare bar
        up, down = max(up, 0.6 * FONT_BUS), max(down, 0.6 * FONT_BUS)
    return x - half - LABEL_W, y - up, x + half, y + down


def resolve_overlaps(xy, lengths, has_gen, has_load, max_iter=500):
    """Iteratively push colliding bus boxes apart along the axis of least overlap."""
    buses = list(xy)
    for _ in range(max_iter):
        moved = False
        boxes = {b: bus_box(b, xy, lengths, has_gen, has_load) for b in buses}
        for i, a in enumerate(buses):
            for b in buses[i + 1:]:
                ax0, ay0, ax1, ay1 = boxes[a]
                bx0, by0, bx1, by1 = boxes[b]
                ox = min(ax1, bx1) - max(ax0, bx0) + CLEARANCE
                oy = min(ay1, by1) - max(ay0, by0) + CLEARANCE
                if ox <= 0.5 or oy <= 0.5:
                    continue
                moved = True
                if oy <= ox:        # separate vertically (keeps the reference columns)
                    s = 1 if xy[b][1] >= xy[a][1] else -1
                    xy[a][1] -= s * (oy / 2 + 1)
                    xy[b][1] += s * (oy / 2 + 1)
                else:
                    s = 1 if xy[b][0] >= xy[a][0] else -1
                    xy[a][0] -= s * (ox / 2 + 1)
                    xy[b][0] += s * (ox / 2 + 1)
                boxes[a] = bus_box(a, xy, lengths, has_gen, has_load)
                boxes[b] = bus_box(b, xy, lengths, has_gen, has_load)
        if not moved:
            return
    raise RuntimeError("Overlap removal did not converge")


def assign_sides(buses, gens, branches, xy):
    """Which bar side (top/bottom) each attachment uses, given bus centre positions."""
    side_items = defaultdict(list)          # (bus, 'top'|'bottom') -> [key]
    for r in branches.itertuples(index=False):
        a, b = r.from_bus, r.to_bus
        ya, yb = xy[a][1], xy[b][1]
        if abs(ya - yb) < SAME_ROW:         # same row: bridge over the top of both bars
            sa = sb = "top"
        else:
            sa, sb = ("bottom", "top") if yb > ya else ("top", "bottom")
        side_items[(a, sa)].append(("br", r.branch_id, "src"))
        side_items[(b, sb)].append(("br", r.branch_id, "tgt"))
    for g in gens.itertuples(index=False):
        side_items[(g.bus, "top")].append(("gen", g.gen_id))
    for bus in buses.itertuples(index=False):
        if bus.pd_mw > 0:
            side_items[(bus.bus, "bottom")].append(("load", bus.bus))
    return side_items


def plan_bars(buses, gens, branches, pos):
    """Decide bar extents and the x of every attachment (branch end, generator, load)."""
    has_gen = set(gens["bus"])
    has_load = set(buses.loc[buses["pd_mw"] > 0, "bus"])
    xy = {b: [pos[b][0], pos[b][1]] for b in buses["bus"]}
    lengths = {b: max(pos[b][2], MIN_BAR) for b in xy}
    pd_mw = dict(zip(buses["bus"], buses["pd_mw"]))
    trafos = set(branches.loc[branches["is_trafo"], "branch_id"]) if "is_trafo" in branches \
        else set()

    # Two passes: sides depend on positions, bar lengths on sides, positions on lengths
    for _ in range(2):
        side_items = assign_sides(buses, gens, branches, xy)
        for bus in xy:
            n = max(len(side_items[(bus, "top")]), len(side_items[(bus, "bottom")]))
            lengths[bus] = max(lengths[bus], (n - 1) * SLOT + 2 * END_PAD)
            if TIDY:                      # wide attachments (generator, load + value)
                for side in ("top", "bottom"):
                    ws = [item_width(k, pd_mw, trafos) for k in side_items[(bus, side)]]
                    lengths[bus] = max(lengths[bus], sum(ws) + 2 * END_PAD)
        # Push apart buses whose boxes (bar + number + generator + load) collide
        resolve_overlaps(xy, lengths, has_gen, has_load)
    if SEPARATE_REGIONS:
        separate_regions(xy, lengths, has_gen, has_load)
    boxes = [bus_box(b, xy, lengths, has_gen, has_load) for b in xy]
    dx = MARGIN - min(bx[0] for bx in boxes)
    dy = MARGIN - min(bx[1] for bx in boxes)
    for b in xy:
        xy[b][0] += dx
        xy[b][1] += dy

    # Desired x of each attachment follows the *final* position of the other bus
    final_x = {b: xy[b][0] for b in xy}
    bars, slot_x = {}, {}
    for bus in buses["bus"]:
        x, y = xy[bus]
        length = lengths[bus]
        left = x - length / 2
        bars[bus] = (left, y - BAR_H / 2, length)
        for side in ("top", "bottom"):
            items = [(key, final_x[other_bus(key, bus, branches)] if key[0] == "br" else x)
                     for key in side_items[(bus, side)]]
            if not items:
                continue
            # parallel circuits share a desired x; branch_id order keeps them side by side
            items.sort(key=lambda it: (it[1], str(it[0])))
            xs = spread([min(max(d, left + END_PAD), left + length - END_PAD) for _, d in items],
                        left + END_PAD, left + length - END_PAD,
                        [item_width(k, pd_mw, trafos) for k, _ in items] if TIDY else None)
            for (key, _), sx in zip(items, xs):
                slot_x[key] = (sx - left, side)       # x relative to the bar's left edge
    obstacles = {b: bus_box(b, xy, lengths, has_gen, has_load) for b in xy}
    return bars, slot_x, obstacles


# ---------------------------------------------------------------------------- routing
TRACK_STEP = 10       # spacing between candidate horizontal tracks (px)
STUB = 14             # minimum vertical leg leaving / entering a bar
SEP = 7               # two collinear segments closer than this count as overlapping


def _overlap(a0, a1, b0, b1):
    return min(max(a0, a1), max(b0, b1)) - max(min(a0, a1), min(b0, b1))


def _hits_box(seg, box, pad=4):
    """Does an axis-aligned segment ((x0, y0), (x1, y1)) cross a bus box?"""
    (x0, y0), (x1, y1) = seg
    bx0, by0, bx1, by1 = box
    if not TIDY:
        bx0 += LABEL_W  # the number label may be crossed; the bar and symbols may not
    return (_overlap(x0, x1, bx0 - pad, bx1 + pad) > 0
            and _overlap(y0, y1, by0 - pad, by1 + pad) > 0)


class Router:
    """Vertical-horizontal-vertical routes with a free horizontal track per branch."""

    def __init__(self, obstacles, zones=()):
        self.obstacles = obstacles
        self.zones = list(zones)       # tidy: generator / load symbols, for every branch
        self.h = []      # placed horizontal segments (y, x0, x1)
        self.v = []      # placed vertical segments   (x, y0, y1)

    def legs(self, pa, pb, yc):
        (xa, ya), (xb, yb) = pa, pb
        return [((xa, ya), (xa, yc)), ((xa, yc), (xb, yc)), ((xb, yc), (xb, yb))]

    def cost(self, segs, own):
        c = 0.0
        for (x0, y0), (x1, y1) in segs:
            if y0 == y1:                                  # horizontal
                for y, a0, a1 in self.h:
                    if abs(y - y0) < SEP and _overlap(x0, x1, a0, a1) > 2:
                        c += 100
                for x, b0, b1 in self.v:                  # crossing a vertical: small cost
                    if min(x0, x1) < x < max(x0, x1) and min(b0, b1) < y0 < max(b0, b1):
                        c += 3
            else:                                         # vertical
                for x, b0, b1 in self.v:
                    if abs(x - x0) < SEP and _overlap(y0, y1, b0, b1) > 2:
                        c += 100
                for y, a0, a1 in self.h:
                    if min(y0, y1) < y < max(y0, y1) and min(a0, a1) < x0 < max(a0, a1):
                        c += 3
            for b, box in self.obstacles.items():
                if b not in own and _hits_box(((x0, y0), (x1, y1)), box):
                    c += 40
            for z in self.zones:
                if _seg_hits(((x0, y0), (x1, y1)), z, pad=3):
                    c += 150                 # worse than two lines overlapping (100)
        return c

    def place(self, segs):
        for (x0, y0), (x1, y1) in segs:
            if y0 == y1:
                self.h.append((y0, x0, x1))
            elif x0 == x1:
                self.v.append((x0, y0, y1))

    def candidates(self, pa, da, pb, db, stub=STUB):
        """Track y values allowed by the leg directions (+1 down, -1 up), best-first."""
        (_, ya), (_, yb) = pa, pb
        if da > 0 and db < 0:
            lo, hi = ya + stub, yb - stub
        elif da < 0 and db > 0:
            lo, hi = yb + stub, ya - stub
        else:                                             # both up (same row): go above
            top = min(ya, yb) - STUB
            return [top - i * TRACK_STEP for i in range(40)]
        if hi < lo:
            return [(ya + yb) / 2]
        mid = (lo + hi) / 2
        out = [mid]
        for i in range(1, 200):
            for y in (mid - i * TRACK_STEP / 2, mid + i * TRACK_STEP / 2):
                if lo <= y <= hi:
                    out.append(y)
            if mid - i * TRACK_STEP / 2 < lo and mid + i * TRACK_STEP / 2 > hi:
                break
        return out

    def route(self, pa, da, pb, db, own):
        best = None
        # Normal legs first; if every track collides, accept shorter legs (small penalty)
        for stub, penalty in ((STUB, 0), (4, 20)):
            for i, yc in enumerate(self.candidates(pa, da, pb, db, stub)):
                segs = self.legs(pa, pb, yc)
                c = self.cost(segs, own) + 0.05 * i + penalty   # prefer the middle track
                if best is None or c < best[0]:
                    best = (c, yc, segs)
                    if c < 1:
                        break
            if best[0] < 1:
                break
        self.place(best[2])
        return best[1], best[0]


def symbol_zones(buses, gens, bars, slot_x):
    """Generator circles and load triangles with their value (absolute boxes)."""
    zones = []
    for g in gens.itertuples(index=False):
        left, top, _ = bars[g.bus]
        cx = left + slot_x[("gen", g.gen_id)][0]
        zones.append((cx - GEN_D / 2, top - GEN_GAP - GEN_D, cx + GEN_D / 2, top))
    for bus in buses.itertuples(index=False):
        if bus.pd_mw > 0:
            left, top, _ = bars[bus.bus]
            cx = left + slot_x[("load", bus.bus)][0]
            w = max(LOAD_W, text_size(f"{bus.pd_mw:g}", FONT_LOAD)[0])
            zones.append((cx - w / 2, top + BAR_H, cx + w / 2,
                          top + BAR_H + GEN_GAP + LOAD_H + FONT_LOAD * 1.15))
    return zones


def route_branches(branches, bars, slot_x, obstacles, zones=()):
    """Return {branch_id: (track_y, points)} with absolute port coordinates."""
    def port_abs(key, bus):
        rel, side = slot_x[key]
        left, top, _ = bars[bus]
        return (left + rel, top if side == "top" else top + BAR_H), (-1 if side == "top" else 1)

    jobs = []
    for r in branches.itertuples(index=False):
        pa, da = port_abs(("br", r.branch_id, "src"), r.from_bus)
        pb, db = port_abs(("br", r.branch_id, "tgt"), r.to_bus)
        jobs.append((r.branch_id, r.from_bus, r.to_bus, pa, da, pb, db))

    router = Router(obstacles, zones)
    # Short spans first: they have the least freedom
    jobs.sort(key=lambda j: abs(j[3][0] - j[5][0]) + abs(j[3][1] - j[5][1]))
    routes, total = {}, 0.0
    for bid, a, b, pa, da, pb, db in jobs:
        yc, c = router.route(pa, da, pb, db, own={a, b})
        total += c
        routes[bid] = (pa, pb, yc)
    return routes, router


# ------------------------------------------------------------- free spots (tidy mode)
NUM_POS = ["left", "right", "top-left", "top-right", "bottom-left", "bottom-right",
           "corner-top-left", "corner-bottom-left", "corner-top-right", "corner-bottom-right"]
LOAD_POS = ["below", "right", "left"]
TR_T = [0.5, 0.4, 0.6, 0.3, 0.7, 0.25, 0.75, 0.2, 0.8, 0.15, 0.85, 0.1, 0.9]


def text_size(txt, font, bold=False):
    """Approximate rendered size of a one-line label (draw.io default font)."""
    return len(txt) * font * (0.62 if bold else 0.56), font * 1.15


def number_box(pos, left, top, length, txt):
    """Box of a bus number for a position around its bar (absolute coordinates)."""
    w, h = text_size(txt, FONT_BUS, bold=True)
    mid = top + BAR_H / 2
    if pos == "left":
        return left - 4 - w, mid - h / 2, left - 4, mid + h / 2
    if pos == "right":
        return left + length + 4, mid - h / 2, left + length + 4 + w, mid + h / 2
    if pos.startswith("corner-"):                 # diagonal, outside a corner of the bar
        _, vert, horiz = pos.split("-")
        x0 = left - 2 - w if horiz == "left" else left + length + 2
        y0 = top - h if vert == "top" else top + BAR_H
        return x0, y0, x0 + w, y0 + h
    vert, horiz = pos.split("-")
    y0 = top - 2 - h if vert == "top" else top + BAR_H + 2
    x0 = left if horiz == "left" else left + length - w
    return x0, y0, x0 + w, y0 + h


def number_style(pos):
    if pos == "left":
        return dict(labelPosition="left", verticalLabelPosition="middle", align="right",
                    verticalAlign="middle", spacingRight="4")
    if pos == "right":
        return dict(labelPosition="right", verticalLabelPosition="middle", align="left",
                    verticalAlign="middle", spacingLeft="4")
    if pos.startswith("corner-"):
        _, vert, horiz = pos.split("-")
        return dict(labelPosition=horiz, verticalLabelPosition=vert,
                    align="right" if horiz == "left" else "left",
                    verticalAlign="bottom" if vert == "top" else "top", spacing="0",
                    **({"spacingRight": "2"} if horiz == "left" else {"spacingLeft": "2"}))
    vert, horiz = pos.split("-")
    extra = {"spacingBottom": "2"} if vert == "top" else {"spacingTop": "2"}
    return dict(labelPosition="center", verticalLabelPosition=vert, align=horiz,
                verticalAlign="bottom" if vert == "top" else "top", spacing="0", **extra)


def load_value_box(pos, tri, txt):
    """Box of a load value around its triangle tri = (x0, y0, x1, y1)."""
    w, h = text_size(txt, FONT_LOAD)
    x0, y0, x1, y1 = tri
    if pos == "below":
        cx = (x0 + x1) / 2
        return cx - w / 2, y1 - 2, cx + w / 2, y1 - 2 + h
    cy = (y0 + y1) / 2
    if pos == "right":
        return x1 + 3, cy - h / 2, x1 + 3 + w, cy + h / 2
    return x0 - 3 - w, cy - h / 2, x0 - 3, cy + h / 2


def load_value_style(pos):
    if pos == "below":
        return dict(labelPosition="center", verticalLabelPosition="bottom", align="center",
                    verticalAlign="top", spacingTop="-2")
    if pos == "right":
        return dict(labelPosition="right", verticalLabelPosition="middle", align="left",
                    verticalAlign="middle", spacing="0", spacingLeft="3")
    return dict(labelPosition="left", verticalLabelPosition="middle", align="right",
                verticalAlign="middle", spacing="0", spacingRight="3")


def point_at(pts, t):
    """Point at fraction t of a polyline's length and whether that segment is horizontal."""
    segs = list(zip(pts, pts[1:]))
    lens = [abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in segs]
    target, acc = t * sum(lens), 0.0
    for (p, q), ln in zip(segs, lens):
        if ln > 0 and acc + ln >= target:
            u = (target - acc) / ln
            return (p[0] + u * (q[0] - p[0]), p[1] + u * (q[1] - p[1])), abs(q[1] - p[1]) < 1e-6
        acc += ln
    return pts[-1], False


def trafo_box(pts, t):
    (x, y), horizontal = point_at(pts, t)
    w, h = (TRAFO_W, TRAFO_H) if horizontal else (TRAFO_H, TRAFO_W)
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2), horizontal


def _boxes_hit(a, b, pad=2):
    return (min(a[2], b[2]) - max(a[0], b[0]) > -pad
            and min(a[3], b[3]) - max(a[1], b[1]) > -pad)


def _seg_hits(seg, box, pad=2):
    (x0, y0), (x1, y1) = seg
    return (min(max(x0, x1), box[2] + pad) - max(min(x0, x1), box[0] - pad) >= 0
            and min(max(y0, y1), box[3] + pad) - max(min(y0, y1), box[1] - pad) >= 0)


def branch_polylines(routes):
    """Absolute polyline of every routed branch."""
    polys = {}
    for bid, ((ax, ay), (bx, by), yc) in routes.items():
        polys[bid] = ([(ax, ay), (bx, by)] if abs(ax - bx) < 1
                      else [(ax, ay), (ax, yc), (bx, yc), (bx, by)])
    return polys


def place_free(buses, gens, branches, bars, slot_x, routes):
    """Choose transformer positions along their branch, load-value and bus-number positions,
    each on the spot with fewest overlaps (symbols, texts) and line crossings."""
    polys = branch_polylines(routes)
    segs = [(bid, p, q) for bid, pts in polys.items() for p, q in zip(pts, pts[1:])]

    fixed = []                                           # bars, generators, load triangles
    tri = {}
    for b, (left, top, length) in bars.items():
        fixed.append((left, top, left + length, top + BAR_H))
    for g in gens.itertuples(index=False):
        left, top, _ = bars[g.bus]
        cx = left + slot_x[("gen", g.gen_id)][0]
        fixed.append((cx - GEN_D / 2, top - GEN_GAP - GEN_D, cx + GEN_D / 2, top - GEN_GAP))
    for bus in buses.itertuples(index=False):
        if bus.pd_mw > 0:
            left, top, _ = bars[bus.bus]
            cx = left + slot_x[("load", bus.bus)][0]
            tri[bus.bus] = (cx - LOAD_W / 2, top + BAR_H + GEN_GAP, cx + LOAD_W / 2,
                            top + BAR_H + GEN_GAP + LOAD_H)
            fixed.append(tri[bus.bus])

    def cost(box, placed, skip_branch=None, ignore=None):
        c = 100 * sum(_boxes_hit(box, o) for o in fixed if o is not ignore)
        # texts / transformer symbols already placed: keep a visible gap (no "4 11" -> "411")
        c += 100 * sum(_boxes_hit((box[0] - 0.4 * FONT_BUS, box[1], box[2] + 0.4 * FONT_BUS,
                                   box[3]), o) for o in placed)
        c += 10 * sum(_seg_hits((p, q), box) for bid, p, q in segs if bid != skip_branch)
        return c

    placed, tr_pos, load_pos, num_pos = [], {}, {}, {}
    for r in branches.itertuples(index=False):
        if not r.is_trafo:
            continue
        best = min((cost(trafo_box(polys[r.branch_id], t)[0], placed, r.branch_id) + 0.5 * i, t)
                   for i, t in enumerate(TR_T))
        box, horizontal = trafo_box(polys[r.branch_id], best[1])
        tr_pos[r.branch_id] = (best[1], 0 if horizontal else 90)
        placed.append(box)
    for bus in buses.itertuples(index=False):
        if bus.pd_mw > 0:
            txt = f"{bus.pd_mw:g}"
            best = min((cost(load_value_box(pos, tri[bus.bus], txt), placed,
                             ignore=tri[bus.bus]) + 0.5 * i, pos)
                       for i, pos in enumerate(LOAD_POS))
            load_pos[bus.bus] = best[1]
            placed.append(load_value_box(best[1], tri[bus.bus], txt))
    for bus in buses.itertuples(index=False):
        left, top, length = bars[bus.bus]
        best = min((cost(number_box(pos, left, top, length, str(bus.bus)), placed) + 0.5 * i,
                    pos) for i, pos in enumerate(NUM_POS))
        num_pos[bus.bus] = best[1]
        placed.append(number_box(best[1], left, top, length, str(bus.bus)))
    return tr_pos, load_pos, num_pos


# -------------------------------------------------------------------------- drawing
def style(**kw):
    """draw.io style string; an empty value emits a bare shape key (e.g. 'ellipse;')."""
    return ";".join(k if v == "" else f"{k}={v}" for k, v in kw.items()) + ";"


def trafo_image():
    r = TRAFO_H / 2 - 1.5
    cy = TRAFO_H / 2
    c1, c2 = TRAFO_W / 2 - r * 0.6, TRAFO_W / 2 + r * 0.6
    circles = "".join(f'<circle cx="{c}" cy="{cy}" r="{r}" fill="#FFFFFF"/>' for c in (c1, c2))
    circles += "".join(f'<circle cx="{c}" cy="{cy}" r="{r}" fill="none" stroke="{TRAFO_COLOR}" '
                       f'stroke-width="2.2"/>' for c in (c1, c2))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{TRAFO_W}" height="{TRAFO_H}">'
           f'{circles}</svg>')
    # draw.io convention: "data:image/svg+xml,<base64>" (no ';base64', which would break the style)
    return "data:image/svg+xml," + base64.b64encode(svg.encode()).decode()


class Diagram:
    def __init__(self):
        self.mxfile = ET.Element("mxfile", host="app.diagrams.net")
        self.diagram = ET.SubElement(self.mxfile, "diagram", id="ieee118", name="IEEE 118")
        self.model = ET.SubElement(self.diagram, "mxGraphModel", grid="0", gridSize="10",
                                   guides="1", tooltips="1", connect="1", arrows="0", fold="1",
                                   page="1", pageScale="1", math="0", shadow="0")
        self.root = ET.SubElement(self.model, "root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")

    def _cell(self, cid, label, tooltip, **attrs):
        if tooltip:
            obj = ET.SubElement(self.root, "object", id=cid, label=label, tooltip=tooltip)
            return ET.SubElement(obj, "mxCell", **attrs)
        return ET.SubElement(self.root, "mxCell", id=cid, value=label, **attrs)

    def vertex(self, cid, label, st, x, y, w, h, parent="1", tooltip=None):
        cell = self._cell(cid, label, tooltip, style=st, vertex="1", parent=parent)
        ET.SubElement(cell, "mxGeometry", x=f"{x:.1f}", y=f"{y:.1f}",
                      width=f"{w:.1f}", height=f"{h:.1f}", **{"as": "geometry"})
        return cell

    def edge(self, cid, st, source, target, parent="1", tooltip=None, points=None):
        cell = self._cell(cid, "", tooltip, style=st, edge="1", parent=parent,
                          source=source, target=target)
        geo = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        if points:
            arr = ET.SubElement(geo, "Array", **{"as": "points"})
            for x, y in points:
                ET.SubElement(arr, "mxPoint", x=f"{x:.1f}", y=f"{y:.1f}")
        return cell

    def edge_child(self, cid, st, edge_id, w, h, tooltip=None, pos=0.0):
        """Vertex attached to an edge (moves with it); pos in [-1, 1] along it, 0 = middle."""
        cell = self._cell(cid, "", tooltip, style=st, vertex="1", parent=edge_id,
                          connectable="0")
        geo = ET.SubElement(cell, "mxGeometry", x="0" if pos == 0 else f"{pos:.4f}", y="0", width=f"{w}", height=f"{h}",
                            relative="1", **{"as": "geometry"})
        ET.SubElement(geo, "mxPoint", x=f"{-w / 2}", y=f"{-h / 2}", **{"as": "offset"})

    def write(self, path, page_w, page_h):
        self.model.set("pageWidth", str(int(page_w)))
        self.model.set("pageHeight", str(int(page_h)))
        ET.indent(self.mxfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(self.mxfile).write(path, encoding="utf-8", xml_declaration=True)


def port(slot, bar_len):
    """exit/entry point on a bar for an attachment slot."""
    rel_x, side = slot
    return rel_x / bar_len, (0 if side == "top" else 1), side


def build(buses, gens, branches, slack_bus, pos, out=OUT):
    bars, slot_x, obstacles = plan_bars(buses, gens, branches, pos)
    routes, router = route_branches(branches, bars, slot_x, obstacles,
                                    symbol_zones(buses, gens, bars, slot_x) if TIDY else ())
    tr_pos, load_pos, num_pos = (place_free(buses, gens, branches, bars, slot_x, routes)
                                 if TIDY else ({}, {}, {}))
    d = Diagram()
    bar_id = {b: f"bus_{b}" for b in buses["bus"]}
    trafo_img = trafo_image()
    pair_count = branches.groupby(
        branches[["from_bus", "to_bus"]].min(axis=1).astype(str) + "-"
        + branches[["from_bus", "to_bus"]].max(axis=1).astype(str))["branch_id"].transform("size")

    # 1) branches first, so busbars and symbols are drawn on top of the lines
    for r, k in zip(branches.itertuples(index=False), pair_count):
        sx, sy, sside = port(slot_x[("br", r.branch_id, "src")], bars[r.from_bus][2])
        tx, ty, tside = port(slot_x[("br", r.branch_id, "tgt")], bars[r.to_bus][2])
        st = style(edgeStyle="orthogonalEdgeStyle", rounded="0", html="1", endArrow="none",
                   startArrow="none", strokeColor=LINE_COLOR, strokeWidth=LINE_W,
                   exitX=f"{sx:.4f}", exitY=sy, exitPerimeter="0",
                   entryX=f"{tx:.4f}", entryY=ty, entryPerimeter="0")
        kind = "transformer" if r.is_trafo else "line"
        tip = (f"Branch {r.branch_id}: {r.label} ({kind})\n"
               f"x = {r.x_pu:g} pu\nRATE_A = {r.rate_mw:g} MW"
               + (f"\nTAP = {r.tap:g}" if r.is_trafo else "")
               + ("\nRadial (bridge): excluded from C_T and never switched" if r.is_bridge else "")
               + (f"\nParallel circuit ({k} between these buses)" if k > 1 else ""))
        eid = f"br_{r.branch_id}"
        (ax, ay), (bx, by), yc = routes[r.branch_id]
        straight = abs(ax - bx) < 1           # aligned ports: a single vertical segment
        d.edge(eid, st, bar_id[r.from_bus], bar_id[r.to_bus], tooltip=tip,
               points=None if straight else [(ax, yc), (bx, yc)])
        if r.is_trafo:
            # The symbol sits at the path midpoint: on the horizontal leg if the midpoint
            # falls there, otherwise on a vertical leg.
            l1, l2, l3 = abs(yc - ay), abs(bx - ax), abs(by - yc)
            half = (l1 + l2 + l3) / 2
            rot = 0 if (not straight and l1 <= half <= l1 + l2) else 90
            t = 0.5
            if r.branch_id in tr_pos:                # tidy: free spot along the branch
                t, rot = tr_pos[r.branch_id]
            d.edge_child(f"tr_{r.branch_id}",
                         style(shape="image", image=trafo_img, imageAspect="0",
                               rotation=rot, html="1"),
                         eid, TRAFO_W, TRAFO_H, tooltip=tip, pos=2 * t - 1)

    # 2) busbars with generator / load children
    gens_at = defaultdict(list)
    for g in gens.itertuples(index=False):
        gens_at[g.bus].append(g)

    for bus in buses.itertuples(index=False):
        left, top, length = bars[bus.bus]
        color = KV_COLORS.get(bus.baseKV, KV_OTHER)
        is_slack = bus.bus == slack_bus
        tip = (f"Bus {bus.bus}" + (" (reference / slack)" if is_slack else "")
               + f"\nBASE_KV = {bus.baseKV:g} kV\nPD = {bus.pd_mw:g} MW")
        bid = bar_id[bus.bus]
        if bus.bus in num_pos:
            lab = dict(number_style(num_pos[bus.bus]), lblPos=num_pos[bus.bus])
        else:
            lab = dict(labelPosition="left", verticalLabelPosition="middle", align="right",
                       verticalAlign="middle", spacingRight="4")
        d.vertex(bid, str(bus.bus),
                 style(rounded="0", html="1", fillColor=color, strokeColor=color, **lab,
                       fontStyle="1", fontSize=FONT_BUS, fontColor=color),
                 left, top, length, BAR_H, tooltip=tip)

        for g in gens_at.get(bus.bus, []):
            cx = slot_x[("gen", g.gen_id)][0]
            fill, stroke = ("#F5B041", "#B9770E") if is_slack else ("#D5F5E3", "#1E8449")
            gid = f"gen_{g.gen_id}"
            gtip = (f"Generator {g.gen_id} @ bus {g.bus}" + (" (slack)" if is_slack else "")
                    + f"\nPMIN = {g.pmin_mw:g} MW\nPMAX = {g.pmax_mw:g} MW\nc1 = {g.c1:g} $/MWh")
            d.vertex(gid, "~",
                     style(ellipse="", html="1", fillColor=fill, strokeColor=stroke,
                           strokeWidth="2", fontSize=FONT_GEN, fontStyle="1", fontColor=stroke,
                           verticalAlign="middle", aspect="fixed"),
                     cx - GEN_D / 2, -GEN_GAP - GEN_D, GEN_D, GEN_D, parent=bid, tooltip=gtip)
            d.edge(f"gstub_{g.gen_id}",
                   style(endArrow="none", html="1", strokeColor=stroke, strokeWidth="2",
                         exitX="0.5", exitY="1", exitPerimeter="0",
                         entryX=f"{cx / length:.4f}", entryY="0", entryPerimeter="0"),
                   gid, bid, parent=bid)

        if bus.pd_mw > 0:
            cx = slot_x[("load", bus.bus)][0]
            lid = f"load_{bus.bus}"
            if bus.bus in load_pos:
                lab = dict(load_value_style(load_pos[bus.bus]), lblPos=load_pos[bus.bus])
            else:
                lab = load_value_style("below")
            d.vertex(lid, f"{bus.pd_mw:g}",
                     style(triangle="", direction="south", html="1",
                           fillColor=LOAD_COLOR, strokeColor=LOAD_COLOR, **lab,
                           fontSize=FONT_LOAD, fontColor=LOAD_COLOR),
                     cx - LOAD_W / 2, BAR_H + GEN_GAP, LOAD_W, LOAD_H, parent=bid,
                     tooltip=f"Load @ bus {bus.bus}\nPD = {bus.pd_mw:g} MW")
            # Stub as a thin fixed rectangle, not an edge: with direction=south draw.io rotates
            # the triangle's connection frame, so an edge to its "top centre" lands on its side.
            d.vertex(f"lstub_{bus.bus}", "",
                     style(html="1", fillColor=LOAD_COLOR, strokeColor="none"),
                     cx - 1, BAR_H, 2, GEN_GAP, parent=bid)

    # 3) legend in the empty bottom-left corner of the reference layout
    width = max(l + w for l, _, w in bars.values())
    left_bottom = max(t for l, t, w in bars.values() if l + w / 2 < 0.4 * width)
    lx, ly = MARGIN, left_bottom + 110
    # rows: bus kV levels + generator + slack generator + load + line + transformer + parallel
    n_rows = len(KV_COLORS) + 6
    L = legend_factor()                 # legend text grows less than the network symbols
    row, lw = max(round(34 * L), GEN_D + 8), round(330 * L)
    lh = round(40 * L) + n_rows * row + 8          # title band + rows + bottom padding
    d.vertex("legend", "<b>IEEE 118-bus</b>",
             style(rounded="1", html="1", fillColor="#FFFFFF", strokeColor="#BDC3C7",
                   verticalAlign="top", align="left", spacingLeft="12", spacingTop="6",
                   fontSize=round(20 * L), arcSize="4"),
             lx, ly, lw, lh)
    text = style(text="", html="1", align="left", verticalAlign="middle",
                 fontSize=round(18 * L))
    tx, sx, sw = round(100 * L), 14, round(MIN_BAR * L)   # text x, symbol x, symbol width
    yy = round(40 * L)

    def label(cid, txt):
        d.vertex(cid, txt, text, tx, yy, lw - tx - 8, row - 6, parent="legend")

    for j, (kv, c) in enumerate(KV_COLORS.items()):
        d.vertex(f"lg_kv{j}", "", style(html="1", fillColor=c, strokeColor=c),
                 sx, yy + (row - 6 - BAR_H) / 2, sw, BAR_H, parent="legend")
        label(f"lg_kvt{j}", f"Bus {kv:g} kV")
        yy += row
    for j, (txt, fill, stroke) in enumerate([("Generator", "#D5F5E3", "#1E8449"),
                                             ("Slack generator", "#F5B041", "#B9770E")]):
        d.vertex(f"lg_gen{j}", "~",
                 style(ellipse="", html="1", fillColor=fill, strokeColor=stroke, fontStyle="1",
                       fontSize=FONT_GEN, fontColor=stroke, strokeWidth="2"),
                 sx + (sw - GEN_D) / 2, yy + (row - 6 - GEN_D) / 2, GEN_D, GEN_D, parent="legend")
        label(f"lg_gent{j}", txt)
        yy += row
    d.vertex("lg_load", "", style(triangle="", direction="south", html="1",
                                  fillColor=LOAD_COLOR, strokeColor=LOAD_COLOR),
             sx + (sw - LOAD_W) / 2, yy + (row - 6 - LOAD_H) / 2, LOAD_W, LOAD_H, parent="legend")
    label("lg_loadt", "Load (PD in MW)")
    yy += row
    d.vertex("lg_line", "", style(line="", html="1", strokeColor=LINE_COLOR, strokeWidth=LINE_W),
             sx, yy + (row - 6) / 2 - 2, sw, 4, parent="legend")
    label("lg_linet", "Line")
    yy += row
    d.vertex("lg_tr", "", style(shape="image", image=trafo_img, imageAspect="0", html="1"),
             sx + (sw - TRAFO_W) / 2, yy + (row - 6 - TRAFO_H) / 2, TRAFO_W, TRAFO_H,
             parent="legend")
    label("lg_trt", "Transformer")
    yy += row
    for j in range(2):
        d.vertex(f"lg_par{j}", "", style(line="", html="1", strokeColor=LINE_COLOR,
                                         strokeWidth=LINE_W),
                 sx, yy + (row - 6) / 2 - 7 + j * 9, sw, 4, parent="legend")
    label("lg_part", "Parallel circuits")

    max_y = max(t for _, t, _ in bars.values())
    if SIZE != 1:                                # read by cs3-renewables/scenario_diagram.py
        d.mxfile.set("sizeFactor", f"{SIZE:g}")
    d.write(out, width + MARGIN, max(max_y + 2 * MARGIN, ly + lh + MARGIN))
    return bars


def main():
    ap = argparse.ArgumentParser(
        description="Draw the IEEE 118-bus single-line diagram in draw.io format.",
        epilog="Examples:\n  python preprocessing/single_line_diagram.py\n"
               "  python preprocessing/single_line_diagram.py --layout regions",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", choices=["classic", "regions"], default="classic",
                    help="classic: IEEE 118 drawing (-> figures/ieee118_unifilar.drawio); "
                         "regions: blocks of regions A, B, C moved apart so each fits in a "
                         "rectangle (-> figures/ieee118_unifilar_regions.drawio)")
    ap.add_argument("--size", choices=list(SIZES), default=None,
                    help="normal: fonts/symbols as in the classic figure; large: x2 and stretched "
                         "vertically, readable on an A4 sheet (default: normal for classic, "
                         "large for regions)")
    ap.add_argument("--out", type=Path, default=None, help="output file (default by layout)")
    args = ap.parse_args()
    out = args.out or (OUT if args.layout == "classic" else OUT_REGIONS)
    size = args.size or ("normal" if args.layout == "classic" else "large")
    global SEPARATE_REGIONS
    SEPARATE_REGIONS = args.layout == "regions"
    apply_size(size)
    print(f"Layout '{args.layout}', size '{size}' (fonts/symbols x{SIZE:g}, SCALE_Y {SCALE_Y:g})")

    buses, gens, branches, slack_bus = load_data()
    pos = load_positions(buses, args.layout)
    bars = build(buses, gens, branches, slack_bus, pos, out)
    width = max(l + w for l, _, w in bars.values())
    height = max(t for _, t, _ in bars.values())
    print(f"Buses {len(buses)} | generators {len(gens)} | loads {(buses['pd_mw'] > 0).sum()} | "
          f"branches {len(branches)} ({int(branches['is_trafo'].sum())} transformers)")
    print(f"Drawing extent ~{width:.0f} x {height:.0f} px")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
