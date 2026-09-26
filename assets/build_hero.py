#!/usr/bin/env python3
"""Build assets/jev-hero.svg, the animated hero at the top of the root README.

Run from the repo root:   python3 assets/build_hero.py
Standard library only. Edit this script, not the SVG: the SVG is generated.

The story, once per demo: English types in on the left, Jev judges it, typed values come out
on the right. Adding a demo means adding one entry to SCENES and one render function.

Numbers follow the repo rule: every number drawn comes from a live, logged run, and each scene
prints its source file. Scene 01 has no logged per-post scores, so its bars carry no numbers
(bar lengths are illustrative); likewise the chart scene 03 draws has no axis values.

  02 · 780 / 913 / 595   02-semsql/docs/handoff-llm-benchmark.md ("Live runs from this session")
  03 · 1.00 / 0.57       03-visualize/docs/eval-results.md (region_trend, Run 1-2; partial `line`)
  04 · row 44, P/R       04-dbt-semantic-tests/docs/eval-results.md (2026-09-24T20:37:35Z live/pack=1)

How it animates: plain CSS keyframes inside the SVG (GitHub renders an <img> SVG with CSS
animation but no JS). Every animated element runs one cycle of length T (the sum of the scene
lengths) from t=0 with no delay, so the whole loop stays in sync; each element gets its own
@keyframes, computed from absolute times on that single timeline. With prefers-reduced-motion,
animation is off and one static scene (STATIC_SCENE) is shown.
"""

import random
from pathlib import Path
from xml.sax.saxutils import escape as esc

OUT_PATH = Path(__file__).with_name("jev-hero.svg")
W, H = 960, 420

# Palette (the hero is a dark card, so it reads the same on GitHub's light and dark themes)
BG, CARD, EDGE = "#0A0E1A", "#10162A", "#222B47"
TXT, SOFT, MUTED, DIM = "#E6E9F2", "#C9CFE0", "#8A93AD", "#5B6480"
VIOLET, CYAN, GREEN, RED, AMBER, PINK = "#8B5CF6", "#22D3EE", "#34D399", "#FB7185", "#FBBF24", "#F472B6"
KW, FN, STR = "#C4B5FD", "#67E8F9", "#86EFAC"  # code: keyword, function, string

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

# Layout
IN_X, OUT_X, CARD_Y, CARD_W, CARD_H = 32, 556, 76, 372, 262
PAD = 18
OX, OY = 480, 207            # orb centre
LINE0, LH = 138, 20          # first code baseline, line height
CW = 7.5                     # monospace advance at 12.5px (0.6em)
RX = OUT_X + PAD             # output content left edge
RW = CARD_W - 2 * PAD        # output content width

# Scene-local times (seconds from the start of a scene)
T_TYPE0, T_TYPE1 = 0.3, 1.9  # typing window
T_JUDGE = 2.3                # orb pulse
T_OUT = 2.5                  # typed values start appearing
STATIC_SCENE = 1             # shown when motion is reduced

EASE = "animation-timing-function:cubic-bezier(.2,.8,.2,1)"


