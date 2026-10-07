"""v6 weekly 2026-10-07 explainer: one Manim scene per narration scene (S01..S11).

Timing comes from the JSON named by $V6_TIMINGS (timings.json from tts.py, or
estimated_timings.json from estimate_timings.py). Each narration line is a beat:
its subtitle shows exactly from `start` to `start + dur`, and the beat's
animations are squeezed into that window. Scenes render silent; assemble.py lays
the audio clips on the same clock and muxes.
"""
import json
import os
from pathlib import Path

import numpy as np
from manim import *

HERE = Path(__file__).resolve().parent
TIMINGS = json.loads(Path(os.environ["V6_TIMINGS"]).read_text())
CURVE = json.loads((HERE.parent / "curve_eth_mainnet.json").read_text())

FONT = "PingFang TC"
BG = "#1C1F26"
CARD = "#252A33"
C_BLUE = "#58C4DD"
C_ORANGE = "#F0A35E"
C_GREY = "#8A8F98"
C_DIM = "#4A505A"
C_YEL = "#FFD866"
C_GREEN = "#83C167"
C_WHITE = "#ECEFF4"
SUB_SIZE = 19          # ~34 px em height at 1080p
CONTENT_FLOOR = -2.6   # nothing but the subtitle goes below this

config.background_color = BG


def T(s, size=32, color=C_WHITE, weight=NORMAL):
    return Text(s, font=FONT, font_size=size, color=color, weight=weight)


def vis_w(s):
    return sum(0.55 if ord(c) < 128 else 1.0 for c in s)


def wrap(s, maxw=28):
    """Split a subtitle into at most two lines, preferring a punctuation break near the middle."""
    if vis_w(s) <= maxw:
        return [s]
    def word(c):
        return c.isascii() and (c.isalnum() or c in "-.%$+")

    best = None
    for i in range(1, len(s) - 1):
        c, nxt = s[i], s[i + 1]
        if c in "，。：、；？！":
            pen = 0
        elif word(c) and word(nxt):
            continue                      # never split inside an ASCII token
        elif c == " ":
            pen = 12 if (word(s[i - 1]) and word(nxt)) else 5
        elif nxt in "，。：、；？！）":
            continue                      # never start a line with punctuation
        else:
            pen = 6
        a, b = s[:i + 1].rstrip(), s[i + 1:].lstrip()
        score = max(vis_w(a), vis_w(b)) + pen
        if best is None or score < best[0]:
            best = (score, a, b)
    return [best[1], best[2]]


def card(title, body=None, edge=C_GREY, w=6.2, h=1.5, tsize=30, bsize=24, tcolor=None):
    box = RoundedRectangle(corner_radius=0.15, width=w, height=h, stroke_color=edge,
                           stroke_width=3, fill_color=CARD, fill_opacity=1)
    parts = [T(title, tsize, tcolor or edge, weight=BOLD)]
    if body:
        parts.append(T(body, bsize, C_WHITE))
    txt = VGroup(*parts).arrange(DOWN, buff=0.18)
    if txt.width > w - 0.4:
        txt.scale_to_fit_width(w - 0.4)
    return VGroup(box, txt.move_to(box))


def header(s, color=C_WHITE):
    return T(s, 40, color, weight=BOLD).to_edge(UP, buff=0.4)


class Narrated(Scene):
    SID = None

    def setup(self):
        sc = next(s for s in TIMINGS["scenes"] if s["id"] == self.SID)
        self.L, self.total, self.sub = sc["lines"], sc["total"], None

    # clock ---------------------------------------------------------------
    def now(self):
        return self.renderer.time

    def wait_until(self, t):
        dt = t - self.now()
        if dt > 1 / 60:
            self.wait(dt)

    # subtitles -----------------------------------------------------------
    def show_sub(self, text):
        rows = VGroup(*[T(r, SUB_SIZE, WHITE) for r in wrap(text)]).arrange(DOWN, buff=0.12)
        band = RoundedRectangle(corner_radius=0.1, width=rows.width + 0.6, height=rows.height + 0.3,
                                fill_color=BLACK, fill_opacity=0.6, stroke_width=0)
        band.move_to([0, -3.78 + band.height / 2, 0])
        rows.move_to(band)
        self.sub = VGroup(band, rows)
        self.add_foreground_mobject(self.sub)

    def hide_sub(self):
        if self.sub is not None:
            self.remove_foreground_mobject(self.sub)
            self.remove(self.sub)
            self.sub = None

    # beats ---------------------------------------------------------------
    def say(self, i, *steps):
        """Narration line i. steps: (anims | callable -> anims | None, weight)."""
        L = self.L[i]
        self.wait_until(L["start"])
        self.show_sub(L["text"])
        end = L["start"] + L["dur"]
        budget = end - self.now() - 0.05
        total = sum(w for _, w in steps) or 1
        k = min(1.0, budget / total)
        for anims, w in steps:
            rt = max(w * k, 1 / 15)
            if anims is None:
                self.wait(rt)
                continue
            if callable(anims):
                anims = anims()
            if not isinstance(anims, (list, tuple)):
                anims = [anims]
            self.play(*anims, run_time=rt)
        self.wait_until(end)
        self.hide_sub()

    def finish(self, fade=0.5):
        self.wait_until(self.total - fade)
        mobs = [m for m in self.mobjects if m is not self.sub]
        if mobs:
            self.play(*[FadeOut(m) for m in mobs], run_time=fade)
        self.wait_until(self.total)


