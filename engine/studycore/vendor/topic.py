#!/usr/bin/env python
"""topic.py - build a topic study page from a CONTENT JSON, so a new topic costs thinking, not HTML.

WHY. The first topic page (biology, Virskinimas) was hand-written: 120 KB of markup, CSS and JS around
about 65 KB of actual content. Every subject needs many such pages (maths ~7 topics, Lithuanian ~5,
English ~6, biology ~15), and the owner asked for every subject, split into parts. So the shell - memory
palace, ranked questions, exam track, recall table, fact tiles, flashcards, quiz, mnemonics - lives once
in tools/topic.template.html and every page is a JSON of CONTENT rendered into it.

    python tools/topic.py build study/matematika/laipsniai.json     # -> study/matematika/laipsniai.html
    python tools/topic.py check study/matematika/laipsniai.json     # validate the contract, render nothing
    python tools/topic.py list                                      # every content JSON and what it holds

The page keeps the exact JS constant names tools/units.py reads (ROOMS, Q, S, C, T, VBE, O, SUBROOM) and
the exact #mnemonikos markup it scrapes, so `python tools/units.py extract <page>` keeps working unchanged.

CONTENT JSON (every section optional except title/rooms/questions):
{
  "topic": "mat-laipsniai",            # id used by the planner and by localStorage
  "subject": "matematika",             # study/<subject>/ folder
  "eyebrow": "Matematika 12 - B lygis - mokytoja I. Geciene",
  "title": "Laipsniai ir saknys",
  "lead": "one paragraph: what this page is for",
  "footer": "sources, verbatim, with the Moodle file names",
  "plan": [["Siandien - 20 min", "what to do"], ...],          # 4 cards; a default is generated
  "rooms": [{"place":"Virtuve","topic":"Laipsniu savybes","tags":"a^m*a^n","scene":"...",
             "hooks":[["terminas","juokingas zodis","ka reiskia"]]}],
  "questions": [{"p":92,"q":"...","t":"tema","a":"atsakymas (HTML)","st":["zingsnis"],"w":"kodel tiketina",
                 "m":{"r":[0],"h":["juokingas zodis"],"s":"pirmuju raidziu sakinys"}}],
  "figure": {"title":"...","intro":"...","svg":"<svg ...>...</svg>","legend":[["#B4524B","traktas"]],
             "info":{"key":{"n":"Vardas","f":"funkcija","k":["faktas"]}}},
  "table": {"title":"...","intro":"...","head":["Stulpelis"],"rows":[["pirmas","<b>langelis</b>"]]},
  "numbers": [["ka reiskia","reiksme"]],
  "cards": [["klausimas","atsakymas"]],
  "quiz": [{"s":"klausimas","o":["a","b"],"r":0,"e":"paaiskinimas"},
           {"s":"irasyk","t":["teisingas","variantas"],"e":"paaiskinimas","ph":"rasyk lietuviskai"}],
  "mnemonics": [["Pirmuju raidziu sakinys","ka jis koduoja"]],
  # MATHS (owner 2026-09-10): any question/practice item may carry "board": [steps] - the handwritten animated solution
  # (contract in tools/board.js; validated by board_problems), a practice item "rule": "taisykles vardas" (feeds the
  # 'Kuria taisykle taikysi?' drill in units.py), and the page may carry "mistakes": [{"t","s","board","bad","fix","e","tip"}].

  "lessons": {"title":"...","intro":"...","items":[                     # mokytojos vaizdo pamokos (kadrai perskaityti akimis)
      {"id":"yt-xxxx","src":"youtube|loom","url":"https://...","t":"6 pamoka - Laipsniai","min":44,
       "sum":"viena eilute - ka ta pamoka duoda","test":"ka is jos tiketina atsiskaityme (arba praleisk)",
       "gone":"irasas neveikia",                                        # tik jei irasas nepasiekiamas
       "beats":[["13:02","kas matoma ekrane - formule, pavyzdys, taisykle mokytojos zodziais"]]}]},
  "exam": {"title":"...","intro":"...","strip":[["Antraste","tekstas"]],"subroom":{"potema":0},
           "tasks":[{"year":2024,"session":"pagrindine","part":"II","number":"3 (2)","points":2,
                     "form":"struktūrinė","subtopic":"potema","question":"...","answer":"...","source":"..."}]}
}
"""
from __future__ import annotations

import json
import math
import re
import calc   # the scientific-calculator layer: key tokens, keymap, evaluator (owner 2026-09-12)
import sys
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "study"
TEMPLATE = Path(__file__).resolve().parent / "topic.template.html"

# room box geometry for the generated floor plan
BOX_W, BOX_H, GAP, MARGIN = 158, 112, 22, 20


LESSON_TOOLS = """  <div class="tools">
    <button class="btn" id="lOnly">Tik tai, kas tikėtina teste</button>
    <button class="btn" id="lOpen">Atverti visas</button>
    <button class="btn" id="lClose">Užverti visas</button>
  </div>
"""


def js(value) -> str:
    """JSON that is safe to paste inside a <script> block."""
    return json.dumps(value, ensure_ascii=False).replace("</script", "<\\/script").replace("<!--", "<\\!--")


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def palace_svg(rooms: list[dict]) -> str:
    """Serpentine floor plan: room 1 bottom-left, walking right, then up a row and back left."""
    n = len(rooms)
    cols = 2 if n <= 4 else 3
    rows = math.ceil(n / cols)
    w = MARGIN * 2 + cols * BOX_W + (cols - 1) * GAP
    h = MARGIN * 2 + rows * BOX_H + (rows - 1) * GAP
    pos = []
    for i in range(n):
        r, c = divmod(i, cols)
        if r % 2:                                   # walk back the other way on the next row up
            c = cols - 1 - c
        x = MARGIN + c * (BOX_W + GAP)
        y = h - MARGIN - (r + 1) * BOX_H - r * GAP  # first row sits at the bottom
        pos.append((x, y))
    route = " ".join(("M" if i == 0 else "L") + f"{x + BOX_W / 2:.0f} {y + BOX_H / 2:.0f}" for i, (x, y) in enumerate(pos))
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Buto planas - atminties kelias">',
           f'<path class="route" d="{route}"/>']
    for i, (r, (x, y)) in enumerate(zip(rooms, pos)):
        out.append(f'<g class="room" data-r="{i}" tabindex="0"><rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="10"/>'
                   f'<text class="rn" x="{x + 10}" y="{y + 28}">{esc(str(i + 1))} · {esc(r["place"])}</text>'
                   f'<text class="ro" x="{x + 10}" y="{y + 50}">{esc(r["topic"])}</text>'
                   + (f'<text class="ro" x="{x + 10}" y="{y + 68}">{esc(r.get("tags", ""))}</text>' if r.get("tags") else "")
                   + "</g>")
    out.append("</svg>")
    return "\n        ".join(out)