class Timeline:
    """One loop of length T. Each call returns a CSS class bound to fresh @keyframes."""

    def __init__(self, durations):
        self.starts, t = [], 0.0
        for d in durations:
            self.starts.append(t)
            t += d
        self.durations, self.T = durations, t
        self.css, self.k = [], 0

    def span(self, i):
        s = self.starts[i]
        return s, s + self.durations[i]

    def anim(self, stops):
        """stops: [(absolute seconds, css declarations)]. Clamped to [0, T], padded at both ends."""
        T = self.T
        stops = sorted(((min(max(t, 0), T), d) for t, d in stops), key=lambda s: s[0])
        if stops[0][0] > 0:
            stops.insert(0, (0, stops[0][1]))
        if stops[-1][0] < T:
            stops.append((T, stops[-1][1]))
        frames = {}  # stops at the same percent merge; a later declaration wins in CSS
        for t, d in stops:
            p = round(t / T * 100, 2)
            frames[p] = f"{frames[p]};{d}" if p in frames else d
        name = f"k{self.k}"
        self.k += 1
        body = "".join(f"{p:g}%{{{d}}}" for p, d in frames.items())
        self.css.append(f"@keyframes {name}{{{body}}}.{name}{{animation:{name} {T:g}s linear infinite}}")
        return name

    # --- building blocks -------------------------------------------------------------------

    def window(self, i, t_in, t_out=None, dur=0.4, rise=8):
        """Fade/rise in at t_in, out at t_out (default: end of scene)."""
        s, e = self.span(i)
        a, b = s + t_in, (s + t_out) if t_out else e - 0.35
        hid = f"opacity:0;transform:translateY({rise}px)"
        shown = "opacity:1;transform:translateY(0)"
        return self.anim([(0, hid), (a, f"{hid};{EASE}"), (a + dur, shown), (b, shown), (b + 0.3, hid)])

    def typer(self, i, t0, t1, n, width):
        """Slide a card-coloured cover (with cursor) right in n steps: a typing reveal."""
        s, e = self.span(i)
        a, b, r = s + t0, s + t1, min(e, self.T - 0.02)
        on0, onw = "transform:translateX(0);opacity:1", f"transform:translateX({width:g}px);opacity:1"
        offw = f"transform:translateX({width:g}px);opacity:0"
        return self.anim([(0, on0), (a, f"{on0};animation-timing-function:steps({n},end)"),
                          (b, onw), (b + 0.15, offw), (r - 0.01, offw), (r, on0)])

    def cursor(self, i, t0, t1):
        s, _ = self.span(i)
        return self.anim([(0, "opacity:0"), (s + t0, "opacity:0"), (s + t0 + 0.01, "opacity:1"),
                          (s + t1 + 0.15, "opacity:1"), (s + t1 + 0.16, "opacity:0")])

    def grow(self, i, t0, dur=0.7):
        """scaleX 0 -> 1 (pair with class .bar for a left origin)."""
        s, e = self.span(i)
        a, r = s + t0, min(e, self.T - 0.02)
        return self.anim([(0, "transform:scaleX(0)"), (a, f"transform:scaleX(0);{EASE}"),
                          (a + dur, "transform:scaleX(1)"), (r - 0.01, "transform:scaleX(1)"),
                          (r, "transform:scaleX(0)")])

    def draw(self, i, t0, dur=1.2):
        """Stroke a path with pathLength=1 from start to end."""
        s, e = self.span(i)
        a, r = s + t0, min(e, self.T - 0.02)
        return self.anim([(0, "stroke-dashoffset:1"), (a, "stroke-dashoffset:1;animation-timing-function:cubic-bezier(.4,0,.2,1)"),
                          (a + dur, "stroke-dashoffset:0"), (r - 0.01, "stroke-dashoffset:0"), (r, "stroke-dashoffset:1")])

    def fly(self, a, dur, dx, dy, ease_x, ease_y, fade_at=0.75):
        """Absolute-time flight: separate X and Y easing curves the path; returns 2 classes."""
        end, T = a + dur, self.T
        x = self.anim([(0, "transform:translateX(0)"), (a, f"transform:translateX(0);animation-timing-function:{ease_x}"),
                       (end, f"transform:translateX({dx:g}px)"), (end + 0.01, "transform:translateX(0)")])
        y = self.anim([(0, "transform:translateY(0);opacity:0"), (a, f"transform:translateY(0);opacity:0;animation-timing-function:{ease_y}"),
                       (a + 0.12, "opacity:1"), (a + dur * fade_at, "opacity:1"),
                       (end, f"transform:translateY({dy:g}px);opacity:0"), (end + 0.01, "transform:translateY(0)"),
                       (T, "transform:translateY(0);opacity:0")])
        return x, y


# --- small SVG helpers ---------------------------------------------------------------------

def text(x, y, s, cls="s", fill=TXT, size=12, anchor=None, weight=None, extra=""):
    a = f' text-anchor="{anchor}"' if anchor else ""
    w = f' font-weight="{weight}"' if weight else ""
    return f'<text class="{cls}" x="{x:g}" y="{y:g}" fill="{fill}" font-size="{size}"{a}{w}{extra}>{esc(s)}</text>'


def g(cls, inner, transform=None):
    t = f' transform="{transform}"' if transform else ""
    c = f' class="{cls}"' if cls else ""
    return f"<g{c}{t}>{inner}</g>"


def mono_width(s, size=12.5):
    return len(s) * size * 0.6


# --- scenes --------------------------------------------------------------------------------
# Each scene: header chip, an input file typed on the left, typed output on the right.
# `lines` are lists of (text, colour) segments; `tokens` fly from the input into the orb.