# --------------------------------------------------------------------------
class S01(Narrated):
    SID = "s01_karpathy"

    def construct(self):
        title = T("v6 研究週報", 80, C_WHITE, weight=BOLD)
        date = T("2026-10-07", 36, C_GREY)
        tc = VGroup(title, date).arrange(DOWN, buff=0.35).shift(UP * 0.4)
        bar = Line(LEFT * 3, RIGHT * 3, color=C_BLUE, stroke_width=4).next_to(tc, DOWN, buff=0.4)
        self.play(Write(title), run_time=1.2)
        self.play(FadeIn(date, shift=UP * 0.2), Create(bar), run_time=0.8)

        q_name = T("Karpathy", 40, C_YEL, weight=BOLD)
        q_date = T("2026-10-02", 28, C_GREY)
        q = VGroup(q_name, q_date).arrange(RIGHT, buff=0.35, aligned_edge=DOWN).to_edge(UP, buff=0.45)
        sub = T("理解 AI 產出的四種形式", 28, C_GREY).next_to(q, DOWN, buff=0.2)

        specs = [("1", "文字（ASD-STE100）"), ("2", "圖"), ("3", "HTML 網頁"),
                 ("4", "解說影片（3b1b 風格 + ElevenLabs 配音）")]
        tiers = VGroup()
        for n, s in specs:
            box = RoundedRectangle(corner_radius=0.12, width=9.4, height=0.82, stroke_color=C_GREY,
                                   stroke_width=2.5, fill_color=CARD, fill_opacity=1)
            num = T(n, 34, C_YEL, weight=BOLD).move_to(box.get_left() + RIGHT * 0.5)
            lab = T(s, 28, C_WHITE).next_to(num, RIGHT, buff=0.4)
            tiers.add(VGroup(box, num, lab))
        tiers.arrange(UP, buff=0.22).move_to([-2.0, -0.55, 0])
        for t in tiers:
            t.set_opacity(0.3)

        def light(t, color=C_BLUE):
            return [t.animate.set_opacity(1), t[0].animate.set_stroke(color, opacity=1)]

        self.say(0, (None, 0.6), ([FadeOut(VGroup(tc, bar), shift=UP * 0.3)], 0.8),
                 ([FadeIn(q, shift=DOWN * 0.2)], 0.8))
        self.say(1, ([FadeIn(sub)], 0.6),
                 ([LaggedStart(*[FadeIn(t, shift=UP * 0.2) for t in tiers], lag_ratio=0.25)], 2.0))
        self.say(2, (None, 0.5), (lambda: light(tiers[0]), 0.8))
        self.say(3, (lambda: light(tiers[1]), 0.8), (None, 0.4), (lambda: light(tiers[2]), 0.8))

        def grow4():
            t4 = tiers[3]
            return [t4.animate.set_opacity(1).scale(1.07), t4[0].animate.set_stroke(C_YEL, width=5, opacity=1)]
        self.say(4, (None, 0.6), (grow4, 1.0), ([Indicate(tiers[3][1], color=C_YEL, scale_factor=1.4)], 0.8))

        # line 5: no paid voice -> ask AI for a free alternative
        tip = card("沒有付費配音？", "請 AI 找免費替代", C_GREY, w=3.6, h=1.25, tsize=26, bsize=24,
                   tcolor=C_WHITE).move_to([4.95, -1.0, 0])
        self.say(5, (None, 0.5), ([FadeIn(tip, shift=LEFT * 0.2)], 0.8))

        arrow = Arrow(RIGHT * 0.1, LEFT * 0.8, color=C_YEL, stroke_width=6, buff=0)
        note = VGroup(T("這支影片", 32, C_YEL, weight=BOLD), T("就是第 4 層", 32, C_YEL, weight=BOLD)).arrange(DOWN, buff=0.1)
        grp = VGroup(arrow, note).arrange(RIGHT, buff=0.15)
        grp.next_to(tiers[3], RIGHT, buff=0.15)
        voice = T("配音：微軟免費語音", 24, C_GREEN).next_to(tip, UP, buff=0.3)
        self.say(6, (None, 0.6), ([GrowArrow(arrow), Write(note)], 1.2), (None, 0.6),
                 ([FadeIn(voice, shift=UP * 0.15)], 0.7))
        self.finish()


