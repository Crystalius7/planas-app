#!/usr/bin/env python
"""boardcheck.py - renders every handwritten-board line in a headless browser and refuses a layout a reader would misread.

WHY. Owner 2026-09-12, from a screenshot of "1/9 = 1/3² = 3⁻²" where the small 2 sat on the fraction bar instead of on the 3:
"make sure that never happens anywhere again in this system". A power or index inside a fraction's DENOMINATOR or under a
root's overline must sit fully BELOW the bar / overline; one inside a NUMERATOR must not cross the bar. The rule is checked
on the rendered pixels, not on the markup, so any future CSS or markup change that re-creates the defect is refused at
build time: tools/topic.py check/build runs this for every content JSON that carries boards, and a missing browser is said
out loud (BOARD LAYOUT NOT CHECKED), never passed silently.

    python tools/boardcheck.py study/matematika/rugsejis.json [more.json ...]   # "0 layout problems" or a list, exit 1
    python tools/boardcheck.py --self-test                                       # proves the check catches the 2026-09-12 case
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
FONTS = "https://fonts.googleapis.com/css2?family=Caveat:wght@500;600;700&family=Shantell+Sans:wght@400;600;700&display=swap"

# the same measurement for every line: scripts inside a denominator / under a root overline stay below the bar,
# scripts inside a numerator stay above it (half a pixel of tolerance for anti-aliasing)
MEASURE_JS = """
() => {
  const out = [];
  document.querySelectorAll('.bd-l, .bd-im').forEach((l, li) => {
    const src = l.dataset.src || '';
    l.querySelectorAll('.bd-fr').forEach(fr => {
      const nu = fr.querySelector(':scope>.bd-nu'), de = fr.querySelector(':scope>.bd-de');
      if (!nu || !de) return;
      const bar = nu.getBoundingClientRect().bottom;
      de.querySelectorAll('sup,sub').forEach(s => { const r = s.getBoundingClientRect();
        if (r.top < bar - 0.5) out.push([src, 'a power/index in the DENOMINATOR rises onto the fraction bar', s.textContent]); });
      nu.querySelectorAll('sup,sub').forEach(s => { const r = s.getBoundingClientRect();
        if (r.bottom > bar + 0.5) out.push([src, 'a power/index in the NUMERATOR crosses the fraction bar', s.textContent]); });
    });
    l.querySelectorAll('.bd-rb').forEach(rb => {
      const top = rb.getBoundingClientRect().top;
      rb.querySelectorAll('sup,sub').forEach(s => { if (s.getBoundingClientRect().top < top + 0.5)
        out.push([src, 'a power/index under a ROOT rises onto the overline', s.textContent]); });
    });
    // a power must sit in the UPPER half of its own line, an index in the lower half - never on the baseline like "32"
    // (glance 2026-09-12: a flex child ignores vertical-align)
    l.querySelectorAll('sup,sub').forEach(s => {
      const r = s.getBoundingClientRect(), pr = s.parentElement.getBoundingClientRect();
      const fs = parseFloat(getComputedStyle(s.parentElement).fontSize) || 16;
      if (!r.height || !pr.height) return;
      const raised = (pr.bottom - r.bottom) / fs;   // how far the script's bottom sits above the bottom of its parent's text line, in parent ems
      if (s.tagName === 'SUP' && raised < 0.25) out.push([src, 'a power sits on the baseline instead of raised', s.textContent]);
      if (s.tagName === 'SUB' && raised > 0.2) out.push([src, 'an index sits raised instead of lowered', s.textContent]);
    });
  });
  return out;
}
"""


def board_lines(c: dict) -> tuple[list[str], list[str]]:
    """(written lines, explanation maths): the lines the board writes in the hand, and the $maths$ segments of the explanations,
    which the real renderer puts as .bd-im inside a .bd-say panel (glance 2026-09-12 round 8: measure them in THAT context)."""
    lines: list[str] = []
    inline: list[str] = []
    for key in ("questions", "practice", "mistakes"):
        for x in c.get(key, []):
            for st in x.get("board") or []:
                if not isinstance(st, dict):
                    continue
                w = st.get("w")
                lines += [w] if isinstance(w, str) else list(w or [])
                for k in ("do", "why", "mind"):
                    inline += re.findall(r"\$([^$]+)\$", str(st.get(k, "")))
                a = st.get("ask")
                if isinstance(a, dict):
                    inline += re.findall(r"\$([^$]+)\$", str(a.get("q", "")))
                    for o in a.get("o") or []:
                        inline += re.findall(r"\$([^$]+)\$", str(o))
    return ([s for s in lines if isinstance(s, str) and s.strip()], [s for s in inline if isinstance(s, str) and s.strip()])


def harness(lines: list[str], extra_css: str = "", inline: list[str] | None = None) -> str:
    css = (TOOLS / "board.css").read_text(encoding="utf-8")
    js = (TOOLS / "board.js").read_text(encoding="utf-8")
    return (f'<meta charset="utf-8"><link rel="stylesheet" href="{FONTS}"><style>{css}{extra_css}</style>'
            '<div class="bd"><div class="bd-paper"><div class="bd-sheet"><div class="bd-lines" id="L"></div></div></div>'
            '<div class="bd-say" id="S"></div></div>'
            f"<script>{js}</script><script>const SRC={json.dumps(lines, ensure_ascii=False)};const INL={json.dumps(inline or [], ensure_ascii=False)};"
            "const L=document.getElementById('L');SRC.forEach(s=>{const words=/^~/.test(s),body=words?s.replace(/^~\\s?/,''):s;"
            "const el=document.createElement('div');el.className='bd-l'+(words?' bd-txt':'');el.dataset.src=s;"
            "el.innerHTML='<span class=\"bd-in\">'+Board.md(body,words)+'</span>';L.appendChild(el);});"
            "const S=document.getElementById('S');INL.forEach(s=>{const p=document.createElement('p');p.innerHTML='Kodėl: <span class=\"bd-im\" data-src=\"'+s.replace(/\"/g,'&quot;')+'\">'+Board.md(s)+'</span> – tekstas toliau.';S.appendChild(p);});</script>")


def measure(lines: list[str], extra_css: str = "", inline: list[str] | None = None, widths: tuple[int, ...] = (1000, 390)) -> list[list[str]]:
    """Problems found at every width (desktop and phone): the explanation panel wraps differently on a phone."""
    from playwright.sync_api import sync_playwright  # imported here so a PC without a browser fails loudly, once, in check()
    out: list[list[str]] = []
    seen: set[tuple[str, str, str]] = set()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        try:
            for w in widths:
                p = b.new_page(viewport={"width": w, "height": 700})
                p.set_content(harness(lines, extra_css, inline), wait_until="load")
                try:
                    p.evaluate("() => document.fonts.ready.then(() => 1)")
                except Exception:  # noqa: BLE001 - offline: the fallback font measures the same CSS rules
                    pass
                p.wait_for_timeout(150)
                for row in p.evaluate(MEASURE_JS):
                    key = tuple(row)
                    if key not in seen:
                        seen.add(key)
                        out.append(row + [f"{w}px"])
                p.close()
        finally:
            b.close()
    return out


def check(paths: list[Path]) -> list[str]:
    """Problems as text lines; a browser failure is one problem line (never a silent pass)."""
    lines: list[str] = []
    inline: list[str] = []
    for p in paths:
        try:
            a, b = board_lines(json.loads(p.read_text(encoding="utf-8")))
            lines += a
            inline += b
        except (OSError, ValueError) as e:
            return [f"BOARD LAYOUT NOT CHECKED: {p}: {e}"]
    lines, inline = sorted(set(lines)), sorted(set(inline))
    if not lines and not inline:
        return []
    try:
        found = measure(lines, inline=inline)
    except Exception as e:  # noqa: BLE001
        return [f"BOARD LAYOUT NOT CHECKED (no headless browser?): {type(e).__name__}: {e}"]
    return [f"board layout ({w}): {why} - '{txt}' in {src!r}" for src, why, txt, w in found]


def self_test() -> int:
    bad = [r"\f{1}{9} = \f{1}{3^2} = 3^-2", r"\f{1}{(√[3]{64})^2}", r"√{3^2}", r"\f{x^2}{4}", r"\f{a_1}{b^2}", "x⁻²·\\f{1}{3²}"]
    # exactly the pre-fix CSS: the generic ".bd-l sup" lift applied inside fractions too, and the denominator had no padding
    lift = ".bd-fr sup,.bd-rb sup{position:relative;top:-.62em;line-height:0;vertical-align:baseline}.bd-fr>.bd-de{padding-top:0}"
    # the glance's case: a power dropped to the baseline (what a flex child does with vertical-align) must be caught too
    flat = ".bd-fr sup,.bd-rb sup,.bd-rbi sup{position:static;top:auto;line-height:1;vertical-align:baseline}"
    broken = measure(bad, lift, inline=bad)
    flattened = measure(bad, flat, inline=bad)
    clean = measure(bad, inline=bad)
    print(f"self-test: with the 2026-09-12 lift {len(broken)} problem(s) found, with a baseline power {len(flattened)}, with the shipped CSS {len(clean)} (board lines + explanation panel, 1000 and 390 px)")
    if not broken or not flattened:
        print("FAIL: the check did not catch a known-bad layout - it proves nothing")
        return 1
    if clean:
        for src, why, txt, w in clean:
            print(f"  ({w}) {why} - '{txt}' in {src!r}")
        return 1
    print("ok")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--self-test":
        return self_test()
    paths = [Path(a) if Path(a).is_absolute() else ROOT / a for a in argv]
    problems = check(paths)
    if problems:
        print("\n".join(problems))
        return 1
    print("0 layout problems")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
