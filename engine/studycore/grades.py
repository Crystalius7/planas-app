"""grades.py - grading scales and the coverage <-> grade mapping.

Every number here is an ESTIMATE (partner DISAGREE 3, 2026-09-12): a grade is mapped from the probability-weighted share of
the core material a plan covers, through the country's usual percentage bands, and the app shows it as a band with the
uncertainty stated. `min_score(scale, grade)` is the lower percentage bound of a grade; `coverage_for(scale, grade)` adds a
margin because covering a fact is not the same as scoring it.
"""
from __future__ import annotations

MARGIN = 0.10          # coverage needed above the band's lower bound
FLOOR = 0.15           # score a student gets with nothing learned (prior knowledge, guessing)
CEIL = 0.95            # score with every core unit learned - nobody scores 100 % from a plan
BAND = 0.08            # +/- on the estimated score

# best grade first; (label, minimum score 0..1). Sources: the usual national conversion tables; a school may differ,
# which is why the scale is a user setting and the app says "estimate".
SCALES: dict[str, dict] = {
    "pct":  {"name": "Percent", "grades": [(str(p), p / 100) for p in range(100, -1, -5)], "pass": "50", "good": "80", "kind": "number"},
    "lt10": {"name": "Lithuania 1-10", "grades": [("10", .95), ("9", .85), ("8", .75), ("7", .65), ("6", .55), ("5", .45), ("4", .35), ("3", .25), ("2", .15), ("1", 0)], "pass": "4", "good": "8", "kind": "number"},
    "lv10": {"name": "Latvia 1-10", "grades": [("10", .95), ("9", .85), ("8", .75), ("7", .65), ("6", .55), ("5", .45), ("4", .35), ("3", .25), ("2", .15), ("1", 0)], "pass": "4", "good": "8", "kind": "number"},
    "ee5":  {"name": "Estonia 1-5", "grades": [("5", .90), ("4", .75), ("3", .50), ("2", .20), ("1", 0)], "pass": "3", "good": "4", "kind": "number"},
    "pl6":  {"name": "Poland 1-6", "grades": [("6", .98), ("5", .90), ("4", .75), ("3", .50), ("2", .30), ("1", 0)], "pass": "2", "good": "4", "kind": "number"},
    "de6":  {"name": "Germany 1-6 (1 best)", "grades": [("1", .92), ("2", .81), ("3", .67), ("4", .50), ("5", .30), ("6", 0)], "pass": "4", "good": "2", "kind": "number-inverted"},
    "at5":  {"name": "Austria 1-5 (1 best)", "grades": [("1", .90), ("2", .80), ("3", .65), ("4", .50), ("5", 0)], "pass": "4", "good": "2", "kind": "number-inverted"},
    "ch6":  {"name": "Switzerland 1-6", "grades": [("6", .95), ("5.5", .875), ("5", .80), ("4.5", .70), ("4", .60), ("3.5", .50), ("3", .40), ("2", .20), ("1", 0)], "pass": "4", "good": "5", "kind": "number"},
    "fr20": {"name": "France 0-20", "grades": [(str(g), g / 20) for g in range(20, -1, -1)], "pass": "10", "good": "14", "kind": "number"},
    "es10": {"name": "Spain 0-10", "grades": [(str(g), g / 10) for g in range(10, -1, -1)], "pass": "5", "good": "8", "kind": "number"},
    "it10": {"name": "Italy 0-10", "grades": [(str(g), g / 10) for g in range(10, -1, -1)], "pass": "6", "good": "8", "kind": "number"},
    "pt20": {"name": "Portugal 0-20", "grades": [(str(g), g / 20) for g in range(20, -1, -1)], "pass": "10", "good": "14", "kind": "number"},
    "nl10": {"name": "Netherlands 1-10", "grades": [(str(g), (g - 1) / 9) for g in range(10, 0, -1)], "pass": "6", "good": "8", "kind": "number"},
    "ua12": {"name": "Ukraine 1-12", "grades": [(str(g), (g - 1) / 11) for g in range(12, 0, -1)], "pass": "4", "good": "9", "kind": "number"},
    "ru5":  {"name": "5-point (2-5)", "grades": [("5", .85), ("4", .65), ("3", .45), ("2", 0)], "pass": "3", "good": "4", "kind": "number"},
    "us":   {"name": "US letters", "grades": [("A", .90), ("B", .80), ("C", .70), ("D", .60), ("F", 0)], "pass": "D", "good": "B", "kind": "letter"},
    "uk9":  {"name": "UK GCSE 9-1", "grades": [("9", .85), ("8", .77), ("7", .70), ("6", .60), ("5", .50), ("4", .40), ("3", .30), ("2", .20), ("1", .10), ("U", 0)], "pass": "4", "good": "7", "kind": "number"},
    "fi10": {"name": "Finland 4-10", "grades": [("10", .95), ("9", .85), ("8", .75), ("7", .65), ("6", .55), ("5", .45), ("4", 0)], "pass": "5", "good": "8", "kind": "number"},
    "se":   {"name": "Sweden A-F", "grades": [("A", .90), ("B", .80), ("C", .70), ("D", .60), ("E", .50), ("F", 0)], "pass": "E", "good": "B", "kind": "letter"},
    "tr100": {"name": "Turkey 0-100", "grades": [(str(p), p / 100) for p in range(100, -1, -5)], "pass": "50", "good": "85", "kind": "number"},
}