class S02(Narrated):
    SID = "s02_thesis"

    def construct(self):
        a = T("9 類變化", 64, C_WHITE, weight=BOLD)
        arr = T("→", 64, C_GREY)
        b = T("2 類有用", 64, C_BLUE, weight=BOLD)
        stmt = VGroup(a, arr, b).arrange(RIGHT, buff=0.4).move_to([0, 2.7, 0])
        sq = VGroup(*[RoundedRectangle(corner_radius=0.08, width=0.8, height=0.8, stroke_width=0,
                                       fill_color=C_DIM, fill_opacity=1) for _ in range(9)])
        sq.arrange(RIGHT, buff=0.3).move_to([0, 1.15, 0])
        cap = T("112 個實驗 · 3 天", 26, C_GREY).next_to(sq, DOWN, buff=0.3)

        self.say(0, ([Write(a)], 0.8),
                 ([LaggedStart(*[GrowFromCenter(s) for s in sq], lag_ratio=0.12)], 1.6),
                 ([FadeIn(cap)], 0.5))

        l1 = T("refill 時機", 26, C_BLUE).next_to(sq[1], DOWN, buff=0.3)
        l2 = T("swap routing", 26, C_BLUE).next_to(sq[6], DOWN, buff=0.3)
        self.say(1, ([FadeOut(cap), FadeIn(arr), Write(b)], 0.9),
                 ([sq[1].animate.set_fill(C_BLUE), FadeIn(l1, shift=UP * 0.15)], 0.7),
                 ([sq[6].animate.set_fill(C_BLUE), FadeIn(l2, shift=UP * 0.15)], 0.7))

        pivot = np.array([0, -1.55, 0])
        ang = ValueTracker(0)
        half = 2.8

        def end(sign):
            a_ = ang.get_value()
            return pivot + sign * half * np.array([np.cos(a_), np.sin(a_), 0])

        plank = always_redraw(lambda: Line(end(-1), end(1), color=C_GREY, stroke_width=8))
        fulcrum = Triangle(color=C_GREY, fill_color=C_GREY, fill_opacity=1).scale(0.35)
        fulcrum.move_to(pivot + DOWN * 0.3)
        eth = T("ETH", 32, C_WHITE, weight=BOLD)
        btc = T("BTC", 32, C_WHITE, weight=BOLD)

        def follow(sign):
            def upd(m):
                p = end(sign)
                m.move_to(p + UP * 0.4)
                up = p[1] > pivot[1] + 0.02
                down = p[1] < pivot[1] - 0.02
                m.set_color(C_BLUE if up else C_ORANGE if down else C_WHITE)
            return upd

        eth.add_updater(follow(-1))
        btc.add_updater(follow(1))
        tilt = 0.2
        self.say(2, ([FadeIn(fulcrum), Create(plank), FadeIn(eth), FadeIn(btc)], 0.6),
                 ([ang.animate.set_value(-tilt)], 0.8), (None, 0.3),
                 ([ang.animate.set_value(tilt)], 1.0), (None, 0.3),
                 ([ang.animate.set_value(-tilt)], 1.0), (None, 0.2))
        eth.clear_updaters(); btc.clear_updaters()
        self.remove(plank)
        self.add(Line(end(-1), end(1), color=C_GREY, stroke_width=8))
        self.finish()


class S03(Narrated):
    SID = "s03_context"

    def construct(self):
        h = header("v6 怎麼運作")
        self.say(0, ([Write(h)], 1.0))

        def box(t1, t2, color):
            r = RoundedRectangle(corner_radius=0.15, width=3.7, height=1.25, stroke_color=color,
                                 stroke_width=3, fill_color=CARD, fill_opacity=1)
            g = VGroup(T(t1, 28, color, weight=BOLD), T(t2, 24, C_WHITE)).arrange(DOWN, buff=0.12)
            return VGroup(r, g.move_to(r))

        b1 = box("① 訊號", "EMA 90–120", C_GREY).move_to([-4.6, 2.0, 0])
        b2 = box("② F 引擎", "部署比例 F", C_GREY).move_to([0, 2.0, 0])
        b3 = box("③ LP ladder", "±20% 谷形", C_BLUE).move_to([4.6, 2.0, 0])
        a1 = Arrow(b1.get_right(), b2.get_left(), buff=0.1, color=C_GREY)
        a2 = Arrow(b2.get_right(), b3.get_left(), buff=0.1, color=C_GREY)
        self.say(1, ([FadeIn(b1, shift=RIGHT * 0.2)], 0.8), ([GrowArrow(a1)], 0.4),
                 ([FadeIn(b2, shift=RIGHT * 0.2)], 0.8))

        base = -1.45
        xs = np.linspace(-3.2, 3.2, 17)
        bars = VGroup()
        for x in xs:
            hgt = 0.25 + 1.85 * (1 - np.exp(-(x / 1.5) ** 2))
            bars.add(Rectangle(width=0.32, height=hgt, stroke_width=0, fill_color=C_BLUE,
                               fill_opacity=0.75).move_to([x, base + hgt / 2, 0]))
        axis = Line([-3.6, base, 0], [3.6, base, 0], color=C_GREY, stroke_width=2)
        price = DashedLine([0, base, 0], [0, 0.95, 0], color=C_YEL, stroke_width=3)
        plab = T("價格", 22, C_YEL).next_to(price, UP, buff=0.08)
        lo = T("−20%", 22, C_GREY).next_to(axis.get_start(), DOWN, buff=0.12)
        hi = T("+20%", 22, C_GREY).next_to(axis.get_end(), DOWN, buff=0.12)
        self.say(2, ([GrowArrow(a2), FadeIn(b3, shift=RIGHT * 0.2)], 0.8),
                 ([Create(axis), FadeIn(lo), FadeIn(hi)], 0.5),
                 ([LaggedStart(*[GrowFromEdge(b, DOWN) for b in bars], lag_ratio=0.08)], 1.6),
                 ([Create(price), FadeIn(plab)], 0.6))

        def tag(s):
            r = RoundedRectangle(corner_radius=0.12, width=2.3, height=0.62, stroke_color=C_YEL,
                                 stroke_width=2.5, fill_color=CARD, fill_opacity=1)
            return VGroup(r, T(s, 24, C_YEL).move_to(r))

        tags = [tag("refill"), tag("exit / stop"), tag("rebuild"), tag("執行")]
        pos = [(-5.4, 0.1), (-5.4, -1.0), (5.4, 0.1), (5.4, -1.0)]
        for t, (x, y) in zip(tags, pos):
            t.move_to([x, y, 0])
        self.say(3, *[([FadeIn(t, scale=1.3)], 0.6) for t in tags])
        self.finish()


