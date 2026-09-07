#!/usr/bin/env python3
# epubveri for Sigil — the plugin icon, and the one place its geometry lives
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Write every copy of the plugin icon from one description of the mark.

    python3 icon.py

**At the root, not inside a plugin, because the mark is not a packaging
detail.** Each plugin packages itself — that argument is about the editors'
different and unforgiving archive layouts, and it does not extend to a brand
asset both of them show. There are three copies of this icon and they must be
the same drawing:

    plugins/sigil/plugin.svg          Sigil prefers the SVG
    plugins/sigil/plugin.png          and falls back to the PNG
    plugins/calibre/plugin.png        calibre's `get_icons` reads it from the zip
    plugins/calibre-library/plugin.png  the same mark with a stack behind it

**Two marks now, and the second one exists because of where they meet.** The
library plugin and the editor plugin can both sit in one calibre toolbar, and
until this was written they shipped byte-identical icons — two buttons a user
could not tell apart. The library mark is the same page and the same tick with
two sheets behind it: one book against many, which is the actual difference
between the two plugins, drawn rather than captioned.

Colour is not the discriminator, deliberately. DiapDealer's constraint below is
about themes, and a hue difference is the first thing a theme takes away; a
silhouette difference survives every ground.

Nothing checks that hand-kept copies agree, and a mark edited in one and not
another is a difference only somebody running the other editor would ever see.
The geometry below is the single source; each plugin's tests compare its
shipped file against what this produces.

**Why it rasterises itself.** A PNG needs a rasteriser, and the ones a
contributor might have (rsvg-convert, Inkscape, cairosvg, Pillow) are four
different answers to install. `zlib` and `struct` are in the standard library,
the mark is three shapes, and antialiasing from 36 coverage samples per pixel
is exact where a distance approximation goes wrong at corners. It takes about
a second.

**The mark is a monogram in a container, and the two are separate on purpose
(owner, 2026-09-07).** The monogram is the tick — read as a check here and as
the `veri` **V** when it needs to be, which is what lets it carry across
products without meaning "passed" in one that verifies nothing. The container
says which product: one sheet is epubveri, three sheets is the library
checker. **A new product is a new container around the same glyph**, which is
why `glyph()` and the container builders below never touch each other.

**The palette is two colours, and it is a pair rather than a colour.** Ink
`#111111` outlines every sheet; the body is `#f5c518`. No single colour is
legible on every ground — measured: to clear 3:1 against mid grey you need
L <= 0.076, to clear it against black you need L >= 0.11, and the intersection
is empty. The old teal `#1b5f7a` bore this out at **2.00:1 on a dark UI**. A
pair does what one colour cannot: light grounds are carried by the ink,
dark grounds by the yellow, and **the worst ground of the five measured is
6.71:1** — against 1.47 for the best single colour tried.

**Not green, not red, not amber alone.** The mark contains a tick, and the icon
is the *tool*, not the verdict: it looks the same whether the book is valid or
broken. Green plus a tick claims the book passed; red and amber are severities
this project already prints. Yellow with ink reads as attention rather than as
a judgement, and it is the only pair that also survives every ground.