COUNTRY_SCALE = {
    "LT": "lt10", "LV": "lv10", "EE": "ee5", "PL": "pl6", "DE": "de6", "AT": "at5", "CH": "ch6", "FR": "fr20", "BE": "pt20",
    "ES": "es10", "IT": "it10", "PT": "pt20", "NL": "nl10", "UA": "ua12", "RU": "ru5", "BY": "ru5", "KZ": "ru5",
    "US": "us", "CA": "us", "GB": "uk9", "IE": "pct", "AU": "pct", "NZ": "pct", "IN": "pct", "FI": "fi10", "SE": "se",
    "NO": "ee5", "DK": "pct", "TR": "tr100", "BR": "es10", "MX": "es10", "AR": "es10", "CL": "es10", "CO": "es10",
}


def scale(key: str | None) -> dict:
    return SCALES.get(key or "pct", SCALES["pct"])


def scale_for_country(cc: str | None) -> str:
    return COUNTRY_SCALE.get((cc or "").upper(), "pct")


def labels(key: str) -> list[str]:
    return [g for g, _ in scale(key)["grades"]]


def min_score(key: str, grade: str | None) -> float:
    s = scale(key)
    g = str(grade) if grade is not None else s["good"]
    for label, lo in s["grades"]:
        if label == g:
            return lo
    return dict(s["grades"]).get(s["good"], 0.75)


def coverage_for(key: str, grade: str | None) -> float:
    """Share of the probability-weighted core a plan must cover to make `grade` plausible (an estimate)."""
    return round(min(1.0, max(0.5, min_score(key, grade) + MARGIN)), 2)


def score_for_coverage(coverage: float) -> float:
    return FLOOR + (CEIL - FLOOR) * max(0.0, min(1.0, coverage))


def grade_for_score(key: str, score: float) -> str:
    for label, lo in scale(key)["grades"]:
        if score >= lo:
            return label
    return scale(key)["grades"][-1][0]


def estimate(key: str, coverage: float) -> dict:
    """Estimated grade band for a plan covering `coverage` of the weighted core. Always labelled an estimate by the caller."""
    sc = score_for_coverage(coverage)
    return {"coverage": round(coverage, 3), "score": round(sc, 3), "grade": grade_for_score(key, sc),
            "low": grade_for_score(key, sc - BAND), "high": grade_for_score(key, min(CEIL, sc + BAND)), "estimate": True}


def grade_index(key: str, grade: str) -> int:
    """Position from the top (0 = best); used to say 'the grade drops by N steps'."""
    for i, (label, _) in enumerate(scale(key)["grades"]):
        if label == str(grade):
            return i
    return len(scale(key)["grades"]) - 1