class S04(Narrated):
    SID = "s04_week"
    ROWS = [("fee-tier 分組", 9, 3, 22, 0), ("refill 時機", 18, 2, 3, 0), ("F 引擎結構", 16, 0, 0, 0),
            ("rebuild／置中", 12, 0, 2, 0), ("exit／stop", 5, 3, 0, 0), ("macro 事件", 1, 1, 4, 0),
            ("ladder 形狀", 0, 5, 0, 0), ("swap routing", 1, 0, 1, 1), ("閒置資金", 1, 0, 1, 0)]

    def construct(self):
        x0, unit, bh = -3.3, 0.27, 0.4
        legend = VGroup()
        for c, s in [(C_DIM, "dev 淘汰"), (C_ORANGE, "換時段或池子後失敗"), (C_BLUE, "通過")]:
            sw = Square(0.28, stroke_width=0, fill_color=c, fill_opacity=1)
            legend.add(VGroup(sw, T(s, 24, C_WHITE)).arrange(RIGHT, buff=0.15))
        legend.arrange(RIGHT, buff=0.6).move_to([0, 3.45, 0])

        labels, bars, totals, rows = VGroup(), VGroup(), VGroup(), []
        for k, (name, g, o, b, u) in enumerate(self.ROWS):
            y = 2.75 - k * 0.6
            lab = T(name, 24, C_WHITE)
            lab.move_to([x0 - 0.25 - lab.width / 2, y, 0])
            segs, x = VGroup(), x0
            for n, c in [(g, C_DIM), (o, C_ORANGE), (b, C_BLUE)]:
                if n:
                    segs.add(Rectangle(width=n * unit, height=bh, stroke_width=0, fill_color=c,
                                       fill_opacity=1).move_to([x + n * unit / 2, y, 0]))
                    x += n * unit
            if u:
                segs.add(Rectangle(width=u * unit, height=bh, stroke_color=C_GREY, stroke_width=2,
                                   fill_opacity=0).move_to([x + u * unit / 2, y, 0]))
                x += u * unit
            tot = T(str(g + o + b + u), 24, C_GREY).move_to([x + 0.35, y, 0])
            labels.add(lab); bars.add(segs); totals.add(tot)
            rows.append(VGroup(lab, segs, tot))

        self.say(0, ([FadeIn(legend)], 0.8), ([FadeIn(labels, lag_ratio=0.1)], 0.8),
                 ([LaggedStart(*[GrowFromEdge(b, LEFT) for b in bars], lag_ratio=0.15)], 2.4),
                 ([FadeIn(totals)], 0.5))

        def veil(k, op=0.72):
            r = rows[k]
            return Rectangle(width=13.4, height=0.56, stroke_width=0, fill_color=BG,
                             fill_opacity=op).move_to([0, r.get_center()[1], 0])

        bad = [2, 3, 4, 6]
        veils1 = VGroup(*[veil(k) for k in range(9) if k not in bad])
        marks = VGroup(*[T("✗", 26, C_ORANGE).move_to([totals[k].get_center()[0] + 0.45, totals[k].get_center()[1], 0])
                         for k in bad])
        self.say(1, ([FadeIn(veils1)], 0.6), ([LaggedStart(*[FadeIn(m, scale=1.5) for m in marks], lag_ratio=0.2)], 1.0))

        veils2 = VGroup(*[veil(k) for k in range(1, 9)])
        box = SurroundingRectangle(rows[0], color=C_YEL, buff=0.12, corner_radius=0.08)
        self.say(2, ([FadeOut(veils1), FadeOut(marks)], 0.5), ([FadeIn(veils2)], 0.5), ([Create(box)], 0.8))
        self.finish()