DiapDealer, who maintains Sigil, put the constraint this way (MobileRead
374939 #22): *"Sigil can have just about any theme colors imaginable on Linux.
Simpler is best when including icons that may need to be visible in any theme
from light to dark (and in between) on three platforms."* The tile this
replaces was legible everywhere and read as a badge dropped into a row of
glyphs; a single-colour glyph would fit the row and disappear on a ground near
its own colour. This is the third answer.
"""

import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
SIGIL = os.path.join(ROOT, "plugins", "sigil")
CALIBRE = os.path.join(ROOT, "plugins", "calibre")
CALIBRE_LIBRARY = os.path.join(ROOT, "plugins", "calibre-library")

#: Everything is described on a 64 grid, which is the SVG's viewBox. The mark
#: fills 44x60 of it: as tall as a full-bleed tile would be, so it does not
#: read small beside one, and narrow enough to still be a page.
GRID = 64.0

PAGE = (0xf5, 0xc5, 0x18)     #: the sheet body
INK = (0x11, 0x11, 0x11)      #: every outline, and the glyph knocked out of it
FOLD = (0xc9, 0x93, 0x0c)     #: the turned-back corner, a shade down
TICK = INK                    #: the monogram, knocked out of the body

#: How far the ink runs outside each sheet. It is what makes the silhouette
#: survive a light ground, so it may not go below about 2.5: at 16 px this is
#: already only 0.65 px and antialiasing is carrying it.
OUTLINE = 2.6

RECT = (10.0, 2.0, 54.0, 62.0)                        #: x0, y0, x1, y1
RADIUS = 4.0
#: The page keeps `x - y - CUT <= 0`, which removes the corner above the
#: diagonal from (41, 2) to (54, 15). The fold triangle is then drawn *inside*
#: the page, below the same diagonal — cut plus tint is what reads as a fold.
CUT = 39.0
FOLD_TRI = [(41.0, 2.0), (54.0, 15.0), (41.0, 15.0)]
#: Two segments, round caps and joins. Nothing here is under 5 units, so at
#: 16 px the thinnest thing on screen is about 1.75 px.
TICK_PTS = [(19.0, 33.0), (28.0, 43.0), (45.0, 22.0)]
TICK_WIDTH = 7.0

#: The library container: a **book**, drawn in calibre's own idiom.
#:
#: The library plugin lives only in calibre, and calibre's toolbar is a row of
#: books — Add books, Get books, Remove books — each a flat coloured cover with
#: a white page block behind it, a short rule near the top, and a dark glyph of
#: the same hue knocked into the middle. Ours is that construction with our
#: yellow and our monogram, so it sits in the row instead of on top of it.
#:
#: **Measured off `add_book.png` rather than eyeballed**, and halved onto this
#: 64 grid: cover x 17-100 / y 14-126, page block x 17-109 / y 3-121 with a
#: ~5px outline, rule x 34-83 / y 27-32, glyph centred at 45.7% across and
#: 68.4% down. Two readings were wrong before the numbers settled it — the
#: white was twice calibre's width because it had been drawn out to the
#: block's *outer* edge with the outline added outside that.
#:
#: **This container drops the ink outline on purpose, and that is a real
#: trade.** calibre's own icons measure about 1.90:1 against a light toolbar —
#: they do not separate from the ground either, and rely on the dark glyph
#: inside. Inside calibre that is the native behaviour and the right call. It
#: is why the *page* container keeps its ink outline: that one also ships in
#: Sigil, where any theme is possible and 6.71:1 is the point.
BOOK_DARK = (0x4a, 0x35, 0x03)     #: the body colour taken down, calibre-style
BOOK_PAPER = (0xff, 0xff, 0xff)    #: the pages behind the cover
BOOK_COVER = (8.5, 6.8, 50.0, 63.0)
BOOK_PAGES = (10.6, 4.5, 52.4, 58.4)     #: the white itself, not its outline
BOOK_PAGE_OUTLINE = 2.1                  #: drawn outside it, flush left
BOOK_RULE = (17.0, 13.4, 41.5, 16.4)
BOOK_RADIUS = 1.2
BOOK_GLYPH = (29.25, 43.75)              #: where the monogram sits
BOOK_GLYPH_SCALE = 0.85

#: The Sigil copy. Built from the constants above rather than kept by hand, so
#: the vector and the raster cannot drift; `MARK`'s scale and origin appear
#: here as the group transform.
#:
#: **The outline is a stroked path under a filled one**, not `paint-order`,
#: which is SVG 2 and not worth betting a plugin icon on. A centred stroke puts
#: half its width inside the shape, so the fill goes on top and what is left
#: outside is exactly `OUTLINE` once the group scale is applied — which is why
#: the width is `2 * OUTLINE / scale` rather than a number typed in.
_SVG_SCALE = 0.92
_SVG_ORIGIN = (2.6, 2.5)
_PAGE_PATH = ("M14 2h27l13 13v43a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4V6a4 4 0 0 1 "
              "4-4z")


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by icon.py — edit the geometry there, not this file. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64"
     height="64" role="img" aria-label="epubveri">
  <title>epubveri</title>
  <g transform="translate(%(ox)s %(oy)s) scale(%(scale)s)">
    <path d="%(page)s" fill="none" stroke="%(ink)s" stroke-width="%(stroke).3f"
          stroke-linejoin="round"/>
    <path d="%(page)s" fill="%(body)s"/>
    <path d="M41 2l13 13H41z" fill="%(fold)s"/>
    <path d="M19 33l9 10 17-21" fill="none" stroke="%(ink)s" stroke-width="7"
          stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>
''' % {
    "ox": _SVG_ORIGIN[0], "oy": _SVG_ORIGIN[1], "scale": _SVG_SCALE,
    "page": _PAGE_PATH, "ink": _hex(INK), "body": _hex(PAGE),
    "fold": _hex(FOLD), "stroke": 2.0 * OUTLINE / _SVG_SCALE,
}


def _in_round_rect(x, y):
    x0, y0, x1, y1 = RECT
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - RADIUS, (y1 - y0) / 2 - RADIUS
    qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
    if qx <= 0 or qy <= 0:
        return max(qx, qy) <= RADIUS
    return math.hypot(qx, qy) <= RADIUS


def _in_page(x, y):
    return _in_round_rect(x, y) and (x - y - CUT) <= 0


def _in_fold(x, y):
    def side(a, b):
        return (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
    a, b, c = FOLD_TRI
    s = (side(a, b), side(b, c), side(c, a))
    return all(v >= 0 for v in s) or all(v <= 0 for v in s)


def _in_tick(x, y):
    half = TICK_WIDTH / 2
    for (ax, ay), (bx, by) in zip(TICK_PTS, TICK_PTS[1:]):
        ex, ey = bx - ax, by - ay
        t = ((x - ax) * ex + (y - ay) * ey) / (ex * ex + ey * ey)
        t = min(1.0, max(0.0, t))
        if math.hypot(x - (ax + t * ex), y - (ay + t * ey)) <= half:
            return True
    return False


def _page(scale, origin, grow=0.0):
    """The sheet silhouette, optionally grown by `grow` grid units.

    Exact rather than approximate, which matters because the growth *is* the
    outline: a rounded rectangle dilated by r is the same rectangle inset by r
    with radius r larger, and a half-plane `x - y - CUT <= 0` dilated by r is
    the same half-plane with CUT moved out by r*sqrt(2). Sampling a distance
    field would round the corners differently from the body and the outline
    would thin where it is most visible.
    """
    x0, y0, x1, y1 = RECT
    r = grow / scale
    X0, Y0, X1, Y1 = x0 - r, y0 - r, x1 + r, y1 + r
    radius = RADIUS + r
    cut = CUT + r * math.sqrt(2)
    dx, dy = origin

    def at(x, y):
        u, v = (x - dx) / scale, (y - dy) / scale
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        hx, hy = (X1 - X0) / 2 - radius, (Y1 - Y0) / 2 - radius
        qx, qy = abs(u - cx) - hx, abs(v - cy) - hy
        if qx <= 0 or qy <= 0:
            inside = max(qx, qy) <= radius
        else:
            inside = math.hypot(qx, qy) <= radius
        return inside and (u - v - cut) <= 0

    return at


def _sheet(scale, origin, glyph=False):
    """One outlined sheet as a `(x, y) -> colour or None` layer.

    `glyph` puts the monogram and the turned corner on it — true for the front
    sheet of any container and false for everything behind it, whose detail
    would never be seen and whose tick would show through the gap between
    sheets at some sizes.
    """
    body = _page(scale, origin)
    outline = _page(scale, origin, OUTLINE)
    dx, dy = origin

    def at(x, y):
        if body(x, y):
            if glyph:
                u, v = (x - dx) / scale, (y - dy) / scale
                if _in_tick(u, v):
                    return TICK
                if _in_fold(u, v):
                    return FOLD
            return PAGE
        return INK if outline(x, y) else None

    return at


#: One sheet: epubveri. Scaled just enough to leave the outline inside the
#: grid, so the drawing itself is the one that has always been here.
MARK = [_sheet(0.92, (2.6, 2.5), glyph=True)]

def _rrect(x0, y0, x1, y1, radius, grow=0.0):
    """A rounded rectangle, optionally dilated — the book is built from four."""
    X0, Y0, X1, Y1 = x0 - grow, y0 - grow, x1 + grow, y1 + grow
    r = max(0.01, radius + grow)

    def at(x, y):
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        hx, hy = (X1 - X0) / 2 - r, (Y1 - Y0) / 2 - r
        qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
        if qx <= 0 or qy <= 0:
            return max(qx, qy) <= r
        return math.hypot(qx, qy) <= r

    return at


def _glyph_at(cx, cy, scale):
    """The monogram, moved and scaled into a container that is not the page.

    The tick's own coordinates are the page's, so a container with different
    proportions places it by transform rather than by redrawing it — which is
    the whole reason glyph and container are separate.
    """
    def at(x, y):
        return _in_tick((x - cx) / scale + 32.0, (y - cy) / scale + 32.5)

    return at


def _book():
    """calibre's book, in our colours, carrying our monogram."""
    cover = _rrect(*BOOK_COVER, BOOK_RADIUS)
    pages = _rrect(*BOOK_PAGES, BOOK_RADIUS)
    edge = _rrect(*BOOK_PAGES, BOOK_RADIUS, BOOK_PAGE_OUTLINE)
    rule = _rrect(*BOOK_RULE, 1.0)
    glyph = _glyph_at(BOOK_GLYPH[0], BOOK_GLYPH[1], BOOK_GLYPH_SCALE)

    def at(x, y):
        if cover(x, y):
            if glyph(x, y) or rule(x, y):
                return BOOK_DARK
            return PAGE
        if pages(x, y):
            return BOOK_PAPER
        if edge(x, y):
            return PAGE
        return None

    return [at]


#: The library checker: one book, calibre's shape.
BOOK = _book()


def _pixels(mark, size, samples=6):
    """RGBA rows with a leading PNG filter byte, straight-alpha."""
    out = bytearray()
    step = GRID / size
    sub = step / samples
    total = float(samples * samples)
    for row in range(size):
        out.append(0)                                  # filter: none
        for col in range(size):
            r = g = b = hits = 0.0
            for sy in range(samples):
                y = row * step + (sy + 0.5) * sub
                for sx in range(samples):
                    x = col * step + (sx + 0.5) * sub
                    c = None
                    for layer in reversed(mark):
                        c = layer(x, y)
                        if c is not None:
                            break
                    if c is None:
                        continue
                    r += c[0]; g += c[1]; b += c[2]; hits += 1
            if hits:
                out += bytes((int(r / hits + .5), int(g / hits + .5),
                              int(b / hits + .5), int(255 * hits / total + .5)))
            else:
                out += b"\x00\x00\x00\x00"
    return bytes(out)


def write_png(path, size=128, mark=None):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    head = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head)
            + chunk(b"IDAT", zlib.compress(_pixels(mark or MARK, size), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(blob)
    return len(blob)


def main():
    svg = os.path.join(SIGIL, "plugin.svg")
    with open(svg, "w", encoding="utf-8") as handle:
        handle.write(SVG)
    print("%s  (%d bytes)" % (svg, len(SVG.encode("utf-8"))))
    for png in (os.path.join(SIGIL, "plugin.png"),
                os.path.join(CALIBRE, "plugin.png")):
        print("%s  (%d bytes)" % (png, write_png(png)))
    # No SVG for this one: calibre reads only the PNG out of the zip, and a
    # second vector file with no consumer is a third copy to keep in step.
    # This file is the source of the drawing either way. It is also the only
    # mark that never reaches Sigil, which is what lets it be calibre-native.
    png = os.path.join(CALIBRE_LIBRARY, "plugin.png")
    print("%s  (%d bytes)" % (png, write_png(png, mark=BOOK)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