def section(sid: str, eyebrow: str, title: str, intro: str, body: str) -> str:
    intro_html = f'\n  <p class="intro">{intro}</p>' if intro else ""
    return f'<section id="{sid}">\n  <div class="eyebrow">{eyebrow}</div>\n  <h2>{title}</h2>{intro_html}\n{body}\n</section>\n'


SETTINGS = ROOT / "study" / "settings.json"


def settings() -> dict:
    """study/settings.json, resolved from the project root; a malformed file stops the build instead of silently defaulting."""
    if not SETTINGS.exists():
        return {}
    try:
        d = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"study/settings.json is not valid JSON ({e}) - fix it before building")
    if not isinstance(d, dict):
        raise SystemExit("study/settings.json must be a JSON object")
    return d


def association_on() -> bool:
    """Owner 2026-09-12: the memory palace, keyword hooks and first-letter sentences are switched off (study/settings.json).
    The flag must be a real boolean - a string like "false" would silently switch the techniques back on (reviewer 2026-09-12)."""
    v = settings().get("association", True)
    if not isinstance(v, bool):
        raise SystemExit(f"study/settings.json: association must be true or false, got {v!r}")
    return v


def build_sections(c: dict) -> tuple[str, str]:
    """Return (rail html, sections html) for whatever the content JSON actually carries."""
    rail, parts, n = [], [], 0

    def add(sid: str, label: str, html: str):
        nonlocal n
        rail.append(f'  <a href="#{sid}"><span class="n">{n}</span>{label}</a>')
        parts.append(html)
        n += 1

    if c.get("rooms") and association_on():
        body = ('  <div class="palace">\n    <div>\n      ' + palace_svg(c["rooms"]) +
                '\n      <div class="walkbar">\n'
                '        <button class="btn primary" id="walkNext">Kitas kambarys →</button>\n'
                '        <button class="btn" id="walkMode">Iš atminties</button>\n'
                '        <button class="btn" id="walkReset">Nuo pradžių</button>\n'
                '        <span class="pos" id="walkPos">1 / %d</span>\n'
                '      </div>\n    </div>\n    <div class="stop" id="stop"></div>\n  </div>' % len(c["rooms"]))
        add("rumai", "Atminties rūmai", section(
            "rumai", "Atminties rūmai + raktiniai žodžiai – tavo būdas įsiminti",
            c.get("palaceTitle", "Kelias per tavo butą"),
            c.get("palaceIntro", "Kiekviename kambaryje – vienas keistas vaizdas ir juokingi žodžiai-kabliukai, kurie skamba kaip terminai. "
                                 "Spausk kambarį arba „Kitas kambarys“. Režimas „Iš atminties“ paslepia sceną ir terminus – pirma prisimink, tada tikrinkis."),
            body))

    plan = c.get("plan") or [
        ["Šiandien · 20 min", "Perskaityk klausimus pagal tikimybę su atsakymais, kortelės vieną kartą."],
        ["Rytoj · 10 min", "Tik kortelės, pažymėtos „Nemoku“, ir lentelė prisiminimo režimu."],
        ["Po 3 dienų · 10 min", "Testas. Klaidingus klausimus pakartok kortelėse."],
        ["Po savaitės · 10 min", "Testas iki 100 %, plytelės paslėptos."]]
    add("planas", "Planas", section(
        "planas", "Kaip mokytis mažiausiai", c.get("planTitle", "Keturi trumpi užėjimai"),
        "Atmintis laikosi ne nuo skaitymo, o nuo prisiminimo su tarpais. Kiekvieną kartą pirmiausia bandyk atsakyti pats, tik tada žiūrėk.",
        '  <div class="plan">\n' + "\n".join(f'    <div><b>{b}</b><span>{s}</span></div>' for b, s in plan) + "\n  </div>"))

    if c.get("questions"):
        add("klausimai", "Klausimai", section(
            "klausimai", "Labiausiai tikėtini klausimai", "Klausimai pagal tikimybę",
            c.get("questionsIntro", "Tikimybė – mano įvertis iš mokytojos įkeltos medžiagos ir tipinių šio dalyko atsiskaitymų; ne mokytojos statistika. "
                                    "Spausk klausimą – pamatysi atsakymą tokį, kokį reikia parašyti."),
            '  <div class="tools">\n    <button class="btn" id="sortP">Rikiuoti pagal tikimybę</button>\n'
            '    <button class="btn" id="sortT">Rikiuoti pagal temą</button>\n'
            '    <button class="btn" id="openAll">Atverti visus</button>\n'
            '    <button class="btn" id="closeAll">Užverti visus</button>\n  </div>\n  <div class="qlist" id="qlist"></div>'))

    if c.get("practice"):
        add("pratybos", c.get("practiceRail", "Spręsk pats"), section(
            "pratybos", "Mokaisi darydamas, ne skaitydamas", c.get("practiceTitle", "Spręsk pats"),
            c.get("practiceIntro", "Viena užduotis vienu metu, dažniau grįžta tos, kurių dar nemoki. Pirma spręsk ant lapo, tik tada žiūrėk sprendimą."),
            '  <div class="tools"><button class="btn" id="pNext">Kita užduotis</button></div>\n  <div class="train" id="practice"></div>'))

    if c.get("calcCard", {}).get("items"):
        cc = c["calcCard"]
        rows = "\n".join(
            f'    <div class="cr"><button class="crq" type="button" aria-expanded="false"><span>{it["t"]}</span><span class="hint">Rodyti klavišus</span></button>'
            f'<div class="cra" hidden><div class="bd-calc" data-calc="1" role="button" tabindex="0" title="Bakstelėk: klavišai užsidegs iš eilės"><b>🔢 Skaičiuotuve.</b> {calc.strip_html(it["calc"])}</div></div></div>'
            for it in cc["items"])
        fam = calc.KEYMAPS[calc.DEFAULT_FAMILY]["family"]
        add("skaiciuotuvas", cc.get("rail", "Skaičiuotuvas"), section(
            "skaiciuotuvas", cc.get("eyebrow", "Skaičiuotuvas daro aritmetiką – tu darai tik tai, ko jis negali"),
            cc.get("title", "Skaičiuotuvo kortelė"),
            cc.get("intro", f"Tinka {fam}: laipsnis – xʸ (arba ^, x■), šaknis – √, logaritmas su pagrindu – log(b) ÷ log(a), "
                            "trupmena – skliaustuose (a ÷ b). Kiekviena eilutė – viena užduotis: pirma gauk atsakymą pats, tada spausk "
                            "„Rodyti klavišus“ ir palygink. Bakstelėk juostą – klavišai užsidegs ta tvarka, kuria spaudi. "
                            "Dvieilis skaičiuotuvas ima seką pažodžiui. Natūralaus ekrano skaičiuotuve (pvz., Casio ClassWiz) iš KIEKVIENO "
                            "langelio (xʸ, √, log) išeik klavišu ▶ prieš spausdamas toliau, o trupmeninį rezultatą jis rodo kaip trupmeną – "
                            "todėl prie tokių atsakymų parašyta ir trupmena, ir dešimtainė (perjungimo klavišas S⇔D)."),
            '  <style>.cr{border:1px solid var(--line,#d5ddd6);border-radius:10px;margin:8px 0;overflow:hidden}'
            '.crq{width:100%;display:flex;justify-content:space-between;gap:8px;align-items:center;text-align:left;background:none;border:0;padding:10px 12px;font:inherit;color:inherit;cursor:pointer;min-height:44px}'
            '.crq .hint{font-size:.85rem;opacity:.7;white-space:nowrap}.cra{padding:0 12px 10px}</style>\n'
            f'  <div class="ccard">\n{rows}\n  </div>\n'
            '  <script>document.querySelectorAll(".crq").forEach(b=>b.onclick=()=>{const a=b.nextElementSibling,o=a.hidden;a.hidden=!o;b.setAttribute("aria-expanded",String(o));if(o&&window.Board)Board.wireCalc(a);});</script>'))

    if c.get("exam", {}).get("tasks"):
        e = c["exam"]
        strip = "\n".join(f'    <div><b>{b}</b><span>{s}</span></div>' for b, s in e.get("strip", []))
        add("vbe", "VBE užduotys", section(
            "vbe", "Egzamino kelias – tik tikri duomenys", e.get("title", "VBE: realios užduotys"), e.get("intro", ""),
            (f'  <div class="vbestrip">\n{strip}\n  </div>\n' if strip else "") +
            '  <h3 style="margin-top:6px">Kur susikaupę taškai</h3>\n'
            '  <p class="intro" style="margin-top:.2rem">Ne spėjimas, o suma: kiek taškų kiekviena potemė realiai davė per praėjusius egzaminus.</p>\n'
            '  <div class="rank" id="vbeRank"></div>\n'
            '  <h3 style="margin-top:26px">Visos užduotys</h3>\n'
            '  <p class="intro" style="margin-top:.2rem">Filtruok ir spausk „Rodyti atsakymą“. Mokykis TOKIA formuluote, kokia yra vertinimo instrukcijoje.</p>\n'
            '  <div class="vfilters">\n    <select id="fYear" aria-label="Metai"></select>\n    <select id="fForm" aria-label="Užduoties forma"></select>\n'
            '    <select id="fSub" aria-label="Potemė"></select>\n    <button class="btn" id="fClear">Išvalyti</button>\n    <span class="vcount" id="vCount"></span>\n  </div>\n'
            '  <div class="vlist" id="vList"></div>\n'
            '  <h3 style="margin-top:30px">Egzamino treniruotė</h3>\n'
            '  <p class="intro" style="margin-top:.2rem">Penkios atsitiktinės užduotys, dažniau iškrenta brangesnės. Atsakyk mintyse arba ant lapo, tada tikrinkis.</p>\n'
            '  <div class="tools"><button class="btn primary" id="vTrainStart">Pradėti treniruotę (5 užduotys)</button></div>\n'
            '  <div class="train" id="vTrain" hidden></div>'))

    if c.get("figure", {}).get("svg"):
        f = c["figure"]
        legend = "".join(f'<span><i style="background:{col}"></i>{lab}</span>' for col, lab in f.get("legend", []))
        add("schema", f.get("rail", "Schema"), section(
            "schema", "Dual coding – paveikslas prie kiekvienos taisyklės", f.get("title", "Schema"), f.get("intro", ""),
            '  <div class="map">\n    <div>\n      ' + f["svg"] +
            (f'\n      <div class="legend">{legend}</div>' if legend else "") +
            '\n    </div>\n    <div class="infobox" id="info">\n      <h3>' + f.get("hint", "Spausk elementą") + '</h3>\n      <p class="fn">' +
            f.get("hintBody", "") + '</p>\n    </div>\n  </div>'))

    if c.get("table", {}).get("rows"):
        t = c["table"]
        head = "".join(f"<th>{h}</th>" for h in t["head"])
        rows = ""
        # glance 2026-09-12: each cell carries its column label, so a phone can stack a row (label above value) instead of scrolling
        labels = [re.sub(r"<[^>]+>", "", h) for h in t["head"]]
        for row in t["rows"]:
            cells = f'<td data-h="{esc(labels[0])}">{row[0]}</td>' + "".join(
                f'<td class="cell" data-h="{esc(labels[j]) if j < len(labels) else ""}"><span>{x}</span></td>' for j, x in enumerate(row[1:], 1))
            rows += f"      <tr>{cells}</tr>\n"
        add("lentele", t.get("rail", "Lentelė"), section(
            "lentele", t.get("eyebrow", "Lentelė, kurios klausia dažniausiai"), t.get("title", "Lentelė"),
            t.get("intro", "Įjunk prisiminimo režimą – langeliai pasislepia, spausk, kai atsakei mintyse."),
            '  <div class="tools"><button class="btn primary" id="recallBtn">Prisiminimo režimas</button>'
            '<button class="btn" id="hideAgain">Paslėpti vėl</button></div>\n'
            f'  <div class="tblwrap"><table id="tbl">\n    <thead><tr>{head}</tr></thead>\n    <tbody>\n{rows}    </tbody>\n  </table></div>'))

    if c.get("numbers"):
        add("skaiciai", "Skaičiai", section(
            "skaiciai", "Skaičiai ir faktai, kurių klausia", c.get("numbersTitle", "Skaičių plytelės"),
            "Spausk plytelę – reikšmė pasislepia arba pasirodo. Mokykis paslėptas.",
            '  <div class="tools"><button class="btn" id="hideStats">Paslėpti visas</button><button class="btn" id="showStats">Rodyti visas</button></div>\n'
            '  <div class="stats" id="stats"></div>'))

    if c.get("cards"):
        add("korteles", "Kortelės", section(
            "korteles", "Aktyvus prisiminimas su tarpais", "Kortelės",
            "Atsakyk garsiai arba mintyse, apversk, tada sąžiningai spausk „Moku“ arba „Nemoku“. Progresas išsaugomas šioje naršyklėje.",
            '  <div class="deck">\n    <div>\n'
            '      <button class="card" id="card"><span class="side" id="cside">Klausimas</span><span class="front" id="cfront"></span>'
            '<span class="back" id="cback"></span><span class="tip">Spausk arba <kbd>tarpas</kbd> – apversti</span></button>\n'
            '      <div class="judge"><button class="btn no" id="no">Nemoku <kbd>1</kbd></button><button class="btn yes" id="yes">Moku <kbd>2</kbd></button></div>\n'
            '    </div>\n    <div class="deckside">\n      <b id="due">0</b>kortelių laukia dabar\n'
            '      <div class="row"><span>Iš viso</span><span id="total">0</span></div>\n'
            '      <div class="row"><span>Išmokta (3+ kartus)</span><span id="learned">0</span></div>\n'
            '      <div class="row"><span>Kitos grįš</span><span id="next">–</span></div>\n'
            '      <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap"><button class="btn" id="resetDeck">Pradėti iš naujo</button>'
            '<button class="btn" id="allDue">Kartoti visas</button></div>\n    </div>\n  </div>'))

    if c.get("quiz"):
        add("testas", "Testas", section(
            "testas", "Patikrink save kaip atsiskaityme", "Testas",
            c.get("quizIntro", "Iš karto matai, ar teisingai. Rašomuose atsakymuose rašyk taip, kaip rašytum lape."),
            '  <div class="score" id="score"><span>Atsakyta 0 iš 0</span><button class="btn" id="retry">Kartoti klaidas</button></div>\n'
            '  <div class="quiz" id="quiz" style="margin-top:12px"></div>'))

    if c.get("lessons", {}).get("items"):
        ls = c["lessons"]
        add("pamokos", ls.get("rail", "Vaizdo pamokos"), section(
            "pamokos", ls.get("eyebrow", "Mokytojos vaizdo pamokos – perskaitytos už tave"),
            ls.get("title", "Ką mokytoja iš tikrųjų rodė per pamokas"),
            ls.get("intro", "Vaizdo pamokose nėra subtitrų, todėl iš kiekvienos paimtos skaidrės ir perskaitytos akimis. "
                            "Žiūrėti jų nereikia: čia surašyta, ką mokytoja rodė ir ką iš to verta mokytis. "
                            "Nori pamatyti pats – spausk laiką, įrašas atsidarys ties ta minute."),
            LESSON_TOOLS +
            '  <div class="lsn" id="lessons"></div>'))

    if c.get("mistakes"):
        add("klaidos", "Rask klaidą", section(
            "klaidos", "Klaidų medžioklė – svetima klaida apsaugo nuo savos", c.get("mistakesTitle", "Rask klaidą"),
            c.get("mistakesIntro", "Kiekviename sprendime vienas žingsnis neteisingas – tokia klaida, kokią mokiniai daro dažniausiai. "
                                   "Spausk eilutę, kurioje suklysta: raudonas rašiklis parodys, kaip turėjo būti ir kaip neapsigauti."),
            '  <div class="mistakes" id="mistakes"></div>'))

    mn = [m for m in c.get("mnemonics", []) if association_on() or (len(m) < 3 or m[2] != "first-letter")]
    if mn:   # a 3rd element "first-letter" marks an acrostic sentence - dropped with the association techniques (owner 2026-09-12)
        cards = "\n".join(f"    <div><b>{m[0]}</b><span>{m[1]}</span></div>" for m in mn)
        add("mnemonikos", "Atmintinės", section(
            "mnemonikos", "Kabliukai atminčiai", "Atmintinės ir vieno sakinio paaiškinimai", "",
            f'  <div class="mn">\n{cards}\n  </div>'))

    return "\n".join(rail), "\n".join(parts)