class S05(Narrated):
    SID = "s05_refill"
    LOWS = [96.0, 93.0, 94.0, 90.0, 91.0, 92.0, 88.0, 89.0, 90.0, 91.0, 86.0, 87.0, 89.0, 90.5]
    PRE = [(101.8, 103.0), (100.6, 102.5), (95.5, 101.5)]  # (low, close) before the break

    def construct(self):
        h = header("① refill 時機", C_BLUE)

        def X(d):  # d = day index, pre-days negative
            return -6.3 + (d + 3) * 0.48

        def Y(p):
            return -2.0 + (p - 84) / 20 * 4.4

        ema = lambda d: 101.5 - (d + 3) * 0.15
        ema_line = DashedLine([X(-3.4), Y(ema(-3.4)), 0], [X(13.4), Y(ema(13.4)), 0], color=C_YEL,
                              stroke_width=3, dash_length=0.12)
        ema_lab = T("EMA", 22, C_YEL).next_to(ema_line.get_end(), RIGHT, buff=0.1)

        lows = [l for l, _ in self.PRE] + self.LOWS
        closes = [c for _, c in self.PRE] + [l + 1.8 for l in self.LOWS]
        days = list(range(-3, 14))
        wicks, dots, segs = VGroup(), VGroup(), VGroup()
        for j, d in enumerate(days):
            hi = closes[j] + 1.0
            wicks.add(Line([X(d), Y(lows[j]), 0], [X(d), Y(hi), 0], color=C_GREY, stroke_width=3))
            dots.add(Dot([X(d), Y(closes[j]), 0], radius=0.05, color=C_WHITE))
            if j:
                segs.add(Line(dots[j - 1].get_center(), dots[j].get_center(), color=C_WHITE, stroke_width=2.5))

        pre = VGroup(*wicks[:3], *dots[:3], *segs[:2])
        self.say(0, ([Write(h)], 0.8), ([Create(ema_line), FadeIn(ema_lab)], 0.8), ([FadeIn(pre)], 0.6))

        # counters
        c1_lab = T("v6 refill 天數", 26, C_GREY).move_to([4.7, 1.7, 0])
        c1 = T("0", 72, C_WHITE, weight=BOLD).move_to([4.7, 0.85, 0])
        c2_lab = T("v6.75（不算新低日）", 26, C_BLUE).move_to([4.7, -0.35, 0])
        c2 = T("0", 72, C_BLUE, weight=BOLD).move_to([4.7, -1.2, 0])
        my = -2.3
        grey_marks = VGroup(*[Dot([X(d), my, 0], radius=0.07, color=C_GREY) for d in range(14)])

        steps = [([FadeIn(c1_lab), FadeIn(c1)], 0.4)]
        for d in range(14):
            j = d + 3
            new = T(str(d + 1), 72, C_WHITE, weight=BOLD).move_to(c1)
            steps.append(([Create(wicks[j]), Create(segs[j - 1]), FadeIn(dots[j]), FadeIn(grey_marks[d]),
                           Transform(c1, new)], 0.32))
        self.say(1, *steps)

        run_min = min(l for l, _ in self.PRE)
        steps = [([FadeIn(c2_lab), FadeIn(c2), grey_marks.animate.set_opacity(0.25)], 0.5)]
        count = 0
        for d in range(14):
            j = d + 3
            p = [X(d), my, 0]
            if self.LOWS[d] < run_min:
                run_min = self.LOWS[d]
                cross = VGroup(Line([-0.11, -0.11, 0], [0.11, 0.11, 0]), Line([-0.11, 0.11, 0], [0.11, -0.11, 0]))
                cross.set_stroke(C_ORANGE, 5).move_to(p)
                steps.append(([FadeIn(cross, scale=1.6), wicks[j].animate.set_color(C_ORANGE)], 0.32))
            else:
                count += 1
                new = T(str(count), 72, C_BLUE, weight=BOLD).move_to(c2)
                steps.append(([FadeIn(Dot(p, radius=0.08, color=C_BLUE), scale=1.5), Transform(c2, new)], 0.32))
        self.say(2, (None, 1.2), *steps)

        chart = [m for m in self.mobjects if m is not h and m is not self.sub]
        y_lab = T("2021 ETH 年化", 32, C_WHITE)
        v0 = T("7.0%", 60, C_GREY, weight=BOLD)
        ar = T("→", 52, C_GREY)
        v1 = T("21.4%", 72, C_BLUE, weight=BOLD)
        big = VGroup(y_lab, v0, ar, v1).arrange(RIGHT, buff=0.4).move_to([0, 1.5, 0])
        self.say(3, ([FadeOut(Group(*chart))], 0.6), ([FadeIn(y_lab), FadeIn(v0)], 0.6),
                 ([FadeIn(ar), FadeIn(v1, shift=LEFT * 0.3)], 0.8))

        r1 = VGroup(T("全歷史 mainnet ETH 兩池", 28, C_WHITE), T("+1.5～2.1 pts", 40, C_BLUE, weight=BOLD)).arrange(RIGHT, buff=0.4)
        r2 = VGroup(T("BTC 兩池", 28, C_WHITE), T("+0.06（雜訊）", 40, C_GREY, weight=BOLD)).arrange(RIGHT, buff=0.4)
        VGroup(r1, r2).arrange(DOWN, buff=0.35, aligned_edge=LEFT).move_to([0, 0.0, 0])
        self.say(4, ([FadeIn(r1, shift=UP * 0.2)], 0.8), (None, 0.6), ([FadeIn(r2, shift=UP * 0.2)], 0.8))

        lab = T("外部訊號控制 refill：", 28, C_WHITE)
        chips = VGroup(*[card(s, None, C_ORANGE, w=1.9, h=0.62, tsize=24) for s in ["funding", "gas", "成交量"]])
        chips.arrange(RIGHT, buff=0.25)
        verdict = T("全部無效", 30, C_ORANGE, weight=BOLD)
        row = VGroup(lab, chips, verdict).arrange(RIGHT, buff=0.35).move_to([0, -1.75, 0])
        self.say(5, ([FadeIn(lab)], 0.5), ([LaggedStart(*[FadeIn(c, shift=UP * 0.2) for c in chips], lag_ratio=0.3)], 1.0),
                 ([Write(verdict)], 0.6))
        self.finish()


