"""
Build a PnL analysis page from its prose and its numbers, then run it once in a stub DOM.

  content  an HTML fragment: header, section headings and prose, and the empty containers the renderer fills
           (#pnl-takeaways, #pnl-tables, #pnl-cum, #pnl-attr, #pnl-diff); see references/pnl-analysis.md
  config   JSON for PNL.render (schema at the top of assets/pnl_lib.js)

The check fails on a script error, on NaN / undefined in anything rendered, or on a container that stayed empty,
so a broken page is caught before it is published.

  python .claude/skills/backtest-report/scripts/build_pnl_page.py \
      --title "多池現貨濾網年度帳" --content content.html --config config.json --out page.html
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")


def build(title: str, content: str, config: dict) -> str:
    shell = open(os.path.join(ASSETS, "pnl_shell.html"), encoding="utf-8").read()
    lib = open(os.path.join(ASSETS, "pnl_lib.js"), encoding="utf-8").read()
    # the config sits inside a <script>: a "</" in any string would end the script early
    data = json.dumps(config, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (shell.replace("__TITLE__", title).replace("__CONTENT__", content)
            .replace("__LIB__", lib).replace("__CONFIG__", data))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--title", required=True, help="2-4 word page name, also the artifact title")
    p.add_argument("--content", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    config = json.load(open(a.config, encoding="utf-8"))
    page = build(a.title, open(a.content, encoding="utf-8").read(), config)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {a.out} ({len(page) / 1024:.0f} KB)")
    r = subprocess.run(["node", os.path.join(HERE, "check_page.js"), a.out], capture_output=True, text=True,
                       encoding="utf-8")
    print(r.stdout, end="")
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit("page check failed")


if __name__ == "__main__":
    main()
