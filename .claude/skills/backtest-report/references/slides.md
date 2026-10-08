# Backtest deck (claude.ai Slides artifact)

A deck tells one research result to people who will not read the report: the question, how it was tested, what
came out against which yardstick, why, and what happens next. It downloads as .pptx or PDF from the artifact, so
it never needs a local file.

## Make it

1. Call the Artifact tool with `action: "quickstart"`, `intent: "slides"`. It returns the Slides type and the
   design systems; follow that type's own instructions for creating the deck and filling its data. Those
   instructions win over anything here about mechanics.
2. Take every number from the report or the PnL page data of the same study. If neither exists yet, build the
   PnL numbers first (references/pnl-analysis.md, step 2); a deck is not where numbers get computed.

## Story, about 8–12 slides

| # | Slide | What it says |
|---|---|---|
| 1 | Title | Study name, date, one-line result |
| 2 | 問題 | What the current strategy does and the one weakness this tests |
| 3 | 假設與判定 | The hypothesis and the pass rule, marked 事先寫死, with the commit |
| 4 | 做法 | Pool, capital, period, costs; one simple diagram of the rule if it has states |
| 5 | 對照組 | Which yardsticks and why each matters |
| 6 | 結果 | The yearly table (or the window summary) of the candidate vs the controls; the verdict |
| 7 | 報酬從哪裡來 | The candidate's attribution, one chart |
| 8 | 比對照組多在哪 | The difference split; the one finding a reader should remember |
| 9 | 穩健性 | Other EMA, pool, capital, gas: a pass / fail grid |
| 10 | 限制 | Same price path, choices made after the fact, approximations |
| 11 | 下一步 | Two or three concrete next tests |

Merge or drop slides for a small result; never drop 對照組 or 限制.

## Per slide

- One message per slide, written as the slide's title in a full sentence ("g_down 的增益主要是買單收到的手續費").
- At most one chart or one table; a table bigger than about 6 × 6 belongs in the report.
- Numbers with signs and units as in the report (`+10.6%`, `−2.2 pt`, `14/16`).
- Charts use the PnL page's component colors and order, so a reader who saw both recognizes them.
- Speaker notes, if the type has them: the caveat behind each number.