class S06(Narrated):
    SID = "s06_routing"

    def construct(self):
        h = header("② swap routing", C_BLUE)
        self.say(0, ([Write(h)], 1.0))

        src = card("USDC", None, C_GREY, w=1.7, h=0.8, tsize=28, tcolor=C_WHITE).move_to([-5.2, 0.75, 0])
        dst = card("WBTC", None, C_GREY, w=1.7, h=0.8, tsize=28, tcolor=C_WHITE).move_to([5.2, 0.75, 0])
        pa = card("WBTC 0.3%", None, C_ORANGE, w=3.2, h=0.8, tsize=28).move_to([0, 1.75, 0])
        pb = card("WBTC/ETH 0.05%", None, C_BLUE, w=3.2, h=0.8, tsize=28).move_to([0, -0.25, 0])

        def path(pool, color):
            p1 = VMobject(stroke_color=color, stroke_width=5).set_points_as_corners(
                [src.get_right(), [pool.get_left()[0] - 0.6, pool.get_center()[1], 0], pool.get_left()])
            corner = np.array([pool.get_right()[0] + 0.6, pool.get_center()[1], 0])
            p2 = Line(pool.get_right(), corner, color=color, stroke_width=5)
            p3 = Arrow(corner, dst.get_left(), buff=0, color=color, stroke_width=5,
                       max_tip_length_to_length_ratio=0.12)
            return VGroup(p1, p2, p3)

        A = path(pa, C_ORANGE)
        B = path(pb, C_BLUE)
        fa = T("手續費 0.3%", 24, C_ORANGE).next_to(pa, UP, buff=0.12)
        fb = T("手續費 0.05%", 24, C_BLUE).next_to(pb, DOWN, buff=0.12)
        lab = T("WBTC 年化", 30, C_WHITE)
        v0 = T("17.3%", 52, C_GREY, weight=BOLD)
        ar = T("→", 48, C_GREY)
        v1 = T("18.2%", 60, C_BLUE, weight=BOLD)
        num = VGroup(lab, v0, ar, v1).arrange(RIGHT, buff=0.35).move_to([0, -1.85, 0])
        self.say(1, ([FadeIn(src), FadeIn(dst), FadeIn(pa), FadeIn(pb)], 0.6),
                 ([Create(A), FadeIn(fa)], 1.0), (None, 0.3),
                 ([A[0].animate.set_stroke(opacity=0.2), A[1].animate.set_stroke(opacity=0.2),
                   A[2].animate.set_opacity(0.2), fa.animate.set_opacity(0.35), pa.animate.set_opacity(0.4)], 0.4),
                 ([Create(B), FadeIn(fb)], 1.0),
                 ([FadeIn(lab), FadeIn(v0)], 0.4), ([FadeIn(ar), FadeIn(v1, shift=LEFT * 0.2)], 0.6))

        diagram = VGroup(src, dst, pa, pb, A, B, fa, fb, num)
        half = T("半有用", 32, C_GREY, weight=BOLD).move_to([0, 2.4, 0])
        c1 = card("macro 事件規則", "rebuild ×2，gas $34k > 收益 $13.6k", C_GREY, w=8.5, h=1.45).move_to([0, 1.0, 0])
        c2 = card("fee-tier 分組", "ETH 一套、WBTC 一套；全歷史只贏 3/7 池", C_GREY, w=8.5, h=1.45).move_to([0, -0.8, 0])
        self.say(2, ([FadeOut(diagram)], 0.6), ([FadeIn(half)], 0.4), ([FadeIn(c1, shift=UP * 0.2)], 0.8))
        self.say(3, (None, 0.4), ([FadeIn(c2, shift=UP * 0.2)], 0.8))
        self.finish()


class S07(Narrated):
    SID = "s07_nohelp"

    def construct(self):
        h = VGroup(T("沒用的四類", 40, C_ORANGE, weight=BOLD), T("43 個實驗", 32, C_GREY)).arrange(RIGHT, buff=0.4)
        h.to_edge(UP, buff=0.4)
        specs = [("F 引擎", "16 個全淘汰"), ("rebuild／置中", "ETH 好、WBTC 手續費少一半"),
                 ("exit／stop", "拿掉 lower stop：2021 +4.5% → −24.6%"), ("ladder 形狀", "加寬 = 加 beta")]
        pos = [(-3.4, 1.55), (3.4, 1.55), (-3.4, -0.2), (3.4, -0.2)]
        cards = [card(t, b, C_ORANGE, w=6.4, h=1.5).move_to([x, y, 0]) for (t, b), (x, y) in zip(specs, pos)]
        self.say(0, ([Write(h)], 1.0))
        for i in range(3):
            self.say(i + 1, (None, 0.3), ([FadeIn(cards[i], shift=UP * 0.2)], 0.8))
        n43 = T("43", 64, C_ORANGE, weight=BOLD)
        arr = T("→", 56, C_GREY)
        n0 = T("0 通過", 64, C_WHITE, weight=BOLD)
        big = VGroup(n43, arr, n0).arrange(RIGHT, buff=0.4).move_to([0, -1.85, 0])
        self.say(4, ([FadeIn(cards[3], shift=UP * 0.2)], 0.8), (None, 0.2),
                 ([FadeIn(n43)], 0.4), ([FadeIn(arr), FadeIn(n0, shift=LEFT * 0.2)], 0.6))
        self.finish()