def build(path: Path) -> Path:
    c = json.loads(path.read_text(encoding="utf-8"))
    problems = check_content(c) + layout_problems(c, path)
    if problems:
        raise SystemExit("content problems:\n  " + "\n  ".join(problems))
    rooms = [{"n": f'{i + 1} · {r["place"]} = {r["topic"]}', "scene": r.get("scene", ""), "hooks": r.get("hooks", [])}
             for i, r in enumerate(c.get("rooms", []))]
    questions = c.get("questions", [])
    if not association_on():
        rooms = []                                                     # no palace, no room chips anywhere on the page
        questions = [{k: v for k, v in q.items() if k != "m"} for q in questions]   # no "Kaip įsiminti" block under a question
    rail, sections = build_sections(c)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    exam = c.get("exam", {})
    html = (tpl.replace("{{TITLE}}", esc(c["title"]))
               .replace("{{EYEBROW}}", c.get("eyebrow", ""))
               .replace("{{LEAD}}", c.get("lead", ""))
               .replace("{{RAIL}}", rail)
               .replace("{{SECTIONS}}", sections)
               .replace("{{FOOTER}}", c.get("footer", ""))
               .replace("{{ROOMS}}", js(rooms))
               .replace("{{Q}}", js(questions))
               .replace("{{S}}", js(c.get("numbers", [])))
               .replace("{{C}}", js(c.get("cards", [])))
               .replace("{{T}}", js(c.get("quiz", [])))
               .replace("{{VBE}}", js(exam.get("tasks", [])))
               .replace("{{O}}", js(c.get("figure", {}).get("info", {})))
               .replace("{{P}}", js(c.get("practice", [])))
               .replace("{{L}}", js(c.get("lessons", {}).get("items", [])))
               .replace("{{SUBROOM}}", js(exam.get("subroom", {})))
               .replace("{{M}}", js(c.get("mistakes", [])))
               .replace("{{KEY}}", js(c["topic"] + "-leitner")))
    html = inline_board(html)
    if c.get("lang") == "en":
        html = english_chrome(html)
    dest = path.with_suffix(".html")
    dest.write_text(html, encoding="utf-8")
    counts = {k: len(c.get(k, [])) for k in ("rooms", "questions", "numbers", "cards", "quiz", "mnemonics")}
    counts["practice"] = len(c.get("practice", []))
    counts["hooks"] = sum(len(r.get("hooks", [])) for r in c.get("rooms", []))
    counts["exam"] = len(exam.get("tasks", []))
    counts["lessons"] = len(c.get("lessons", {}).get("items", []))
    counts["boards"] = sum(1 for k in ("questions", "practice") for x in c.get(k, []) if x.get("board"))
    counts["mistakes"] = len(c.get("mistakes", []))
    print(f"{dest.relative_to(ROOT)}: {len(html)//1024} KB · " + " · ".join(f"{k} {v}" for k, v in counts.items() if v))
    return dest