def render_cringe(tl, i):
    dims = [  # (label, primitive, illustrative bar length — no logged scores exist for this post)
        ("Humblebrag", "score", 0.86), ("Engagement bait", "score", 0.62),
        ("Fake vulnerability", "score", 0.38), ("Buzzword density", "score", 0.54),
        ("Broetry", "noul", 0.95), ("“Humbled to announce”", "noul", 0.98),
        ("Toddler-industrial complex", "noul", 0.74), ("Unsolicited hustle advice", "noul", 0.41),
    ]
    out, bx, bw = [], RX + 198, RW - 198
    for k, (label, prim, v) in enumerate(dims):
        y = 138 + k * 23.4
        t = T_OUT + k * 0.09
        row = (text(RX, y, label, fill=SOFT, size=12)
               + text(RX + 162, y, prim, cls="m", fill=KW if prim == "score" else FN, size=10)
               + f'<rect x="{bx}" y="{y - 8}" width="{bw}" height="7" rx="3.5" fill="#1B2340"/>'
               + f'<rect class="bar {tl.grow(i, t + 0.1)}" x="{bx}" y="{y - 8}" width="{bw * v:g}" height="7" rx="3.5" fill="url(#barg)"/>')
        out.append(g(tl.window(i, t), row))
    out.append(g(tl.window(i, T_OUT + 1.2), text(RX, 326, "bars reweight live · no API call", cls="m", fill=DIM, size=9.5)))
    return "".join(out)


def render_semsql(tl, i):
    scale = 262 / 913
    kw_w, jev_w, never_w = 780 * scale, 913 * scale, 595 * scale
    out = []
    out.append(g(tl.window(i, T_OUT),
                 text(RX, 140, "ILIKE '%refund%'", cls="m", fill=MUTED, size=11)
                 + text(RX + RW, 140, "keyword search", fill=DIM, size=10.5, anchor="end")
                 + f'<rect x="{RX}" y="148" width="{kw_w:g}" height="20" rx="4" fill="#2A3350" class="bar {tl.grow(i, T_OUT + 0.1)}"/>'
                 + g(tl.window(i, T_OUT + 0.7, rise=0), text(RX + kw_w + 8, 163, "780 rows", fill=SOFT, size=13, weight=600))))
    out.append(g(tl.window(i, T_OUT + 0.5),
                 text(RX, 196, "jev_noul(body, …) > 0.8", cls="m", fill=FN, size=11)
                 + text(RX + RW, 196, "stars ≤ 2", fill=DIM, size=10.5, anchor="end")
                 + f'<rect x="{RX}" y="204" width="{jev_w:g}" height="20" rx="4" fill="url(#jg)" class="bar {tl.grow(i, T_OUT + 0.6)}"/>'
                 + g(tl.window(i, T_OUT + 1.2, rise=0), text(RX + jev_w + 8, 219, "913 rows", fill=TXT, size=13, weight=700))))
    # 595 of the 913 never contain the word
    out.append(g(tl.window(i, T_OUT + 1.6, rise=0),
                 f'<rect x="{RX}" y="204" width="{never_w:g}" height="20" rx="4" fill="url(#hatch)"/>'
                 + f'<path d="M{RX} 232v6h{never_w:g}v-6" fill="none" stroke="{CYAN}" stroke-width="1.2"/>'))
    out.append(g(tl.window(i, T_OUT + 1.9),
                 f'<text class="s" x="{RX}" y="262" font-size="14" fill="{SOFT}">'
                 f'<tspan fill="{CYAN}" font-weight="700" font-size="17">595</tspan> of them never say “refund”</text>'
                 + text(RX, 284, "a keyword filter can't find them. English can.", fill=MUTED, size=11.5)))
    out.append(g(tl.window(i, T_OUT + 2.2), text(RX, 326, "live run · 02-semsql/docs/handoff-llm-benchmark.md", cls="m", fill=DIM, size=9.5)))
    return "".join(out)