class S08(Narrated):
    SID = "s08_fullhist"

    def construct(self):
        dates = CURVE["dates"]
        n = len(dates)
        xl, xr, yb, yt, vmax = -5.6, 4.6, -2.05, 2.55, 240

        def P(i, v):
            return np.array([xl + (xr - xl) * i / (n - 1), yb + (yt - yb) * v / vmax, 0])

        title = T("mainnet ETH 0.05% 淨值（$k，本金 $100k）", 28, C_WHITE).to_edge(UP, buff=0.4)
        grid = VGroup()
        for v in (50, 100, 150, 200):
            grid.add(Line(P(0, v), P(n - 1, v), color=C_DIM, stroke_width=1.2))
            grid.add(T(str(v), 20, C_GREY).next_to(P(0, v), LEFT, buff=0.15))
        for yr in range(2022, 2027):
            i = next(k for k, d in enumerate(dates) if d.startswith(str(yr)))
            grid.add(DashedLine(P(i, 0), P(i, vmax), color=C_DIM, stroke_width=1, dash_length=0.06))
            grid.add(T(str(yr), 20, C_GREY).move_to(P(i, 0) + DOWN * 0.3))
        axis = Line(P(0, 0), P(n - 1, 0), color=C_GREY, stroke_width=2)

        def curve(key, color, width):
            return VMobject(stroke_color=color, stroke_width=width).set_points_as_corners(
                [P(i, v) for i, v in enumerate(CURVE[key])])

        hold = curve("hold_eth", "#5F6670", 2.5)
        spec = curve("spec_v1", C_GREY, 3.5)
        v675 = curve("v6_75", C_BLUE, 4.5)
        self.say(0, ([FadeIn(title), Create(axis), FadeIn(grid)], 0.8),
                 ([Create(hold, rate_func=linear), Create(spec, rate_func=linear), Create(v675, rate_func=linear)], 3.0))

        def end_lab(key, s, color):
            return T(s, 22, color, weight=BOLD).next_to(P(n - 1, CURVE[key][-1]), RIGHT, buff=0.12)

        lb = end_lab("v6_75", "v6.75 212.6", C_BLUE).shift(UP * 0.08)
        ls = end_lab("spec_v1", "spec v1 197.7", C_GREY).shift(DOWN * 0.08)
        lh = end_lab("hold_eth", "持有 ETH 75.8", "#8C939C")
        self.say(1, ([FadeIn(lb), Indicate(v675, color=C_BLUE, scale_factor=1.0)], 0.9),
                 ([FadeIn(ls)], 0.7), ([FadeIn(lh)], 0.7))

        chart = VGroup(title, grid, axis, hold, spec, v675, lb, ls, lh)
        pools = [("ETH mainnet\n0.05%", 1), ("ETH mainnet\n0.3%", 1), ("ETH Base\n0.3%", 1), ("ETH Base\n0.05%", 0),
                 ("ETH Arb\n0.05%", 0), ("WBTC mainnet\n0.3%", 1), ("cbBTC Base\n0.05%", 1)]
        dots, labs = VGroup(), VGroup()
        for k, (name, win) in enumerate(pools):
            x = -6.0 + k * 2.0
            dots.add(Circle(radius=0.42, stroke_width=0, fill_color=C_BLUE if win else C_ORANGE, fill_opacity=1).move_to([x, 0.6, 0]))
            labs.add(VGroup(*[T(r, 18, C_WHITE) for r in name.split("\n")]).arrange(DOWN, buff=0.08).move_to([x, -0.45, 0]))
        score = VGroup(T("7 池全歷史", 34, C_WHITE), T("5 贏", 40, C_BLUE, weight=BOLD),
                       T("2 輸", 40, C_ORANGE, weight=BOLD)).arrange(RIGHT, buff=0.45).move_to([0, 2.3, 0])
        hl = SurroundingRectangle(VGroup(dots[:2], labs[:2]), color=C_YEL, buff=0.15, corner_radius=0.1)
        hl_t = T("真正有差", 28, C_YEL, weight=BOLD).next_to(hl, DOWN, buff=0.15)
        self.say(2, ([FadeOut(chart)], 0.6), ([FadeIn(score)], 0.5),
                 ([LaggedStart(*[GrowFromCenter(d) for d in dots], lag_ratio=0.12), FadeIn(labs)], 1.2),
                 ([Create(hl), FadeIn(hl_t)], 0.7))
        self.finish()