BOARD_CSS = Path(__file__).resolve().parent / "board.css"
BOARD_JS = Path(__file__).resolve().parent / "board.js"
MARK_TYPES = {"o", "x", "u", "b"}


def inline_board(html: str) -> str:
    """Paste the shared handwritten maths board (tools/board.css + tools/board.js) into a page that has the slots."""
    html = html.replace("/*__BOARD_CSS__*/", BOARD_CSS.read_text(encoding="utf-8"))
    js = BOARD_JS.read_text(encoding="utf-8").replace("/*__KEYMAP__*/null", calc.keymap_js()).replace("</script", "<\\/script")
    return html.replace("/*__BOARD_JS__*/", js)


# English lessons in English (owner 2026-09-12: "i want all english lessons to be in english"): a content JSON with
# "lang": "en" carries English content, and every fixed Lithuanian chrome string of the shell is swapped here. Longest first.
EN_CHROME = [
    ("Atsakyk garsiai arba mintyse, apversk, tada sąžiningai spausk „Moku“ arba „Nemoku“. Progresas išsaugomas šioje naršyklėje.",
     "Say the answer aloud or in your head, flip, then honestly press “I know” or “Not yet”. Progress is saved in this browser."),
    ("Atmintis laikosi ne nuo skaitymo, o nuo prisiminimo su tarpais. Kiekvieną kartą pirmiausia bandyk atsakyti pats, tik tada žiūrėk.",
     "Memory is built by recalling with gaps between sessions, not by reading. Always try to answer first, only then look."),
    ("Spausk kambarį arba „Kitas kambarys“. Režimas „Iš atminties“ paslepia sceną ir terminus – pirma prisimink, tada tikrinkis.",
     "Press a room or “Next room”. “From memory” hides the scene and the terms – recall first, then check."),
    ("Spausk kortelę – pamatysi, ką kabliukas reiškia. Užsimerk ir pamatyk vaizdą 3 sekundes.", "Press a card to see what the hook means. Close your eyes and picture the image for 3 seconds."),
    ("Juokingas žodis rodomas – prisimink terminą, tada spausk kortelę.", "The funny word is shown – recall the term, then press the card."),
    ("Spausk plytelę – reikšmė pasislepia arba pasirodo. Mokykis paslėptas.", "Press a tile – the value hides or shows. Learn with them hidden."),
    ("Įjunk prisiminimo režimą – langeliai pasislepia, spausk, kai atsakei mintyse.", "Turn on recall mode – the cells hide; press one once you have answered in your head."),
    ("Šiandien viskas pakartota. Grįžk, kai kortelės vėl lauks.", "Everything is reviewed for today. Come back when cards are due again."),
    ("Nemokėtas potemes pasižymėk ir pakartok jų korteles.", "Note the subtopics you missed and review their cards."),
    ("Kas čia vyksta? Pirma prisimink, tada spausk „Rodyti“", "What happens here? Recall first, then press “Show”"),
    ("Atminties rūmai + raktiniai žodžiai – tavo būdas įsiminti", "Memory palace + keyword hooks – your way to remember"),
    ("Atmintinės ir vieno sakinio paaiškinimai", "Mnemonics and one-sentence explanations"),
    ("Iš karto matai, ar teisingai. Rašomuose atsakymuose rašyk taip, kaip rašytum lape.", "Instant feedback. In written answers write exactly as you would on paper."),
    ("Rašomuose atsakymuose rašyk taip, kaip rašytum lape.", "In written answers write exactly as you would on paper."),
    ("Santrauka – atsakymas žodžiais", "Summary – the answer in words"),
    ("Patikrink save kaip atsiskaityme", "Test yourself as in the assessment"),
    ("Mokaisi darydamas, ne skaitydamas", "You learn by doing, not by reading"),
    ("Labiausiai tikėtini klausimai", "Most likely questions"), ("Klausimai pagal tikimybę", "Questions by probability"),
    ("Skaičiai ir faktai, kurių klausia", "Numbers and facts they ask"), ("Aktyvus prisiminimas su tarpais", "Active recall with spacing"),
    ("Visos mokamos. Grįžk po 3 dienų.", "All known. Come back in 3 days."),
    ("Rikiuoti pagal tikimybę", "Sort by probability"), ("Rikiuoti pagal temą", "Sort by topic"),
    ("Kaip mokytis mažiausiai", "How to study the least"), ("Keturi trumpi užėjimai", "Four short visits"),
    ("Kelias per tavo butą", "A walk through your flat"), ("Kabliukai atminčiai", "Hooks for memory"),
    ("Rodyti visas pamokas", "Show all lessons"), ("Šios pamokos įrašo nebėra – ką ji dėstė, paimta iš mokytojos failų.", "The recording of this lesson is gone – its content was taken from the teacher files."), ("Neteisingai. ", "Wrong. "),
    ("Visi metai", "All years"), ("Visos potemės", "All subtopics"), ("Visos formos", "All forms"), ("Su tokiais filtrais užduočių nėra.", "No tasks match these filters."),
    ("Atsakymas", "Answer"), ("užd.", "tasks"),
    ("Prisiminimo režimas", "Recall mode"), ("Rodyti sprendimą", "Show solution"), ("Rodyti atsakymą", "Show answer"),
    ("Slėpti atsakymą", "Hide answer"), ("Rodyti viską", "Show all"), ("Rodyti sceną", "Show scene"),
    ("Kitas kambarys →", "Next room →"), ("Pradėti iš naujo", "Start again"), ("Iš atminties", "From memory"), ("Nuo pradžių", "From the start"),
    ("Atminties rūmai", "Memory palace"), ("Atverti visus", "Open all"), ("Užverti visus", "Close all"),
    ("Kita užduotis", "Next task"), ("Spręsk pats", "Do it yourself"), ("Paslėpti visas", "Hide all"), ("Rodyti visas", "Show all"),
    ("Paslėpti vėl", "Hide again"), ("Kartoti klaidas", "Retry mistakes"), ("Kartoti visas", "Review all"), ("Tik laukiančias", "Only due"),
    ("Kaip įsiminti:", "How to remember:"), ("Kodėl tikėtina: ", "Why likely: "), (" · ✍️ sprendimas ranka", " · ✍️ worked by hand"),
    ("kortelių laukia dabar", "cards due now"), ("Išmokta (3+ kartus)", "Learned (3+ times)"), ("Kitos grįš", "Next due"), ("Iš viso", "Total"),
    ("Spausk arba <kbd>tarpas</kbd> – apversti", "Press or <kbd>space</kbd> – flip"), ("Nemoku <kbd>1</kbd>", "Not yet <kbd>1</kbd>"), ("Moku <kbd>2</kbd>", "I know <kbd>2</kbd>"),
    ("rašyk lietuviškai", "type your answer"), ("Neteisingai – teisinga: ", "Wrong – correct: "), ("Teisingai. ", "Correct. "), ("Tikrinti", "Check"),
    ("Atsakyta 0 iš 0", "Answered 0 of 0"), ("Atsakyta ${n} iš ${T.length} · teisingai ${ok}", "Answered ${n} of ${T.length} · correct ${ok}"),
    ("Užduotis ${pDone+1} · šioje temoje ${P.length} užduotys · išspręsta iš pirmo karto ${pOk}", "Task ${pDone+1} · ${P.length} tasks in this topic · solved first time ${pOk}"),
    (" · šią mokei ", " · you knew this "), ("} k.`", "} times`"), ("Kas iš čia tikėtina atsiskaityme:", "What here is likely in the assessment:"),
    ("Teste tikėtina", "Likely in the test"), ("Tik tai, kas tikėtina teste", "Only what is likely in the test"), ("Šaltinis:", "Source:"), ("Nemokėjau", "Didn’t know"), ("Mokėjau", "Knew it"), ("Užuomina", "Hint"),
    ("Rezultatas: ", "Result: "), ("Dar kartą", "Again"), ("Klausimai", "Questions"), ("Klausimas", "Question"), ("Kortelės", "Cards"), ("Kortelė", "Card"),
    ("Atmintinės", "Mnemonics"), ("Skaičiai", "Numbers"), ("Testas", "Test"), ("Planas", "Plan"), ("Baigta", "Done"), ("Terminas", "Term"), ("Kas tai?", "What is it?"),
]


