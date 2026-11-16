"""Generate an IEEE 118-bus single-line diagram in draw.io format.

Uses exactly the data the SC-DCOPF / OTS-SC-DCOPF notebooks use:
- processed/matpower/{gens,loads,branches,system_meta}.csv (written by pre-processing.ipynb:
  in-service elements only, synchronous condensers with Pmax == 0 dropped, c1 by row position);
- data/matpower/{bus,branch}_data_118-bus.csv only for what the processed files do not carry
  (BASE_KV, bus type, TAP/SHIFT), matched to branch_id with the same status == 1 filter.

Layout: bus positions follow the classic IEEE 118-bus one-line drawing, transcribed by hand
into scripts/ieee118_bus_positions.csv (x, y and bar length in reference-image pixels; edit
that file to move a bus). Busbars are horizontal bars, branches are orthogonal (Manhattan)
connectors that leave a bar from its top or bottom edge, towards the other bus.

Cell ids are stable (bus_<n>, br_<branch_id>, gen_<gen_id>, load_<n>), so per-case
highlighting can later be applied to this same file by id.

Output: figures/ieee118_unifilar.drawio
Run from anywhere:  python scripts/single_line_diagram.py
"""

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


def load_positions(buses):
    p = pd.read_csv(POSITIONS)
    missing = set(buses["bus"]) - set(p["bus"])
    assert not missing, f"Buses without a position in {POSITIONS.name}: {sorted(missing)}"
    return {int(r.bus): (r.x * SCALE_X + MARGIN, r.y * SCALE_Y + MARGIN, r.length * SCALE_LEN)
            for r in p.itertuples(index=False)}


# ------------------------------------------------------------------- attachment slots
def spread(desired, left, right):
    """Place sorted desired x positions inside [left, right] at least SLOT apart."""
    pos = []
    for d in desired:
        pos.append(max(d, left, pos[-1] + SLOT if pos else left))
    for i in range(len(pos) - 1, -1, -1):
        upper = right if i == len(pos) - 1 else pos[i + 1] - SLOT
        pos[i] = min(pos[i], upper)
    return pos


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

    # Two passes: sides depend on positions, bar lengths on sides, positions on lengths
    for _ in range(2):
        side_items = assign_sides(buses, gens, branches, xy)
        for bus in xy:
            n = max(len(side_items[(bus, "top")]), len(side_items[(bus, "bottom")]))
            lengths[bus] = max(lengths[bus], (n - 1) * SLOT + 2 * END_PAD)
        # Push apart buses whose boxes (bar + number + generator + load) collide
        resolve_overlaps(xy, lengths, has_gen, has_load)
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
                        left + END_PAD, left + length - END_PAD)
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
    bx0 += LABEL_W  # the number label may be crossed; the bar and symbols may not
    return (_overlap(x0, x1, bx0 - pad, bx1 + pad) > 0
            and _overlap(y0, y1, by0 - pad, by1 + pad) > 0)


class Router:
    """Vertical-horizontal-vertical routes with a free horizontal track per branch."""

    def __init__(self, obstacles):
        self.obstacles = obstacles
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


def route_branches(branches, bars, slot_x, obstacles):
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

    router = Router(obstacles)
    # Short spans first: they have the least freedom
    jobs.sort(key=lambda j: abs(j[3][0] - j[5][0]) + abs(j[3][1] - j[5][1]))
    routes, total = {}, 0.0
    for bid, a, b, pa, da, pb, db in jobs:
        yc, c = router.route(pa, da, pb, db, own={a, b})
        total += c
        routes[bid] = (pa, pb, yc)
    return routes, router


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

    def edge_child(self, cid, st, edge_id, w, h, tooltip=None):
        """Vertex attached to the midpoint of an edge (moves with the edge)."""
        cell = self._cell(cid, "", tooltip, style=st, vertex="1", parent=edge_id,
                          connectable="0")
        geo = ET.SubElement(cell, "mxGeometry", x="0", y="0", width=f"{w}", height=f"{h}",
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


def build(buses, gens, branches, slack_bus, pos):
    bars, slot_x, obstacles = plan_bars(buses, gens, branches, pos)
    routes, router = route_branches(branches, bars, slot_x, obstacles)
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
            d.edge_child(f"tr_{r.branch_id}",
                         style(shape="image", image=trafo_img, imageAspect="0",
                               rotation=rot, html="1"),
                         eid, TRAFO_W, TRAFO_H, tooltip=tip)

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
        d.vertex(bid, str(bus.bus),
                 style(rounded="0", html="1", fillColor=color, strokeColor=color,
                       labelPosition="left", verticalLabelPosition="middle", align="right",
                       verticalAlign="middle", spacingRight="4", fontStyle="1", fontSize=FONT_BUS,
                       fontColor=color),
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
            d.vertex(lid, f"{bus.pd_mw:g}",
                     style(triangle="", direction="south", html="1",
                           fillColor=LOAD_COLOR, strokeColor=LOAD_COLOR,
                           labelPosition="center", verticalLabelPosition="bottom",
                           align="center", verticalAlign="top", spacingTop="-2",
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
    row, lw = 34, 330
    lh = 40 + n_rows * row + 8          # title band + rows + bottom padding
    d.vertex("legend", "<b>IEEE 118-bus</b>",
             style(rounded="1", html="1", fillColor="#FFFFFF", strokeColor="#BDC3C7",
                   verticalAlign="top", align="left", spacingLeft="12", spacingTop="6",
                   fontSize="20", arcSize="4"),
             lx, ly, lw, lh)
    text = style(text="", html="1", align="left", verticalAlign="middle", fontSize="18")
    tx, sx, sw = 100, 14, MIN_BAR          # text x, symbol x, symbol column width
    yy = 40

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
    d.write(OUT, width + MARGIN, max(max_y + 2 * MARGIN, ly + lh + MARGIN))
    return bars


def main():
    buses, gens, branches, slack_bus = load_data()
    pos = load_positions(buses)
    bars = build(buses, gens, branches, slack_bus, pos)
    width = max(l + w for l, _, w in bars.values())
    height = max(t for _, t, _ in bars.values())
    print(f"Buses {len(buses)} | generators {len(gens)} | loads {(buses['pd_mw'] > 0).sum()} | "
          f"branches {len(branches)} ({int(branches['is_trafo'].sum())} transformers)")
    print(f"Drawing extent ~{width:.0f} x {height:.0f} px")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
