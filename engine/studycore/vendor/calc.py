"""calc.py - the scientific-calculator layer of the maths pages (owner 2026-09-12: "it must guide me what to press on
scientific calculator ... base all math learning around calculators"; question window the same day: "don't use a specific
calculator. a general one.").

A board step (tools/board.js) or a page's `calcCard` routine carries
    "calc": {"k": [<key tokens>], "d": "<what the display shows after =>", "n": "<short note, optional>"}
Tokens are the keys EVERY scientific calculator has (digits, brackets, the four operations, (−), x², x³, x⁻¹, xʸ, √, ∛, log,
ln, Abs, EXP, Ans). Strips are written in LINEAR form - brackets instead of a brand's template boxes - so the same sequence
is what a two-line calculator takes literally; on a natural-display calculator every box (xʸ, √, ∛, log) is left with ▶ before the
next key, and a fraction result shows as a fraction - `d` then reads "1/9 (arba 0.1111111111)". A logarithm with a base is typed as log(b) ÷ log(a), an
n-th root as x^(1÷n), a fraction as (a ÷ b) - universal routes, no brand keys.
`evaluate(tokens)` re-computes a sequence with ordinary calculator precedence (xʸ binds tighter than × ÷, a prefix function
applies to the next number or bracket, (−)2² = −4, two operands in a row multiply) and `check()` refuses a strip whose result
differs from `d` ("125", "0.0625", "-4", "5×10^-5", "Math ERROR"); a fraction display like "1/16" is accepted numerically.

Usage:  python tools/calc.py eval 6 2 5 pow ( 3 ÷ 4 ) =         -> 125
        python tools/calc.py check study/matematika/rugsejis.json   -> problems (empty = all key sequences verified)
        python tools/calc.py test                                -> self-tests
        python tools/calc.py keys                                -> the vocabulary with labels and hints
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---- vocabulary: token -> [label, shifted-label-or-None, hint]. Generic labels; the hint names the usual alternatives.
KEYMAP_GEN = {
    "family": "bet kuris mokslinis skaičiuotuvas be tekstinės atminties (universalūs klavišai, skliaustai vietoj langelių)",
    "keys": {
        "0": ["0"], "1": ["1"], "2": ["2"], "3": ["3"], "4": ["4"], "5": ["5"], "6": ["6"], "7": ["7"], "8": ["8"], "9": ["9"],
        ".": [".", None, "dešimtainis kablelis – klavišas . (arba ,)"],
        "+": ["+"], "-": ["−"], "×": ["×"], "÷": ["÷"], "(": ["("], ")": [")"], "=": ["="],
        "neg": ["(−)", None, "neigiamo skaičiaus klavišas: (−) arba +/−, ne atimties minusas"],
        "x2": ["x²"], "x3": ["x³", None, "jei tokio klavišo nėra: xʸ 3"], "inv": ["x⁻¹", None, "arba 1/x"],
        "pow": ["xʸ", None, "laipsnio klavišas: xʸ, ^ arba x■; trupmeninį ar neigiamą rodiklį rašyk skliaustuose"],
        "sqrt": ["√"], "cbrt": ["∛", None, "jei tokio klavišo nėra: xʸ ( 1 ÷ 3 )"],
        "log": ["log", None, "lg – dešimtainis logaritmas"], "ln": ["ln"],
        "abs": ["Abs", None, "modulis; jei klavišo nėra – suskaičiuok skliaustus ir numesk minusą"],
        "ans": ["Ans", None, "paskutinis rezultatas"], "E": ["EXP", None, "×10ⁿ: klavišas EXP, EE arba ×10■"],
        "pi": ["π"], "AC": ["AC"],
    },
}
KEYMAPS = {"gen": KEYMAP_GEN}
DEFAULT_FAMILY = "gen"
VOCAB = set(KEYMAP_GEN["keys"])
FUNCS = {"sqrt": "sqrt", "cbrt": "cbrt", "log": "log10", "ln": "ln", "abs": "abs"}
POSTFIX = {"x2": "**2", "x3": "**3", "inv": "**(-1)"}
DIGIT = re.compile(r"^[0-9.]$")
BRAND = re.compile(r"▶|▼|log■|SHIFT|ClassWiz|Casio|langel")


class CalcError(Exception):
    pass


class _Parser:
    """Recursive descent over one '='-terminated token segment, producing a python expression."""

    def __init__(self, toks: list[str]):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        v = self.peek()
        self.i += 1
        return v

    def starts_operand(self, tok) -> bool:
        return tok is not None and bool(DIGIT.match(tok) or tok in ("(", "neg", "ans", "pi") or tok in FUNCS)

    def expr(self) -> str:
        s = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            s += {"+": "+", "-": "-"}[op] + self.term()
        return s

    def term(self) -> str:
        s = self.unary()
        while True:
            p = self.peek()
            if p in ("×", "÷"):
                self.take()
                s += {"×": "*", "÷": "/"}[p] + self.unary()
            elif self.starts_operand(p) and p != "neg":
                s += "*" + self.unary()            # implicit multiplication: 3√5, 2(3+1)
            else:
                return s

    def unary(self) -> str:
        if self.peek() == "neg":
            self.take()
            return "(-" + self.unary() + ")"       # (−)2² = −4, like every calculator
        return self.power()

    def power(self) -> str:
        base = self.postfix()
        if self.peek() == "pow":
            self.take()
            if not self.starts_operand(self.peek()):
                raise CalcError("xʸ needs a number or bracket after it")
            return "(" + base + ")**(" + self.unary() + ")"
        if self.peek() == "E":
            self.take()
            if not self.starts_operand(self.peek()):
                raise CalcError("EXP needs an exponent after it")
            return "(" + base + ")*10**(" + self.unary() + ")"
        return base

    def postfix(self) -> str:
        s = self.primary()
        while self.peek() in POSTFIX:
            s = "(" + s + ")" + POSTFIX[self.take()]
        return s

    def primary(self) -> str:
        tok = self.take()
        if tok is None:
            raise CalcError("the sequence ends where a number was expected")
        if DIGIT.match(tok):
            num = tok
            while self.peek() is not None and DIGIT.match(self.peek()):
                num += self.take()
            if num.count(".") > 1 or num == ".":
                raise CalcError(f"not a number: {num}")
            return num if not num.startswith(".") else "0" + num
        if tok == "(":
            s = self.expr()
            if self.peek() == ")":
                self.take()
            return "(" + s + ")"                   # an unclosed bracket is closed by = on every calculator
        if tok in FUNCS:
            if self.peek() != "(":
                raise CalcError(f"{tok} must be followed by ( - on a natural-display calculator the root/log box would swallow what follows (reviewer 2026-09-12)")
            return FUNCS[tok] + self.primary()
        if tok == "ans":
            return "Ans"
        if tok == "pi":
            return "pi"
        raise CalcError(f"unexpected key {tok!r} where a number was expected")


def translate(tokens: list[str]) -> list[str]:
    """Token list -> python expressions, one per '=' (Ans carries the previous result)."""
    toks = [str(t) for t in tokens]
    bad = [t for t in toks if t not in VOCAB]
    if bad:
        raise CalcError(f"unknown key token(s) {bad}")
    toks = [t for t in toks if t != "AC"]
    if not toks or toks[-1] != "=":
        raise CalcError("the sequence must end with =")
    exprs, seg = [], []
    for t in toks:
        if t == "=":
            if not seg:
                raise CalcError("nothing to evaluate before =")
            p = _Parser(seg)
            e = p.expr()
            if p.i != len(seg):
                raise CalcError(f"keys left over after the expression: {' '.join(seg[p.i:])}")
            exprs.append(e)
            seg = []
        else:
            seg.append(t)
    return exprs


def _cbrt(a):
    return -((-a) ** (1.0 / 3)) if a < 0 else a ** (1.0 / 3)


def _log10(x):
    if x <= 0:
        raise ValueError
    return math.log10(x)


def _ln(x):
    if x <= 0:
        raise ValueError
    return math.log(x)


NS = {"sqrt": math.sqrt, "cbrt": _cbrt, "log10": _log10, "ln": _ln, "abs": abs, "pi": math.pi, "__builtins__": {}}


def evaluate(tokens: list[str]):
    """Return the final display value (float) or the string 'Math ERROR'."""
    ans = 0.0
    for expr in translate(tokens):
        try:
            v = eval(expr, dict(NS, Ans=ans))       # noqa: S307 - built by the parser above from the closed vocabulary only
            if isinstance(v, complex) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return "Math ERROR"
            ans = float(v)
        except (ValueError, ZeroDivisionError, OverflowError):
            return "Math ERROR"
        except SyntaxError as e:
            raise CalcError(f"sequence does not form an expression: {expr} ({e.msg})") from None
    return ans


def parse_display(d: str):
    """'125' | '0,5' | '−4' | '1/9' | '5×10^-5' | 'Math ERROR' -> float or the error string."""
    s = str(d).strip().split("(")[0].strip()          # "1/9 (arba 0.1111111111)": the natural-display form decides
    s = s.replace("−", "-").replace(",", ".").replace(" ", "")
    if s.upper().replace(".", "") in ("MATHERROR", "MATHERR", "ERROR"):
        return "Math ERROR"
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(?:/(-?\d+(?:\.\d+)?))?(?:[×x]10\^?\(?(-?\d+)\)?)?", s)
    if not m:
        raise CalcError(f"display {d!r} is not a number, a fraction a/b, a×10^n or Math ERROR")
    v = float(m.group(1))
    if m.group(2):
        v /= float(m.group(2))
    if m.group(3):
        v *= 10 ** int(m.group(3))
    return v


def check(calc, where: str = "") -> list[str]:
    """Problems with one calc strip: vocabulary, shape, and the recomputed result against `d`."""
    p = []
    if not isinstance(calc, dict) or not isinstance(calc.get("k"), list) or not calc["k"] or "d" not in calc:
        return [f"{where}calc must be {{\"k\": [keys...], \"d\": \"display\"}}"]
    bad = [str(t) for t in calc["k"] if str(t) not in VOCAB]
    if bad:
        return [f"{where}unknown key token(s) {bad} - vocabulary: {' '.join(sorted(VOCAB))}"]
    if len(calc["k"]) > 40:
        p.append(f"{where}{len(calc['k'])} keys - split the strip (max 40)")
    if calc.get("n") and len(str(calc["n"])) > 90:
        p.append(f"{where}note longer than 90 characters")
    if calc.get("n") and BRAND.search(str(calc["n"])):
        p.append(f"{where}note names a brand-specific key ({calc['n']!r}) - the strips are generic (owner 2026-09-12)")
    try:
        want = parse_display(calc["d"])
        got = evaluate([str(t) for t in calc["k"]])
    except CalcError as e:
        return p + [f"{where}{e}"]
    if isinstance(want, str) or isinstance(got, str):
        if want != got:
            p.append(f"{where}keys give {got!r} but d says {calc['d']!r}")
    elif not math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-9):
        p.append(f"{where}keys give {got:.10g} but d says {calc['d']!r}")
    return p


def check_content(c: dict) -> list[str]:
    p = []
    for kind in ("questions", "practice", "mistakes"):
        for i, item in enumerate(c.get(kind, [])):
            for j, st in enumerate(item.get("board") or []):
                if isinstance(st, dict) and st.get("calc") is not None:
                    p += check(st["calc"], f"{kind} {i} step {j}: ")
    for i, r in enumerate(c.get("calcCard", {}).get("items", [])):
        if not r.get("t"):
            p.append(f"calcCard {i}: needs `t` (what you are computing)")
        elif "^" in r["t"]:
            p.append(f"calcCard {i}: `t` is shown as HTML - write powers as <sup>…</sup>, not ^ (reviewer 2026-09-12)")
        p += check(r.get("calc"), f"calcCard {i}: ")
    return p


# ---- rendering (Python side: the calculator card; JS side gets the same KEYMAP through keymap_js) ----
def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def key_html(tok: str, family: str = DEFAULT_FAMILY) -> str:
    lab = KEYMAPS[family]["keys"][tok]
    base, shifted = lab[0], lab[1] if len(lab) > 1 else None
    hint = lab[2] if len(lab) > 2 and lab[2] else ""
    title = f' title="{esc(hint)}"' if hint else ""
    if shifted:
        return f'<kbd class="ck ck-s">SHIFT</kbd><kbd class="ck"{title}>{esc(base)}<i>{esc(shifted)}</i></kbd>'
    return f'<kbd class="ck"{title}>{esc(base)}</kbd>'


def strip_html(calc: dict, family: str = DEFAULT_FAMILY) -> str:
    keys = "".join(key_html(str(t), family) for t in calc["k"])
    note = f'<span class="cn">{esc(calc["n"])}</span>' if calc.get("n") else ""
    return f'<span class="ckeys" data-keys="{esc(" ".join(map(str, calc["k"])))}">{keys}</span><span class="cd">→ {esc(calc["d"])}</span>{note}'


def keymap_js(family: str = DEFAULT_FAMILY) -> str:
    return json.dumps(KEYMAPS[family], ensure_ascii=False, separators=(",", ":"))


def calc_seconds(calc: dict) -> float:
    """Reading a strip inside a board: 0.35 s a key + 1 s for the display. It REPLACES mental arithmetic, so it is costed as a
    glance, not as a full press-through (the calcCard drill units carry the real press-through time)."""
    return min(4.0, 1 + 0.2 * len(calc.get("k", [])))   # capped: the bracketed generic strips are longer but read no slower (2026-09-12)


def fmt_display(v) -> str:
    """A generic display string for a value: integers plain, others with up to 10 significant digits."""
    if isinstance(v, str):
        return v
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.10g}"


# ---- CLI ----
def _test():
    cases = [
        (["6", "2", "5", "pow", "(", "3", "÷", "4", ")", "="], 125),
        (["6", "4", "pow", "(", "neg", "2", "÷", "3", ")", "="], 1 / 16),
        (["log", "(", "1", "÷", "9", ")", "÷", "log", "(", "3", ")", "="], -2),
        (["log", "2", "0", "+", "log", "5", "="], None),
        (["log", "(", "2", "0", ")", "+", "log", "(", "5", ")", "="], 2),
        (["sqrt", "(", "2", ")", "×", "sqrt", "(", "8", ")", "="], 4),
        (["(", "8", "×", "2", "7", ")", "pow", "(", "1", "÷", "3", ")", "="], 6),
        (["cbrt", "(", "2", "7", "÷", "1", "2", "5", ")", "="], 0.6),
        (["0", ".", "2", "pow", "0", "-", "0", ".", "1", "pow", "(", "neg", "4", ")", "="], -9999),
        (["3", "sqrt", "(", "5", ")", "="], 3 * math.sqrt(5)),
        (["neg", "2", "x2", "="], -4),
        (["(", "neg", "2", ")", "x2", "="], 4),
        (["sqrt", "(", "neg", "4", ")", "="], "Math ERROR"),
        (["(", "neg", "1", "6", ")", "pow", "(", "1", "÷", "4", ")", "="], "Math ERROR"),
        (["2", "pow", "3", "+", "1", "="], 9),
        (["2", "pow", "(", "3", "+", "1", ")", "="], 16),
        (["8", "x3", "×", "4", "pow", "(", "neg", "2", ")", "="], 32),
        (["8", "x3", "×", "4", "inv", "x2", "="], 32),
        (["2", "x2", "=", "ans", "+", "1", "="], 5),
        (["(", "2", "÷", "3", ")", "+", "(", "1", "÷", "6", ")", "="], 5 / 6),
        (["abs", "(", "2", "×", "neg", "9", "+", "3", ")", "="], 15),
        (["5", "E", "neg", "5", "="], 5e-5),
        (["5", "1", "7", "2", "÷", "6", "="], 862),
        (["1", "x2", "+", "5", "×", "1", "-", "6", "="], 0),
        (["2", "pow", "3", "x2", "="], 512),       # x² applies to the 3 just typed, as on a real calculator: 2^(3²)
        (["(", "1", "÷", "3", ")", "inv", "="], 3),
        (["2", "pow", "="], None),
        (["sd", "2", "="], None),
        (["2", "+", "="], None),
    ]
    bad = 0
    for k, want in cases:
        try:
            got = evaluate(k)
        except CalcError as e:
            got = f"ERR {e}"
        ok = (want is None and str(got).startswith("ERR")) or (isinstance(want, str) and got == want) or \
             (isinstance(want, (int, float)) and not isinstance(got, str) and math.isclose(got, want, rel_tol=1e-9))
        print(("ok  " if ok else "FAIL"), " ".join(k), "->", got)
        bad += not ok
    for d, want in [("0,5", 0.5), ("−4", -4), ("1/9", 1 / 9), ("1/9 (arba 0.1111111111)", 1 / 9), ("5×10^-5", 5e-5), ("Math ERROR", "Math ERROR")]:
        got = parse_display(d)
        ok = got == want if isinstance(want, str) else math.isclose(got, want, rel_tol=1e-9)
        print(("ok  " if ok else "FAIL"), "display", d, "->", got)
        bad += not ok
    print("calc self-test:", "ALL PASSED" if not bad else f"{bad} FAILED")
    return bad


def main(argv):
    if not argv or argv[0] in ("-h", "help"):
        print(__doc__)
        return 0
    if argv[0] == "test":
        return 1 if _test() else 0
    if argv[0] == "eval":
        try:
            print(fmt_display(evaluate(argv[1:])))
        except CalcError as e:
            print("ERROR:", e)
            return 1
        return 0
    if argv[0] == "check":
        c = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        probs = check_content(c)
        n = sum(1 for kind in ("questions", "practice", "mistakes") for it in c.get(kind, [])
                for st in it.get("board") or [] if isinstance(st, dict) and st.get("calc")) + len(c.get("calcCard", {}).get("items", []))
        for x in probs:
            print("-", x)
        print(f"{n} calc strips, {len(probs)} problems")
        return 1 if probs else 0
    if argv[0] == "keys":
        for t, lab in KEYMAPS[DEFAULT_FAMILY]["keys"].items():
            print(f"{t:6} {' / '.join(x for x in lab[:2] if x)}  {lab[2] if len(lab) > 2 else ''}")
        return 0
    print("unknown command", argv[0])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