def english_chrome(html: str) -> str:
    for lt, en in EN_CHROME:
        html = html.replace(lt, en)
    html = re.sub("„([^„“]*)“", r"“\1”", html)      # Lithuanian „quotes“ become English “quotes” on an English page
    if "\x01" in html:
        raise SystemExit("english_chrome produced a U+0001 - a backreference was written as a control character (reviewer 2026-09-12)")
    return html


def line_problems(src: str) -> list[str]:
    """Walk a board line the way board.js md() reads it and report what would render wrongly."""
    p: list[str] = []
    i = 0

    def arg(script: bool = False):
        nonlocal i
        if i < len(src) and src[i] == "{":
            i += 1
            if not seq("}"):
                p.append(f"a {{ never closes in {src!r}")
            return
        if i < len(src) and src[i] == "(" and not script:
            depth = 0
            for j in range(i, len(src)):
                depth += {"(": 1, ")": -1}.get(src[j], 0)
                if depth == 0:
                    i = j + 1
                    return
            p.append(f"a ( never closes in {src!r}")
            i = len(src)
            return
        m = re.match(r"[-−]?(?:\d+(?:,\d+)?|[A-Za-zα-ωπ])", src[i:])
        i += m.end() if m else 1

    def seq(stop: str | None) -> bool:
        nonlocal i
        while i < len(src):
            ch = src[i]
            if stop and ch == stop:
                i += 1
                return True
            if src.startswith("\\f{", i):
                i += 2
                arg()
                arg()
                continue
            if src.startswith("\\r{", i) or src.startswith("\\r[", i) or ch == "√":
                i += 1 if ch == "√" else 2
                if i < len(src) and src[i] == "[":
                    i += 1
                    if not seq("]"):
                        p.append(f"a root index [ never closes in {src!r}")
                arg()
                continue
            if ch in "^_" and i + 1 < len(src):
                if src[i + 1] == "(" and ch == "^":
                    p.append(f"`^(` raises only the bracket - write ^{{...}} in {src!r}")
                i += 1
                arg(True)
                continue
            m = re.match(r"\[#[\w-]+ ?", src[i:]) if ch == "[" else None
            if m:
                i += m.end()
                start = i
                if not seq("]"):
                    p.append(f"a labelled part [#... never closes in {src!r}")
                body = src[start:i - 1]
                if body.count("(") != body.count(")"):
                    p.append(f"an interval bracket ] ends the labelled part early - keep [ ] intervals outside [#...] in {src!r}")
                continue
            i += 1
        return stop is None

    seq(None)
    return p


