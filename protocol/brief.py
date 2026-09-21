"""
Morning brief → glasses. Renders the operator card as stereo depth planes.

Three screens, each built as three full-canvas 1-bit layers that differ only in
z. compose_layers() blends them with AND logic, so a layer is a *depth plane*
rather than a positioned sprite:

    CHROME  z=-5  → 0px disparity   rules, brackets, cell borders, meter track
    LABEL   z= 0  → 5px disparity   section titles, indices, units, times
    HERO    z=+4  → 9px disparity   the one value that matters on that screen

The chrome sits at zero parallax so it reads as the surface the card is printed
on; the hero floats forward off it.

Note on z: api_v3 maps z through (z + 5) / 10, so z=-5 is *zero* shift, not
"behind". There is no behind — every plane gets non-negative disparity.

Usage:
    screens = render_brief(BriefInput(...))   # [{"name":.., "layers":[(bmp, z)]}]
"""

from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw

from .bmp import load_font
from .constants import BMP_WIDTH, BMP_HEIGHT

__all__ = ["BriefInput", "Block", "calc_tier", "calc_power", "render_brief"]


# ── Depth planes ──────────────────────────────────────────────────────────────

Z_CHROME = -5.0
Z_LABEL = 0.0
Z_HERO = 4.0

MARGIN = 10


# ── Input ─────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    name: str = ""
    start: str = ""
    end: str = ""

    @property
    def minutes(self) -> int:
        return minutes_between(self.start, self.end)


@dataclass
class BriefInput:
    """Mirrors the morning-card.html form."""
    energy: int = 7
    focus: int = 7
    t_start: str = "06:00"
    t_end: str = "21:00"
    week_priority: str = ""
    one_thing: str = ""
    domain: str = "vision"
    stop_criteria: str = ""
    checks: dict = field(default_factory=dict)
    blocks: list = field(default_factory=list)

    @property
    def window_minutes(self) -> int:
        return minutes_between(self.t_start, self.t_end)

    @property
    def checks_done(self) -> int:
        return sum(1 for v in self.checks.values() if v)


DOMAIN_LABELS = {
    "vision": "Vision Company - HUD XR",
    "masters": "Masters Coursework",
    "fornix": "Fornix - Clinical DB",
    "identity": "Identity Engineering",
    "physical": "Physical Infrastructure",
    "other": "Other",
}

CHECK_KEYS = ["sleep", "gym", "bible", "no_stim", "no_scroll"]
CHECK_LABELS = {
    "sleep": "SLEEP",
    "gym": "GYM",
    "bible": "WORD",
    "no_stim": "STIM",
    "no_scroll": "SCROLL",
}


# ── Calculations (ported from morning-card.html) ──────────────────────────────

def minutes_between(a: str, b: str) -> int:
    if not a or not b:
        return 0
    try:
        ah, am = (int(x) for x in a.split(":"))
        bh, bm = (int(x) for x in b.split(":"))
    except ValueError:
        return 0
    return max(0, (bh * 60 + bm) - (ah * 60 + am))


def fmt_minutes(m: int) -> str:
    h, mm = divmod(m, 60)
    if h == 0:
        return f"{mm}min"
    return f"{h}h" if mm == 0 else f"{h}h {mm}min"


def calc_tier(energy: int, focus: int, total_min: int) -> tuple[str, str]:
    """Returns (tier, subtitle)."""
    score = (energy + focus) / 2
    if score >= 7 and total_min >= 90:
        return "DEEP WORK", "90min blocks - full technical depth"
    if score >= 5 and total_min >= 45:
        return "STRUCTURED", "documentation - review - learning"
    return "MAINTENANCE", "admin - communication - genuine rest"


def calc_power(energy: int, focus: int, checks_done: int) -> dict:
    """Operator Power Index and its three contributing terms.

    Floor is 25, not 0: the base term contributes 20 unconditionally and
    energy/focus cannot go below 1 each.
    """
    resource = ((energy + focus) / 20) * 50
    checks = (checks_done / 5) * 30
    base = 20
    return {
        "resource": round(resource),
        "checks": round(checks),
        "base": base,
        "total": round(resource + checks + base),
    }


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 255)
    return img, ImageDraw.Draw(img)


# Antialiased glyph edges land around 100-180 in L. Thresholding at 64 (as
# render_text_block does) throws those away and small type disintegrates into
# loose dots on the 1-bit panel. 176 keeps the edge pixels as ink.
INK_THRESHOLD = 176


def _to_bmp(img: Image.Image) -> bytes:
    import io
    bmp = img.point(lambda p: 255 if p > INK_THRESHOLD else 0).convert("1")
    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()