class S09(Narrated):
    SID = "s09_lessons"

    def construct(self):
        h = header("四個教訓")
        self.say(0, ([Write(h)], 1.0))
        texts = ["一個資產變好，另一個通常變差", "所有通過的變體，都是同一個發現",
                 "rebuild 越多，gas 越吃掉收益", "訊號來源比規則細節重要"]
        ys = [2.25, 0.95, -0.35, -1.65]
        ix = -4.4

        for k, (s, y) in enumerate(zip(texts, ys)):
            num = T(f"0{k + 1}", 36, C_YEL, weight=BOLD).move_to([-6.1, y, 0])
            txt = T(s, 30, C_WHITE)
            txt.move_to([-3.0 + txt.width / 2, y, 0])
            if k == 0:
                plank = Line([ix - 0.8, y - 0.1, 0], [ix + 0.8, y - 0.1, 0], color=C_GREY, stroke_width=5)
                e = T("ETH", 16, C_BLUE).next_to(plank.get_start(), UP, buff=0.06)
                b = T("BTC", 16, C_ORANGE).next_to(plank.get_end(), UP, buff=0.06)
                tri = Triangle(color=C_GREY, fill_opacity=1).scale(0.13).move_to([ix, y - 0.25, 0])
                saw = VGroup(plank, e, b)
                piv = np.array([ix, y - 0.1, 0])
                steps = [([FadeIn(num), FadeIn(txt), FadeIn(tri), FadeIn(saw)], 0.7),
                         ([Rotate(saw, 0.3, about_point=piv)], 0.6), ([Rotate(saw, -0.6, about_point=piv)], 0.8)]
            elif k == 1:
                tgt = np.array([ix + 0.55, y + 0.12, 0])
                arrows = VGroup(*[Arrow([ix - 0.9, y + 0.12 + dy, 0], tgt, buff=0.08, stroke_width=3,
                                        max_tip_length_to_length_ratio=0.15, color=C_BLUE)
                                  for dy in (-0.4, -0.2, 0, 0.2, 0.4)])
                dot = Dot(tgt, radius=0.09, color=C_YEL)
                lab = T("no-new-low", 16, C_YEL).move_to([ix, y - 0.42, 0])
                steps = [([FadeIn(num), FadeIn(txt)], 0.5),
                         ([LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.15)], 1.0),
                         ([FadeIn(dot, scale=2), FadeIn(lab)], 0.5)]
            elif k == 2:
                fr1 = Rectangle(width=0.32, height=0.85, stroke_color=C_GREY, stroke_width=2).move_to([ix - 0.35, y + 0.05, 0])
                fr2 = fr1.copy().move_to([ix + 0.35, y + 0.05, 0])
                r_fill = Rectangle(width=0.32, height=0.75, stroke_width=0, fill_color=C_GREY, fill_opacity=1)
                g_fill = Rectangle(width=0.32, height=0.8, stroke_width=0, fill_color=C_ORANGE, fill_opacity=1)
                r_fill.align_to(fr1, DOWN).set_x(fr1.get_x())
                g_fill.align_to(fr2, DOWN).set_x(fr2.get_x())
                l1 = T("rebuild", 14, C_GREY).next_to(fr1, DOWN, buff=0.05)
                l2 = T("gas", 14, C_ORANGE).next_to(fr2, DOWN, buff=0.05)
                steps = [([FadeIn(num), FadeIn(txt), FadeIn(fr1), FadeIn(fr2), FadeIn(l1), FadeIn(l2)], 0.6),
                         ([GrowFromEdge(r_fill, DOWN)], 0.6), ([GrowFromEdge(g_fill, DOWN)], 0.8)]
            else:
                old = T("pool price", 18, C_GREY).move_to([ix, y + 0.05, 0])
                new = T("Binance close", 18, C_BLUE, weight=BOLD).move_to([ix, y + 0.05, 0])
                strike = Line(old.get_left(), old.get_right(), color=C_ORANGE, stroke_width=3)
                steps = [([FadeIn(num), FadeIn(txt), FadeIn(old)], 0.6), ([Create(strike)], 0.4),
                         ([FadeOut(strike), ReplacementTransform(old, new)], 0.8)]
            self.say(k + 1, *steps)
        self.finish()


class S10(Narrated):
    SID = "s10_impact"

    def construct(self):
        h = header("對策略的影響")
        self.say(0, ([Write(h)], 1.0))
        specs = [("−15", C_ORANGE, "舊 v6 落後 spec v1（pts）"), ("7 池", C_WHITE, "全歷史判定"),
                 ("1 條", C_BLUE, "值得留下的規則：no-new-low")]
        for k, (big, color, cap) in enumerate(specs):
            x = (-4.4, 0, 4.4)[k]
            b = T(big, 100, color, weight=BOLD).move_to([x, 0.7, 0])
            c = T(cap, 24, C_GREY).next_to(b, DOWN, buff=0.4)
            if c.width > 3.9:
                c.scale_to_fit_width(3.9)
            self.say(k + 1, (None, 0.3), ([FadeIn(b, scale=1.4)], 0.8), ([FadeIn(c, shift=UP * 0.15)], 0.6))
        self.finish()


class S11(Narrated):
    SID = "s11_summary"

    def construct(self):
        h = header("總結")
        key = T("v6 的優勢在 EMA 下方的分段補回", 40, C_YEL, weight=BOLD).move_to([0, -0.85, 0])
        self.say(0, ([FadeIn(h)], 0.5), ([Write(key)], 1.6))

        def panel(title, items, color, x):
            box = RoundedRectangle(corner_radius=0.15, width=6.0, height=2.3, stroke_color=color, stroke_width=3,
                                   fill_color=CARD, fill_opacity=1).move_to([x, 1.45, 0])
            g = VGroup(T(title, 34, color, weight=BOLD), *[T(s, 26, C_WHITE) for s in items]).arrange(DOWN, buff=0.18)
            return VGroup(box, g.move_to(box))

        good = panel("有用", ["refill 時機", "swap routing"], C_BLUE, -3.3)
        bad = panel("沒用", ["F 引擎 · rebuild · stop", "ladder · 外部訊號"], C_ORANGE, 3.3)
        self.say(1, ([FadeIn(good, shift=RIGHT * 0.2)], 0.8), ([FadeIn(bad, shift=LEFT * 0.2)], 0.8))
        nxt = T("下一步：用 2026-09-17 之後的新資料驗證 no-new-low", 28, C_WHITE).move_to([0, -1.9, 0])
        self.say(2, ([FadeIn(nxt, shift=UP * 0.15)], 0.8))
        self.finish(fade=0.8)