def board_problems(steps, explained: bool = True) -> list[str]:
    """The contract of a handwritten board (tools/board.js header). `explained` boards teach, so every step says what it does."""
    if not isinstance(steps, list) or not steps:
        return ["a board must be a non-empty list of steps"]
    p: list[str] = []
    ids: set[str] = set()
    last: list[str] = []
    for j, st in enumerate(steps):
        if not isinstance(st, dict):
            p.append(f"step {j}: must be an object")
            continue
        w = st.get("w")
        lines = [] if w is None else ([w] if isinstance(w, str) else w)
        if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
            p.append(f"step {j}: `w` must be a string or a list of strings")
            continue
        for src in lines:
            p += [f"step {j}: {x}" for x in line_problems(src)]
            ids |= set(re.findall(r"\[#([\w-]+)", src))
        if st.get("svg") is not None and not str(st["svg"]).lstrip().startswith("<svg"):
            p.append(f"step {j}: `svg` must be an inline <svg> figure")
        last = lines or last
        for m in st.get("marks") or []:
            if not isinstance(m, list) or len(m) < 2 or m[0] not in MARK_TYPES:
                p.append(f"step {j}: a mark is [\"o|x|u|b\", \"id\", \"note?\", \"g?\"], got {m!r}")
            elif m[1] not in ids:
                p.append(f"step {j}: mark id \"{m[1]}\" is not a [#{m[1]} ...] part of this or an earlier step")
            elif len(m) > 2 and m[2] and len(str(m[2])) > 16:
                p.append(f"step {j}: mark note \"{m[2]}\" is longer than 16 characters")
        if explained and not st.get("do"):
            p.append(f"step {j}: no `do` (Ką darau)")
        # owner 2026-09-12: "every other step must be explained too, so i don't go to look for more answers somewhere else" - a
        # step's Kodėl names the rule and answers the question a student would ask there (why negative, why divide, why flip)
        if explained and len(re.sub(r"\s+", " ", str(st.get("why") or "")).strip()) < 40:
            p.append(f"step {j}: `why` (Kodėl) missing or thinner than 40 characters - every step is explained in full (owner 2026-09-12)")
        for k in ("do", "why", "mind"):
            if str(st.get(k, "")).count("$") % 2:
                p.append(f"step {j}: `{k}` has an odd number of $ - inline maths is $...$")
            if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", str(st.get(k, ""))):
                p.append(f"step {j}: `{k}` contains a control character - a JSON \"\\f{{\" decodes to form-feed; write \"\\\\f{{\" (glance 2026-09-12)")
        if st.get("calc") is not None:
            p += calc.check(st["calc"], f"step {j}: ")   # the key sequence is re-computed; a wrong strip never reaches the page
        a = st.get("ask")
        if a is not None:
            o = a.get("o") if isinstance(a, dict) else None
            r = a.get("r") if isinstance(a, dict) else None
            if not isinstance(o, list) or not 2 <= len(o) <= 4 or isinstance(r, bool) or not isinstance(r, int) or not 0 <= r < len(o):
                p.append(f"step {j}: `ask` needs 2-4 options `o` and a valid index `r`")
    if explained and not any(re.match(r"\s*(?:~\s?)?Ats\.", x) for x in last):
        p.append("the last written step has no `Ats.:` line")
    return p


