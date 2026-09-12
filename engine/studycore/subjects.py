"""subjects.py - which page SHAPE a course gets, from its name in any language.

The personal system adapts each page per subject (owner 2026-09-09): procedural (maths - formula wall, worked boards,
calculator strips, drills), factual (biology/geography/history - schemas, mechanism tables, real exam tasks), literary
(literature - works table, quote cards, paragraph practice), language (rule -> exercise, vocabulary decks, essay skeleton).
The product extends the maths style to physics, chemistry and every other computational subject (owner 2026-09-12) and
classifies any course name in any language by keyword families; unknown names fall back to `mixed` and can be set by the user
or by the digest model.
"""
from __future__ import annotations

import re
import unicodedata

FAMILIES: dict[str, dict] = {
    "math": {"shape": "procedural", "calc": True, "kw": ["matemat", "mathemat", "maths", "math ", "algebra", "geometr", "calculus", "matek", "wiskunde", "matte", "matematyka", "математик", "μαθηματ", "matematica", "matemat", "數學", "数学", "수학", "trigonometr", "statistic", "statistik"]},
    "physics": {"shape": "procedural", "calc": True, "kw": ["fizik", "physik", "physics", "physique", "física", "fisica", "fysik", "natuurkunde", "физик", "φυσικ", "物理", "물리"]},
    "chemistry": {"shape": "procedural", "calc": True, "kw": ["chemi", "chimie", "química", "quimica", "kemi", "scheikunde", "хими", "χημ", "chemij", "kimya", "化学", "화학"]},
    "computing": {"shape": "procedural", "calc": False, "kw": ["informatik", "informatic", "computing", "computer science", "programm", "coding", "informatique", "информатик", "programav", "software", "algorithm"]},
    "economics": {"shape": "factual", "calc": True, "kw": ["ekonom", "econom", "économ", "business", "verslo", "verslum", "finance", "accounting", "buhalter", "экономик"]},
    "biology": {"shape": "factual", "calc": False, "kw": ["biolog", "biologie", "biología", "биолог", "βιολογ", "生物", "생물"]},
    "geography": {"shape": "factual", "calc": False, "kw": ["geograf", "geograph", "géograph", "географ", "γεωγραφ", "地理", "지리"]},
    "history": {"shape": "factual", "calc": False, "kw": ["istorij", "histor", "geschichte", "histoire", "historia", "storia", "истори", "ιστορ", "歴史", "历史", "역사"]},
    "civics": {"shape": "factual", "calc": False, "kw": ["pilietiš", "civic", "politik", "politics", "social studies", "sozialkunde", "obywatel", "обществозн", "society", "visuomen"]},
    "religion": {"shape": "factual", "calc": False, "kw": ["tikyb", "religion", "religij", "etika", "ethic", "ethik", "philosoph", "filosof", "философ"]},
    "science": {"shape": "factual", "calc": True, "kw": ["science", "gamtos", "naturwissen", "sciences", "ciencias", "естествозн", "natural"]},
    "literature": {"shape": "literary", "calc": False, "kw": ["literat", "littérat", "literatur", "литератур", "λογοτεχν", "lietuvių kalba", "gimtoji", "native language", "mother tongue", "国語", "国语"]},
    "language": {"shape": "language", "calc": False, "kw": ["anglų", "english", "englisch", "anglais", "inglés", "ingles", "английск", "vokiečių", "deutsch", "german", "allemand", "prancūzų", "french", "français", "francés", "французск", "ispanų", "spanish", "español", "spagnolo", "испанск", "rusų", "russian", "русский", "italų", "italian", "italiano", "lenkų", "polish", "polski", "польск", "latvių", "latvian", "estų", "kalba", "language", "sprache", "langue", "idioma", "lingua", "язык", "esl", "efl", "japanese", "chinese", "korean", "arabic", "portuguese", "português", "svenska", "norsk", "dansk", "suomi", "nederlands", "türkçe"]},
    "arts": {"shape": "mixed", "calc": False, "kw": ["dailė", "art ", "kunst", "musik", "muzik", "music", "musique", "música", "drama", "theatre", "theater", "design", "photo"]},
    "pe": {"shape": "mixed", "calc": False, "kw": ["kūno", "physical education", "sport", "gym", "fizinis", "физкультур", "wychowanie fizyczne"]},
}

ORDER = ["math", "physics", "chemistry", "computing", "economics", "biology", "geography", "history", "civics", "religion",
         "literature", "language", "science", "arts", "pe"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " " + re.sub(r"\s+", " ", s.lower()).strip() + " "


def classify(course_name: str) -> dict:
    """{family, shape, calc, confidence}. Literature keywords win over the generic 'language' family (a native-language
    course is literary); a language course whose name also says 'literature' stays literary."""
    n = _norm(course_name)
    hits = []
    for fam in ORDER:
        for kw in FAMILIES[fam]["kw"]:
            k = _norm(kw).strip()
            if k and (k in n):
                hits.append((fam, len(k)))
                break
    if not hits:
        return {"family": "unknown", "shape": "mixed", "calc": False, "confidence": 0.0}
    fams = [f for f, _ in hits]
    fam = "literature" if "literature" in fams else max(hits, key=lambda h: h[1])[0]
    f = FAMILIES[fam]
    return {"family": fam, "shape": f["shape"], "calc": f["calc"], "confidence": 0.9 if len(fams) == 1 else 0.7}


def shape_sections(shape: str) -> list[str]:
    """The page sections a shape renders (mirrors the personal topic.py adaptation per subject)."""
    return {
        "procedural": ["formulaWall", "taskTypes", "boards", "calcCard", "practice", "mistakes", "cards", "quiz"],
        "factual": ["schema", "mechanismTable", "questions", "numbers", "cards", "quiz", "examTasks"],
        "literary": ["worksTable", "quoteCards", "questions", "paragraphPractice", "cards", "quiz"],
        "language": ["ruleExercise", "vocabularyDecks", "essaySkeleton", "questions", "cards", "quiz"],
        "mixed": ["questions", "numbers", "cards", "quiz"],
    }.get(shape, ["questions", "cards", "quiz"])
