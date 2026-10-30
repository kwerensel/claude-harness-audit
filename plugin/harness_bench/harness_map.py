"""Draw the harness map as an SVG picture, not a table.

Every piece of the harness is its own box, placed by when it reaches the agent:
the agent session sits in the "loaded at launch" zone, inside the "found when
needed" zone, inside the enforced boundary where the guards sit; pieces that
never reach the session sit outside. With an "after" value on any piece, a
second panel with the same layout shows the harness after the plan, and a
"What moved" key lists every piece whose place changed.

Input: the `harness_map` list from findings.json (or a plan's copy of it), each
entry {"piece", "location", "note"?, "before", "after"?}. A note is the box's second line,
at most 22 characters; "note_before" / "note_after" override it on one side. Values are the four in
"The harness map" in the audit skill's lenses.md, or "absent" for a piece that
does not exist on that side.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

VALUES = ("loaded at launch", "found when needed", "enforced", "does not reach", "absent")
SHORT = {"loaded at launch": "launch", "found when needed": "found when needed",
         "enforced": "enforced", "does not reach": "outside", "absent": "absent"}
INK, QUIET, EDGE = "#1F2328", "#5F6368", "#9AA0A6"
BLUE, BLUE_FILL, BLUE_ZONE = "#2E6FD8", "#E8F0FB", "#F5F8FD"
GREEN, GREEN_FILL = "#1E8E3E", "#E6F4EA"
W, CHIP_W, CHIP_H, GAP, ROW = 760, 156, 40, 12, 52


def validate(entries):
    if not isinstance(entries, list) or not entries:
        raise ValueError("harness_map must be a nonempty list")
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("piece"), str) or not e["piece"].strip():
            raise ValueError("Each harness_map entry needs a piece name")
        if e.get("before") not in VALUES:
            raise ValueError(f"{e['piece']}: before must be one of {', '.join(VALUES)}")
        if "after" in e and e["after"] not in VALUES:
            raise ValueError(f"{e['piece']}: after must be one of {', '.join(VALUES)}")
    return entries


def clip(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def chip(kind, x, y, name, note):
    style = {"launch": f'fill="{BLUE_FILL}" stroke="{BLUE}" stroke-width="1.5"',
             "found": f'fill="#FFFFFF" stroke="{EDGE}" stroke-width="1"',
             "guard": f'fill="{GREEN_FILL}" stroke="{GREEN}" stroke-width="2"',
             "out": f'fill="#FFFFFF" stroke="{EDGE}" stroke-width="1" stroke-dasharray="4 3"'}[kind]
    ink = QUIET if kind == "out" else INK
    return (f'<rect x="{x}" y="{y}" width="{CHIP_W}" height="{CHIP_H}" rx="8" {style}/>'
            f'<text x="{x + 12}" y="{y + 17}" font-size="12" font-weight="600" fill="{ink}">{escape(clip(name, 19))}</text>'
            f'<text x="{x + 12}" y="{y + 32}" font-size="11" fill="{QUIET}">{escape(clip(note, 22))}</text>')


def grid(kind, items, left, y0, per_row, side):
    parts = []
    for i, e in enumerate(items):
        parts.append(chip(kind, left + (i % per_row) * (CHIP_W + GAP), y0 + (i // per_row) * ROW,
                          e["piece"], e.get(f"note_{side}") or e.get("note") or e.get("location", "")))
    return "".join(parts), -(-len(items) // per_row) * ROW


def panel(entries, side, heading, y):
    """One panel; returns (svg, height)."""
    pick = lambda value: [e for e in entries if e.get(side) == value]
    launch, found, guards, out = (pick(v) for v in VALUES[:4])
    parts = [f'<text x="24" y="{y + 20}" font-size="14" font-weight="600" fill="{INK}">{escape(heading)}</text>']
    fence = y + 36
    found_top = fence + 36
    found_svg, found_h = grid("found", found, 52, found_top + 28, 4, side)
    launch_top = found_top + 28 + found_h + 8
    launch_svg, launch_h = grid("launch", launch, 92, launch_top + 80, 3, side)
    launch_bottom = launch_top + 80 + launch_h + 4
    found_bottom = launch_bottom + 16
    guard_svg, guard_h = grid("guard", guards, 40, found_bottom + 12, 4, side)
    fence_bottom = found_bottom + 12 + max(guard_h, ROW) + 4
    parts += [
        f'<rect x="24" y="{fence}" width="712" height="{fence_bottom - fence}" rx="12" fill="none" stroke="{GREEN}" stroke-width="2.5"/>',
        f'<text x="40" y="{fence + 22}" font-size="11.5" fill="{QUIET}">Enforced boundary: guards hold whatever the agent does</text>',
        f'<rect x="44" y="{found_top}" width="672" height="{found_bottom - found_top}" rx="10" fill="#FFFFFF" stroke="{EDGE}" stroke-width="1"/>',
        f'<text x="60" y="{found_top + 18}" font-size="11.5" fill="{QUIET}">Found when needed: the agent has to look</text>',
        found_svg,
        f'<rect x="76" y="{launch_top}" width="608" height="{launch_bottom - launch_top}" rx="10" fill="{BLUE_ZONE}" stroke="{BLUE}" stroke-width="1.25"/>',
        f'<text x="92" y="{launch_top + 18}" font-size="11.5" fill="{QUIET}">Loaded at launch: in context from the start</text>',
        f'<rect x="296" y="{launch_top + 28}" width="168" height="40" rx="20" fill="#FFFFFF" stroke="{INK}" stroke-width="1.5"/>',
        f'<text x="380" y="{launch_top + 53}" text-anchor="middle" font-size="13" font-weight="600" fill="{INK}">Agent session</text>',
        launch_svg, guard_svg]
    if not guards:
        parts.append(f'<text x="40" y="{found_bottom + 40}" font-size="11.5" fill="{QUIET}">No guards: nothing holds a rule whatever the agent does</text>')
    out_top = fence_bottom + 36
    parts.append(f'<text x="24" y="{out_top}" font-size="11.5" fill="{QUIET}">Outside: never reaches the session</text>')
    out_svg, out_h = grid("out", out, 24, out_top + 12, 4, side)
    parts.append(out_svg if out else f'<text x="24" y="{out_top + 28}" font-size="11.5" fill="{QUIET}">Nothing</text>')
    return "".join(parts), out_top + 12 + max(out_h, ROW) - y


def moves(entries):
    lines = []
    for e in entries:
        if "after" not in e or e["after"] == e["before"]:
            continue
        if e["before"] == "absent":
            lines.append(f"{e['piece']}: added, {SHORT[e['after']]}")
        elif e["after"] == "absent":
            lines.append(f"{e['piece']}: removed")
        else:
            lines.append(f"{e['piece']}: {SHORT[e['before']]} → {SHORT[e['after']]}")
    return lines


def render(entries, title, before_heading="Before", after_heading="After"):
    validate(entries)
    has_after = any("after" in e for e in entries)
    body, y = [], 96
    svg, h = panel(entries, "before", before_heading, y)
    body.append(svg)
    y += h + 32
    if has_after:
        svg, h = panel(entries, "after", after_heading, y)
        body.append(svg)
        y += h + 24
        lines = moves(entries)
        body.append(f'<text x="24" y="{y + 4}" font-size="13" font-weight="600" fill="{INK}">What moved</text>')
        for i, line in enumerate(lines or ["Nothing changed place"]):
            body.append(f'<text x="24" y="{y + 24 + 18 * i}" font-size="11.5" fill="{INK}">{escape(line)}</text>')
        y += 24 + 18 * max(len(lines), 1)
    legend = [("loaded at launch", f'fill="{BLUE_FILL}" stroke="{BLUE}" stroke-width="1.5"', 24),
              ("found when needed", f'fill="#FFFFFF" stroke="{EDGE}" stroke-width="1"', 164),
              ("guard, enforced", f'fill="{GREEN_FILL}" stroke="{GREEN}" stroke-width="2"', 316),
              ("never reaches the session", f'fill="#FFFFFF" stroke="{EDGE}" stroke-width="1" stroke-dasharray="4 3"', 454)]
    key = "".join(f'<rect x="{x}" y="58" width="14" height="14" rx="3" {style}/>'
                  f'<text x="{x + 20}" y="69" font-size="11.5" fill="{INK}">{label}</text>' for label, style, x in legend)
    height = y + 24
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
            f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" role="img" aria-label="{escape(title)}">'
            f'<rect width="{W}" height="{height}" fill="#FFFFFF"/>'
            f'<text x="24" y="30" font-size="15" font-weight="600" fill="{INK}">{escape(title)}</text>{key}'
            + "".join(body) + "</svg>\n")