def layout_problems(c: dict, path: Path) -> list[str]:
    """Owner 2026-09-12 ("1/3²" drew the 2 on the fraction bar: "make sure that never happens anywhere again"): every board line
    is rendered headlessly by tools/boardcheck.py and a power that climbs onto a fraction bar or a root's overline refuses the
    build. No browser = a named problem, never a silent pass."""
    if not any(x.get("board") for k in ("questions", "practice", "mistakes") for x in c.get(k, [])):
        return []
    import boardcheck
    return boardcheck.check([path])


def check_content(c: dict) -> list[str]:
    p = []
    for i, q in enumerate(c.get("questions", [])):
        if q.get("board") is not None:
            p += [f"question {i} board: {x}" for x in board_problems(q["board"])]
    for i, x in enumerate(c.get("practice", [])):
        if x.get("board") is not None:
            p += [f"practice {i} board: {y}" for y in board_problems(x["board"])]
        if x.get("rule") is not None and (not isinstance(x["rule"], str) or not 3 <= len(x["rule"]) <= 60):
            p.append(f"practice {i}: `rule` must be a 3-60 character rule name")
        near = x.get("near")
        if near is not None:
            rules = {y.get("rule") for y in c.get("practice", []) if y.get("rule")}
            if not isinstance(near, list) or len(near) != 3 or x.get("rule") in near or any(n not in rules for n in near):
                p.append(f"practice {i}: `near` must be 3 OTHER practice tasks' exact `rule` strings (look-alikes this task does not use)")
    for i, m in enumerate(c.get("mistakes", [])):
        if not m.get("s") or not m.get("e") or not m.get("fix"):
            p.append(f"mistake {i}: needs `s` (uzduotis), `fix` (teisinga eilute) and `e` (kas negerai)")
        b = m.get("board")
        p += [f"mistake {i} board: {y}" for y in board_problems(b, explained=False)]
        if isinstance(b, list) and (isinstance(m.get("bad"), bool) or not isinstance(m.get("bad"), int) or not 1 <= m["bad"] < len(b)):
            p.append(f"mistake {i}: `bad` must index a step after the task line (1..{len(b) - 1})")
        fixes = m.get("fix") if isinstance(m.get("fix"), list) else [str(m.get("fix", ""))]
        for f in fixes:
            p += [f"mistake {i} fix: {y}" for y in line_problems(str(f))]
        if not fixes or not re.match(r"\s*(?:~\s?)?Ats\.", str(fixes[-1])):
            p.append(f"mistake {i}: `fix` must continue the corrected solution through to an `Ats.:` line (reviewer 2026-09-10)")
    for k in ("topic", "subject", "title"):
        if not c.get(k):
            p.append(f"missing `{k}`")
    # reviewer 2026-09-12: a rewrite damaged Lithuanian letters (u-breve, combining ogonek) - refuse them anywhere in the content
    damaged = sorted(set(re.findall(r"\w*[̀-ͯŭĕĭŏă]\w*", json.dumps(c, ensure_ascii=False))))
    if damaged:
        p.append(f"damaged letters (combining marks or breve letters): {damaged[:8]} - normalise to NFC and use ą č ę ė į š ų ū ž")
    if c.get("lang") not in (None, "lt", "en"):
        p.append("`lang` must be lt or en")
    for i, r in enumerate(c.get("calcCard", {}).get("items", [])):
        if not r.get("t"):
            p.append(f"calcCard {i}: needs `t` (the task in words, e.g. 'Apskaičiuok 625^(3/4)')")
        p += calc.check(r.get("calc"), f"calcCard {i}: ")
    for i, q in enumerate(c.get("questions", [])):
        if q.get("c") not in (None, "calc", "head", "both"):
            p.append(f"question {i}: `c` must be calc (skaičiuotuvas daro), head (reikia galvos) or both")
    for i, r in enumerate(c.get("rooms", [])):
        if not r.get("place") or not r.get("topic"):
            p.append(f"room {i}: needs `place` and `topic`")
        if len(r.get("place", "")) > 20:
            p.append(f"room {i}: `place` \"{r['place']}\" is wider than the floor-plan box (max 20 chars)")
        for h in r.get("hooks", []):
            if len(h) != 3:
                p.append(f"room {i}: a hook must be [terminas, juokingas zodis, ka reiskia], got {h!r}")
    kws = {h[1] for r in c.get("rooms", []) for h in r.get("hooks", []) if len(h) == 3}
    room_kws = [{h[1] for h in r.get("hooks", []) if len(h) == 3} for r in c.get("rooms", [])]
    # association off (owner 2026-09-12): the memory block is never rendered, so a new page need not carry an invisible
    # first-letter sentence; memBlock() in the template returns '' for a question without `m`, so switching back on is safe
    assoc = association_on()
    for i, q in enumerate(c.get("questions", [])):
        for k in ("p", "q", "t", "a", "w") + (("m",) if assoc else ()):
            if k not in q:
                p.append(f"question {i}: missing `{k}`")
        m = q.get("m", {})
        for r in m.get("r", []):
            if r >= len(c.get("rooms", [])):
                p.append(f"question {i}: room {r} does not exist")
        cited = set().union(*[room_kws[r] for r in m.get("r", []) if r < len(room_kws)]) if m.get("r") else set()
        for h in m.get("h", []):
            if h in kws and cited and h not in cited:
                p.append(f"question {i}: hook \"{h}\" belongs to another room than the one(s) in `m.r` - the room chip would jump somewhere the hook is not")
            if h not in kws:
                p.append(f"question {i}: `m.h` must hold the room hook's KEYWORD (the funny word, hooks[1]), not the term - \"{h}\" is neither")
        if assoc and not m.get("s"):
            p.append(f"question {i}: no first-letter sentence in `m.s`")
    for i, x in enumerate(c.get("practice", [])):
        if not x.get("q") or not x.get("a"):
            p.append(f"practice {i}: needs `q` (uzduotis) and `a` (atsakymas)")
        sec = x.get("sec", 100)
        if isinstance(sec, bool) or not isinstance(sec, int) or not 30 <= sec <= 300:
            p.append(f"practice {i}: sec must be an integer from 30 to 300; split longer work")
        if x.get("chain") and (not isinstance(x.get("stage"), int) or isinstance(x.get("stage"), bool) or x["stage"] < 1):
            p.append(f"practice {i}: chain requires a positive integer stage")
    chains = {}
    for x in c.get("practice", []):
        if x.get("chain"):
            chains.setdefault(x['chain'], []).append(x.get('stage'))
    for chain, stages in chains.items():
        if any(not isinstance(s, int) or isinstance(s, bool) for s in stages) or sorted(stages) != list(range(1, len(stages)+1)):
            p.append(f"practice chain {chain}: stages must be unique and consecutive from 1")
    for i, l in enumerate(c.get("lessons", {}).get("items", [])):
        if not l.get("t"):
            p.append(f"lesson {i}: needs `t` (the teacher's own Moodle title)")
        if not l.get("gone") and not l.get("beats"):
            p.append(f"lesson {i}: no `beats` and not marked `gone` - a lesson with no evidence must say so")
        for b in l.get("beats", []):
            if len(b) != 2 or not str(b[0]).count(":"):
                p.append(f"lesson {i}: a beat must be [\"mm:ss\", \"kas matoma\"], got {b!r}")
    for i, m in enumerate(c.get("mnemonics", [])):
        if not isinstance(m, list) or len(m) not in (2, 3) or (len(m) == 3 and m[2] != "first-letter"):
            p.append(f"mnemonic {i}: must be [title, sentence] or [title, sentence, \"first-letter\"]")
    for i, t in enumerate(c.get("quiz", [])):
        if "o" in t and t.get("r") is None:
            p.append(f"quiz {i}: options need `r` (index of the right one)")
        if "o" not in t and not t.get("t"):
            p.append(f"quiz {i}: a fill-in item needs `t` (accepted answers)")
    for i, x in enumerate(c.get("exam", {}).get("tasks", [])):
        for k in ("year", "session", "part", "number", "points", "form", "subtopic", "question", "answer", "source"):
            if k not in x:
                p.append(f"exam task {i}: missing `{k}` (a real past paper must carry its provenance)")
    for s, r in c.get("exam", {}).get("subroom", {}).items():
        if r >= len(c.get("rooms", [])):
            p.append(f"subroom \"{s}\": room {r} does not exist")
    return p