def _text_width(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _ellipsize(draw, text: str, font, max_w: int) -> str:
    if _text_width(draw, text, font) <= max_w:
        return text
    ell = "..."
    while text and _text_width(draw, text + ell, font) > max_w:
        text = text[:-1]
    return text + ell


def _frame(draw, title: str, right: str = "") -> None:
    """Outer rule + a header band, drawn on the chrome plane."""
    draw.rectangle([0, 0, BMP_WIDTH - 1, BMP_HEIGHT - 1], outline=0, width=1)
    draw.line([(0, 22), (BMP_WIDTH - 1, 22)], fill=0, width=1)


def _bracket(draw, x: int, y: int, w: int, h: int, arm: int = 9) -> None:
    """Corner brackets, the [ ] decorators from the card."""
    draw.line([(x, y), (x + arm, y)], fill=0)
    draw.line([(x, y), (x, y + arm)], fill=0)
    draw.line([(x + w - arm, y), (x + w, y)], fill=0)
    draw.line([(x + w, y), (x + w, y + arm)], fill=0)
    draw.line([(x, y + h - arm), (x, y + h)], fill=0)
    draw.line([(x, y + h), (x + arm, y + h)], fill=0)
    draw.line([(x + w - arm, y + h), (x + w, y + h)], fill=0)
    draw.line([(x + w, y + h - arm), (x + w, y + h)], fill=0)


# ── Screen 1: Operation Brief ─────────────────────────────────────────────────

def _screen_brief(data: BriefInput) -> list[tuple[bytes, float]]:
    tier, tier_sub = calc_tier(data.energy, data.focus, data.window_minutes)
    date_str = datetime.now().strftime("%a %d %b").upper()
    one_thing = data.one_thing.strip() or "Not defined - name it before starting"

    f_micro = load_font(14, "display")
    f_label = load_font(16, "display")
    f_tier = load_font(24, "display")
    f_hero = load_font(30, "display")

    # chrome
    img_c, d_c = _canvas()
    _frame(d_c, "OPERATOR BRIEF")
    _bracket(d_c, MARGIN, 58, BMP_WIDTH - 2 * MARGIN - 1, 44)
    d_c.line([(MARGIN, 112), (BMP_WIDTH - MARGIN, 112)], fill=0)

    # labels
    img_l, d_l = _canvas()
    d_l.text((MARGIN, 5), "OPERATOR BRIEF", font=f_micro, fill=0)
    d_l.text((BMP_WIDTH - MARGIN - _text_width(d_l, date_str, f_micro), 5),
             date_str, font=f_micro, fill=0)
    sub = _ellipsize(d_l, tier_sub, f_micro, 300)
    d_l.text((BMP_WIDTH - MARGIN - _text_width(d_l, sub, f_micro), 34),
             sub, font=f_micro, fill=0)
    footer = f"{DOMAIN_LABELS.get(data.domain, 'Other')}  {data.t_start}-{data.t_end}"
    d_l.text((MARGIN, 117), _ellipsize(d_l, footer, f_micro, BMP_WIDTH - 2 * MARGIN),
             font=f_micro, fill=0)

    # hero
    img_h, d_h = _canvas()
    d_h.text((MARGIN, 28), tier, font=f_tier, fill=0)
    body = _ellipsize(d_h, one_thing, f_hero, BMP_WIDTH - 2 * MARGIN - 28)
    d_h.text((MARGIN + 14, 66), body, font=f_hero, fill=0)

    return [
        (_to_bmp(img_c), Z_CHROME),
        (_to_bmp(img_l), Z_LABEL),
        (_to_bmp(img_h), Z_HERO),
    ]


# ── Screen 2: Scheduled Blocks ────────────────────────────────────────────────

ROW_TOP = 30
ROW_PITCH = 26
MAX_ROWS = 4


def _screen_blocks(data: BriefInput) -> list[tuple[bytes, float]]:
    blocks = [b for b in data.blocks if (b.name or b.start)][:MAX_ROWS]

    f_micro = load_font(14, "display")
    f_idx = load_font(14, "display")
    f_name = load_font(19, "display")

    img_c, d_c = _canvas()
    _frame(d_c, "SCHEDULED BLOCKS")
    for i in range(len(blocks)):
        y = ROW_TOP + i * ROW_PITCH + ROW_PITCH - 4
        if y < BMP_HEIGHT - 4:
            d_c.line([(MARGIN, y), (BMP_WIDTH - MARGIN, y)], fill=0)

    img_l, d_l = _canvas()
    d_l.text((MARGIN, 5), "SCHEDULED BLOCKS", font=f_micro, fill=0)
    count = f"{len(blocks)}/{MAX_ROWS}"
    d_l.text((BMP_WIDTH - MARGIN - _text_width(d_l, count, f_micro), 5),
             count, font=f_micro, fill=0)

    img_h, d_h = _canvas()

    if not blocks:
        d_h.text((MARGIN, 60), "No blocks scheduled", font=f_name, fill=0)
    else:
        for i, b in enumerate(blocks):
            y = ROW_TOP + i * ROW_PITCH
            d_l.text((MARGIN, y + 4), f"{i + 1:02d}", font=f_idx, fill=0)

            dur = fmt_minutes(b.minutes) if b.minutes > 0 else "-"
            span = f"{b.start or '--:--'}-{b.end or '--:--'}"
            right = f"{span}  {dur}"
            right_w = _text_width(d_l, right, f_micro)
            d_l.text((BMP_WIDTH - MARGIN - right_w, y + 4), right, font=f_micro, fill=0)

            name_max = BMP_WIDTH - 2 * MARGIN - right_w - 46
            name = _ellipsize(d_h, b.name or f"Block {i + 1}", f_name, name_max)
            d_h.text((MARGIN + 32, y), name, font=f_name, fill=0)

    return [
        (_to_bmp(img_c), Z_CHROME),
        (_to_bmp(img_l), Z_LABEL),
        (_to_bmp(img_h), Z_HERO),
    ]


# ── Screen 3: Operator Power Index ────────────────────────────────────────────

METER_X = 250
METER_Y = 62
METER_W = BMP_WIDTH - METER_X - MARGIN
METER_H = 14


def _screen_power(data: BriefInput) -> list[tuple[bytes, float]]:
    p = calc_power(data.energy, data.focus, data.checks_done)

    f_micro = load_font(14, "display")
    f_unit = load_font(16, "display")
    f_big = load_font(56, "display")

    img_c, d_c = _canvas()
    _frame(d_c, "OPERATOR POWER INDEX")
    d_c.rectangle([METER_X, METER_Y, METER_X + METER_W, METER_Y + METER_H],
                  outline=0, width=1)
    d_c.line([(MARGIN, 112), (BMP_WIDTH - MARGIN, 112)], fill=0)

    img_l, d_l = _canvas()
    d_l.text((MARGIN, 5), "OPERATOR POWER INDEX", font=f_micro, fill=0)
    # Header and value share a column origin so the numbers sit under their
    # labels; the face is proportional, so padded strings would drift.
    cols = [("RESOURCE", p["resource"]), ("CHECKS", p["checks"]), ("BASE", p["base"])]
    cx = METER_X
    for head, val in cols:
        d_l.text((cx, 40), head, font=f_micro, fill=0)
        d_l.text((cx, METER_Y + METER_H + 6), str(val), font=f_micro, fill=0)
        cx += _text_width(d_l, head, f_micro) + 16

    pills = "  ".join(
        f"{CHECK_LABELS[k]} {'+' if data.checks.get(k) else '-'}" for k in CHECK_KEYS
    )
    d_l.text((MARGIN, 117), _ellipsize(d_l, pills, f_micro, BMP_WIDTH - 2 * MARGIN),
             font=f_micro, fill=0)

    img_h, d_h = _canvas()
    d_h.text((MARGIN + 6, 32), str(p["total"]), font=f_big, fill=0)
    num_w = _text_width(d_h, str(p["total"]), f_big)
    d_h.text((MARGIN + 10 + num_w, 74), "/100", font=f_unit, fill=0)

    # meter fill, clamped to the track
    fill_w = int(round(METER_W * min(100, max(0, p["total"])) / 100))
    if fill_w > 2:
        d_h.rectangle([METER_X + 2, METER_Y + 2,
                       METER_X + max(3, fill_w - 2), METER_Y + METER_H - 2], fill=0)

    return [
        (_to_bmp(img_c), Z_CHROME),
        (_to_bmp(img_l), Z_LABEL),
        (_to_bmp(img_h), Z_HERO),
    ]


# ── Entry point ───────────────────────────────────────────────────────────────

SCREENS = {
    "brief": _screen_brief,
    "blocks": _screen_blocks,
    "power": _screen_power,
}


def render_brief(data: BriefInput, screens: list[str] | None = None) -> list[dict]:
    """Render the requested screens.

    Returns [{"name": str, "layers": [(bmp_bytes, z), ...]}] in send order.
    """
    wanted = screens or ["brief", "blocks", "power"]
    out = []
    for name in wanted:
        fn = SCREENS.get(name)
        if fn is None:
            continue
        out.append({"name": name, "layers": fn(data)})
    return out