def render_visualize(tl, i):
    out = []
    for k, (chart, cols, p, colour, t) in enumerate([
            ("multi_line", "region × revenue", "1.00", GREEN, T_OUT),
            ("line", "total revenue only", "0.57", AMBER, T_OUT + 0.3)]):
        y = 140 + k * 32
        out.append(g(tl.window(i, t),
                     text(RX, y, chart, cls="m", fill=TXT, size=12)
                     + text(RX + 12 + mono_width(chart, 12), y, cols, fill=MUTED, size=11)
                     + text(RX + RW, y, p, cls="m", fill=colour, size=13, anchor="end", weight=700)
                     + f'<rect x="{RX}" y="{y + 7}" width="{RW}" height="4" rx="2" fill="#1B2340"/>'
                     + f'<rect class="bar {tl.grow(i, t + 0.15)}" x="{RX}" y="{y + 7}" width="{RW * float(p):g}" height="4" rx="2" fill="{colour}"/>'))
    out.append(g(tl.window(i, T_OUT + 0.9, rise=0),
                 f'<rect x="{RX - 6}" y="{126}" width="{RW + 12}" height="24" rx="5" fill="none" stroke="{GREEN}" stroke-opacity=".55"/>'))
    # the winning chart draws itself (shape illustrative, no values)
    x0, x1, y0, y1 = RX + 8, RX + RW, 202, 300
    axes = f'<path d="M{x0} {y0 - 4}V{y1}H{x1}" fill="none" stroke="{EDGE}" stroke-width="1"/>'
    series = [(VIOLET, lambda u: 0.25 + 0.55 * u), (CYAN, lambda u: 0.45 + 0.12 * u + 0.08 * (u * 7 % 1)),
              (PINK, lambda u: 0.78 - 0.5 * u), (AMBER, lambda u: 0.2 + 0.18 * u + 0.1 * abs(((u * 3) % 1) - 0.5))]
    lines = []
    for k, (colour, f) in enumerate(series):
        pts = [(x0 + 6 + (x1 - x0 - 12) * n / 11, y1 - 6 - (y1 - y0 - 12) * f(n / 11)) for n in range(12)]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        lines.append(f'<path class="{tl.draw(i, T_OUT + 1.1 + k * 0.12)}" d="{d}" pathLength="1" stroke-dasharray="1" '
                     f'fill="none" stroke="{colour}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
        ex, ey = pts[-1]
        lines.append(g(tl.window(i, T_OUT + 2.3 + k * 0.12, rise=0), f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="{colour}"/>'))
    out.append(g(tl.window(i, T_OUT + 1.0, rise=0), axes) + "".join(lines))
    out.append(g(tl.window(i, T_OUT + 2.4), text(RX, 326, "live run · 03-visualize/docs/eval-results.md", cls="m", fill=DIM, size=9.5)))
    return "".join(out)


def render_dbt(tl, i):
    out = []
    checks = [("not_null", "comment", True), ("not_null", "reason_code", True),
              ("accepted_values", "reason_code", True), ("jev_expect", "comment", False)]
    for k, (test, col, ok) in enumerate(checks):
        y = 138 + k * 22
        t = T_OUT + k * 0.25
        hl = "" if ok else f'<rect x="{RX - 6}" y="{y - 15}" width="{RW + 12}" height="21" rx="5" fill="{RED}" fill-opacity=".12" stroke="{RED}" stroke-opacity=".5"/>'
        status = (text(RX + RW, y, "PASS", cls="m", fill=GREEN, size=11.5, anchor="end", weight=700) if ok else
                  f'<text class="m" x="{RX + RW}" y="{y}" font-size="11.5" text-anchor="end">'
                  f'<tspan fill="{MUTED}">p &gt; 0.8  </tspan><tspan fill="{RED}" font-weight="700">FAIL</tspan></text>')
        out.append(g(tl.window(i, t), hl + text(RX, y, test, cls="m", fill=FN if not ok else SOFT, size=11.5)
                     + text(RX + mono_width(test, 11.5) + 8, y, col, cls="m", fill=MUTED, size=11.5) + status))
    tx = T_OUT + 1.5
    head = (f'<line x1="{RX}" y1="224" x2="{RX + RW}" y2="224" stroke="{EDGE}"/>'
            + text(RX, 244, "whole test · live · pack=1", cls="m", fill=MUTED, size=10)
            + text(RX + 250, 244, "precision", fill=DIM, size=10, anchor="end")
            + text(RX + RW, 244, "recall", fill=DIM, size=10, anchor="end"))
    out.append(g(tl.window(i, tx), head))
    for k, (who, p, r, colour, weight) in enumerate([("Jev", "1.00", "1.00", GREEN, 700), ("regex baseline", "0.45", "0.75", MUTED, 400)]):
        y = 268 + k * 22
        out.append(g(tl.window(i, tx + 0.3 + k * 0.25),
                     text(RX, y, who, fill=TXT if k == 0 else MUTED, size=12.5, weight=weight)
                     + text(RX + 250, y, p, cls="m", fill=colour, size=13, anchor="end", weight=weight)
                     + text(RX + RW, y, r, cls="m", fill=colour, size=13, anchor="end", weight=weight)))
    out.append(g(tl.window(i, tx + 0.9), text(RX, 326, "live run · 04-dbt-semantic-tests/docs/eval-results.md", cls="m", fill=DIM, size=9.5)))
    return "".join(out)


P = TXT  # plain code
SCENES = [
    dict(num="01", name="Cringe-o-Meter", dur=6.5, file="post_draft.txt", out="8 judgments, in parallel",
         prim="score · noul", render=render_cringe, tokens=["humbled", "coffee", "Agree?"],
         lines=[[("I'm humbled to announce", P)], [("that I bought a coffee.", P)], [],
                [("The barista spelled", P)], [("my name wrong.", P)], [],
                [("Here's what that taught", P)], [("me about B2B sales.", P)], [],
                [("Agree?", P)]]),
    dict(num="02", name="semsql", dur=7.0, file="demo.sql", out="DOUBLE 0..1 → a WHERE clause",
         prim="noul", render=render_semsql, tokens=["money back", "reviews", "stars ≤ 2"],
         lines=[[("WITH", KW), (" unhappy ", P), ("AS", KW), (" (", P)],
                [("  SELECT", KW), (" * ", P), ("FROM", KW), (" reviews", P)],
                [("  WHERE", KW), (" stars <= ", P), ("2", AMBER), (")", P)],
                [("SELECT", KW), (" id, body", P)],
                [("FROM", KW), (" unhappy", P)],
                [("WHERE", KW), (" jev_noul", FN), ("(body,", P)],
                [("  'The customer is asking", STR)],
                [("   for their money back'", STR), (")", P)],
                [("  > ", P), ("0.8", AMBER), (";", P)]]),
    dict(num="03", name="VISUALIZE", dur=6.8, file="query.sql", out="P(chart answers the intent)",
         prim="score", render=render_visualize, tokens=["trending", "regions", "revenue"],
         lines=[[("SELECT", KW), (" date_trunc", FN), ("(", P), ("'month'", STR), (",", P)],
                [("         order_date) ", P), ("AS", KW), (" month,", P)],
                [("       region,", P)],
                [("       sum", FN), ("(revenue) ", P), ("AS", KW), (" revenue", P)],
                [("FROM", KW), (" orders", P)],
                [("GROUP BY", KW), (" ALL", KW)], [],
                [("VISUALIZE", PINK)],
                [("  'how are regions trending'", STR)]]),
    dict(num="04", name="dbt semantic tests", dur=7.7, file="stg_returns · row 44", out="4 tests on one row",
         prim="noul", render=render_dbt, tokens=["crushed", "late", "fails_if"],
         lines=[[("reason_code", KW), (": ", P), ("late", AMBER)],
                [("comment", KW), (": ", P), ("The box was crushed", STR)],
                [("  flat and the banana nutella", STR)],
                [("  jaffle inside was falling apart.", STR)], [],
                [("- ", P), ("jev_expect", FN), (":", P)],
                [("    fails_if", KW), (": ", P), ("\"The customer's", STR)],
                [("    `comment` describes a", STR)],
                [("    different main reason for", STR)],
                [("    the return than `reason_code`\"", STR)]]),
]


# --- assembly ------------------------------------------------------------------------------

def card(x, label_left, label_right):
    return (f'<rect x="{x}" y="{CARD_Y}" width="{CARD_W}" height="{CARD_H}" rx="12" fill="{CARD}" stroke="{EDGE}"/>'
            + f'<line x1="{x}" y1="{CARD_Y + 36}" x2="{x + CARD_W}" y2="{CARD_Y + 36}" stroke="{EDGE}"/>'
            + text(x + CARD_W - PAD, CARD_Y + 23, label_right, fill=DIM, size=9.5, anchor="end",
                   extra=' letter-spacing="1.6" font-weight="600"')
            + (f'<circle cx="{x + PAD + 3}" cy="{CARD_Y + 19}" r="3" fill="{label_left}"/>' if label_left else ""))


def typed_input(tl, i, sc):
    lines = sc["lines"]
    chars = [sum(len(t) for t, _ in segs) for segs in lines]
    total = sum(chars) or 1
    t, per_char = T_TYPE0, (T_TYPE1 - T_TYPE0) / total
    x0 = IN_X + PAD
    texts, covers = [], []
    for k, (segs, n) in enumerate(zip(lines, chars)):
        if not n:
            t += 0.04
            continue
        y = LINE0 + k * LH
        spans = "".join(f'<tspan fill="{c}">{esc(s)}</tspan>' for s, c in segs)
        texts.append(f'<text class="m" x="{x0}" y="{y}" font-size="12.5" xml:space="preserve">{spans}</text>')
        w = n * CW + 4
        covers.append(g(f"cover {tl.typer(i, t, t + n * per_char, n, w)}",
                        f'<rect x="{x0 - 2}" y="{y - 14}" width="{w + 4:g}" height="19" fill="{CARD}"/>'
                        f'<rect class="{tl.cursor(i, t, t + n * per_char)}" x="{x0 - 2}" y="{y - 12}" width="2" height="15" fill="{CYAN}"/>'))
        t += n * per_char
    s, _ = tl.span(i)
    a, top, bottom = s + T_TYPE1 - 0.95, CARD_Y + 37, CARD_Y + CARD_H
    scan = tl.anim([(0, "opacity:0;transform:translateY(0)"), (a, "opacity:0;transform:translateY(0);animation-timing-function:cubic-bezier(.45,0,.55,1)"),
                    (a + 0.1, "opacity:1"), (a + 0.75, "opacity:1"), (a + 0.85, f"opacity:0;transform:translateY({bottom - top}px)"),
                    (a + 0.86, "transform:translateY(0)"), (tl.T, "opacity:0;transform:translateY(0)")])
    beam = (f'<g class="pt {scan}"><rect x="{IN_X}" y="{top - 26}" width="{CARD_W}" height="26" fill="url(#scan)"/>'
            f'<rect x="{IN_X}" y="{top - 1}" width="{CARD_W}" height="1.5" fill="{CYAN}" fill-opacity=".8"/></g>')
    return g(tl.window(i, 0.05, rise=0), "".join(texts) + "".join(covers) + beam)


def particles(tl, i, sc, rng):
    s, _ = tl.span(i)
    parts = []
    # dots and word tokens stream from the input card into the orb
    for k in range(9):
        x0, y0 = rng.uniform(318, 396), rng.uniform(128, 318)
        a, dur = s + 1.15 + k * 0.1 + rng.uniform(0, 0.08), rng.uniform(0.85, 1.05)
        cx, cy = tl.fly(a, dur, OX - x0 + rng.uniform(-6, 6), OY - y0 + rng.uniform(-6, 6),
                            "cubic-bezier(.55,0,.9,.5)", "cubic-bezier(.1,.5,.3,1)")
        dot = f'<circle r="{rng.uniform(1.6, 2.8):.1f}" fill="{rng.choice([CYAN, KW, TXT])}"/>'
        parts.append(g("pt", g(cx, g(cy, dot)), f"translate({x0:.1f},{y0:.1f})"))
    for k, tok in enumerate(sc["tokens"]):
        x0, y0 = 350 - k * 10, 146 + k * 78 + rng.uniform(-6, 6)
        a, dur = s + 0.95 + k * 0.3, 0.95
        cx, cy = tl.fly(a, dur, OX - x0, OY - y0, "cubic-bezier(.55,0,.9,.5)", "cubic-bezier(.1,.5,.3,1)", 0.6)
        w = mono_width(tok, 10.5) + 14
        chip = (f'<rect x="{-w / 2:.1f}" y="-10" width="{w:.1f}" height="19" rx="9.5" fill="#1B2340" stroke="{VIOLET}"/>'
                + text(0, 3.5, tok, cls="m", fill=TXT, size=10.5, anchor="middle"))
        parts.append(g("pt", g(cx, g(cy, chip)), f"translate({x0:.1f},{y0:.1f})"))
    # typed values leave the orb as small squares
    for k in range(7):
        ty = 132 + k * 27
        a = s + T_JUDGE + 0.05 + k * 0.05
        cx, cy = tl.fly(a, 0.5, RX - 10 - OX, ty - OY, "cubic-bezier(.2,.7,.3,1)", "cubic-bezier(.4,0,.6,1)", 0.8)
        sq = f'<rect x="-3" y="-3" width="6" height="6" rx="1.5" fill="{GREEN if k % 3 else CYAN}"/>'
        parts.append(g("pt", g(cx, g(cy, sq)), f"translate({OX},{OY})"))
    return "".join(parts)


def orb(tl):
    judges = [s + T_JUDGE for s in tl.starts]
    glow, core = [(0, "opacity:.35")], [(0, "transform:scale(1)")]
    for j in judges:
        glow += [(j - 0.2, "opacity:.35"), (j + 0.08, "opacity:1"), (j + 1.0, "opacity:.35")]
        core += [(j - 0.2, "transform:scale(1)"), (j + 0.06, "transform:scale(1.12)"), (j + 0.6, "transform:scale(1)")]
    waves = ""
    for j in judges:
        w = tl.anim([(0, "opacity:0;transform:scale(1)"), (j, "opacity:.9;transform:scale(1);animation-timing-function:cubic-bezier(.1,.6,.3,1)"),
                     (j + 1.1, "opacity:0;transform:scale(2.7)"), (j + 1.11, "opacity:0;transform:scale(1)")])
        waves += f'<circle class="pt c {w}" cx="{OX}" cy="{OY}" r="34" fill="none" stroke="{CYAN}" stroke-width="1.5"/>'
    return (f'<circle class="{tl.anim(glow)}" cx="{OX}" cy="{OY}" r="92" fill="url(#glow)"/>'
            + waves
            + f'<circle class="c spin" cx="{OX}" cy="{OY}" r="50" fill="none" stroke="url(#jg)" stroke-width="1.5" stroke-dasharray="3 7"/>'
            + f'<circle class="c spin-r" cx="{OX}" cy="{OY}" r="61" fill="none" stroke="{CYAN}" stroke-opacity=".35" stroke-dasharray="40 16 2 16"/>'
            + f'<g class="c {tl.anim(core)}"><circle cx="{OX}" cy="{OY}" r="34" fill="url(#core)" stroke="{KW}" stroke-opacity=".6"/>'
            + text(OX, OY + 6, "jev", fill="#fff", size=17, anchor="middle", weight=700, extra=' letter-spacing=".5"') + "</g>")


def build():
    rng = random.Random(7)
    tl = Timeline([sc["dur"] for sc in SCENES])
    body = []

    # background: dot grid, a slow light sweep, header and cards
    body.append(f'<rect width="{W}" height="{H}" rx="18" fill="{BG}"/>'
                f'<rect width="{W}" height="{H}" rx="18" fill="url(#dots)"/>'
                f'<g clip-path="url(#frame)"><rect class="sweep" x="-320" y="0" width="320" height="{H}" fill="url(#sweep)"/></g>'
                f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="17.5" fill="none" stroke="{EDGE}"/>')
    body.append(f'<circle cx="46" cy="40" r="8" fill="url(#core)"/><circle class="c spin" cx="46" cy="40" r="12" fill="none" stroke="url(#jg)" stroke-dasharray="2 3"/>'
                + text(66, 46, "Jev demos", size=18, weight=700)
                + text(174, 46, "typed judgments, not generated text · TypeSafe", fill=MUTED, size=12.5))
    body.append(card(IN_X, None, "ENGLISH IN") + card(OUT_X, None, "TYPED OUT"))

    for i, sc in enumerate(SCENES):
        scene = []
        # header chip: "01 · Cringe-o-Meter"
        label = f"{sc['num']} · {sc['name']}"
        cw = len(label) * 7.1 + 26
        scene.append(g(tl.window(i, 0.0, rise=-6),
                       f'<rect x="{W - 32 - cw:.1f}" y="26" width="{cw:.1f}" height="26" rx="13" fill="#161D35" stroke="{VIOLET}" stroke-opacity=".6"/>'
                       + text(W - 32 - cw / 2, 43.5, label, fill=TXT, size=12.5, anchor="middle", weight=600)))
        # card sub-labels
        scene.append(g(tl.window(i, 0.05, rise=0), text(IN_X + PAD, CARD_Y + 23, sc["file"], cls="m", fill=MUTED, size=11)))
        scene.append(g(tl.window(i, T_OUT - 0.1, rise=0), text(RX, CARD_Y + 23, sc["out"], cls="m", fill=MUTED, size=11)))
        scene.append(f'<g clip-path="url(#inclip)">{typed_input(tl, i, sc)}</g>')
        scene.append(sc["render"](tl, i))
        # primitive under the orb
        scene.append(g(tl.window(i, T_JUDGE - 0.2, rise=4),
                       text(OX, OY + 90, "primitive", fill=DIM, size=9.5, anchor="middle", extra=' letter-spacing="1.2"')
                       + text(OX, OY + 106, sc["prim"], cls="m", fill=FN, size=11.5, anchor="middle")))
        scene.append(particles(tl, i, sc, rng))
        body.append(g("later" if i != STATIC_SCENE else "", "".join(scene)))

    body.append(orb(tl))

    # footer: tagline and per-scene progress
    body.append(f'<text class="s" x="32" y="390" font-size="19" font-weight="700" fill="{TXT}">English in. '
                f'<tspan fill="url(#jg)">Typed judgments out.</tspan></text>')
    seg_w, gap = 60, 10
    x = W - 32 - len(SCENES) * seg_w - (len(SCENES) - 1) * gap
    for i, sc in enumerate(SCENES):
        s, e = tl.span(i)
        e2 = min(e, tl.T - 0.02)
        fill = tl.anim([(0, "transform:scaleX(0)"), (s, "transform:scaleX(0)"), (e2, "transform:scaleX(1)"),
                        (tl.T - 0.02, "transform:scaleX(1)"), (tl.T - 0.01, "transform:scaleX(0)")])
        lit = tl.anim([(0, "opacity:.4"), (s, "opacity:.4"), (s + 0.2, "opacity:1"), (e - 0.2, "opacity:1"), (e, "opacity:.4")])
        body.append(text(x, 378, sc["num"], cls=f"m {lit}", fill=TXT, size=10)
                    + f'<rect x="{x}" y="385" width="{seg_w}" height="3" rx="1.5" fill="#1B2340"/>'
                    + f'<rect class="bar {fill}" x="{x}" y="385" width="{seg_w}" height="3" rx="1.5" fill="url(#jg)"/>')
        x += seg_w + gap

    defs = f"""<defs>
<linearGradient id="jg" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="{KW}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>
<linearGradient id="barg" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}"/><stop offset=".6" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
<radialGradient id="core" cx=".38" cy=".35" r=".75"><stop offset="0" stop-color="#C4B5FD"/><stop offset=".45" stop-color="#7C3AED"/><stop offset="1" stop-color="#2E1065"/></radialGradient>
<radialGradient id="glow"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".55"/><stop offset=".5" stop-color="{VIOLET}" stop-opacity=".12"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
<linearGradient id="sweep" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#8B5CF6" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<linearGradient id="scan" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".16"/></linearGradient>
<pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".9" fill="#1A2140"/></pattern>
<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="{CYAN}" fill-opacity=".25"/><rect width="2.5" height="6" fill="#fff" fill-opacity=".35"/></pattern>
<clipPath id="frame"><rect width="{W}" height="{H}" rx="18"/></clipPath>
<clipPath id="inclip"><rect x="{IN_X + 1}" y="{CARD_Y + 37}" width="{CARD_W - 2}" height="{CARD_H - 38}" rx="11"/></clipPath>
</defs>"""

    style = (f".m{{font-family:{MONO}}}.s,text{{font-family:{SANS}}}text.m{{font-family:{MONO}}}"
             ".bar{transform-box:fill-box;transform-origin:0 50%}.c{transform-box:fill-box;transform-origin:center}"
             "@keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin 16s linear infinite}"
             ".spin-r{animation:spin 26s linear infinite reverse}"
             f"@keyframes sweep{{to{{transform:translateX({W + 320}px)}}}}.sweep{{animation:sweep 9s cubic-bezier(.4,0,.6,1) infinite}}"
             + "".join(tl.css)
             + "@media (prefers-reduced-motion:reduce){*{animation:none!important}.later,.cover,.pt,.sweep{display:none}}")

    desc = ("An animated loop through the four Jev demos. In each, English goes in on the left, the Jev model "
            "judges it, and typed values come out on the right: eight cringe judgments of a LinkedIn post; "
            "a semantic SQL filter that finds 913 refund requests where keyword search finds 780, 595 of which "
            "never say refund; a VISUALIZE clause that scores a multi-line chart 1.00 and a partial line chart 0.57; "
            "and a dbt test that passes every structural check on a return row but fails the English one, "
            "with precision and recall 1.00 against a regex baseline's 0.45 and 0.75.")

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'role="img" aria-labelledby="title desc">'
           f'<title id="title">Jev demos: English in, typed judgments out</title><desc id="desc">{esc(desc)}</desc>'
           f"<style>{style}</style>{defs}{''.join(body)}</svg>\n")
    OUT_PATH.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT_PATH} · {len(svg) / 1024:.1f} KB · loop {tl.T:g} s · {tl.k} keyframe sets")


if __name__ == "__main__":
    build()