def cmd_list():
    for f in sorted(STUDY.glob("*/*.json")):
        if f.name.endswith(".units.json"):
            continue
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "topic" not in c or "title" not in c:
            continue
        bits = [f"{len(c.get('questions', []))} klaus.", f"{sum(len(r.get('hooks', [])) for r in c.get('rooms', []))} kabliukų",
                f"{len(c.get('cards', []))} kort.", f"{len(c.get('quiz', []))} test.", f"{len(c.get('exam', {}).get('tasks', []))} VBE"]
        page = f.with_suffix(".html")
        print(f"{c['topic']:<22} {f.relative_to(ROOT).as_posix():<48} {'page' if page.exists() else 'NO PAGE':<8} " + " · ".join(bits))


def main(argv: list[str]):
    if not argv or argv[0] == "list":
        return cmd_list()
    cmd = argv[0]
    if cmd in ("build", "check") and len(argv) > 1:
        path = Path(argv[1]) if Path(argv[1]).is_absolute() else ROOT / argv[1]
        if cmd == "build":
            return build(path)
        c = json.loads(path.read_text(encoding="utf-8"))
        problems = check_content(c) + layout_problems(c, path)
        print("\n".join("  " + x for x in problems) if problems else "content ok")
        if problems:
            raise SystemExit(1)   # a failed check must fail the process too (glance 2026-09-12)
        return
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
