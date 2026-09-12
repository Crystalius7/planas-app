"""studycore - the study engine shared by the personal 12th-grade system and the product.

vendor/   one-way synced copies of the personal tools (product/tools/sync_engine.py) - never edited here
workspace  per-user workspace (same layout as the personal study/ + courses/), settings, binding of the vendored modules
planner    the two sliders: minutes per day (with the forced adaptable minimum) and the grade target; estimates
grades     grading scales per country and the coverage <-> grade mapping (labelled estimates)
subjects   subject family + page shape from a course name in any language (procedural/factual/literary/language)
collect    Moodle collectors: web-service token (Route A), logged-in session (Route B/C), extension bundle import
digest     material -> content JSON through a model adapter (ollama | anthropic | openai | none)
notify     what is new since the last scan (courses, modules, files, deadlines) -> notification records
render     topic page + units in any UI language (wraps vendor/topic.py and vendor/units.py)
factcheck  the "certain facts beat the material" switch, OFF by default; every correction listed with its basis
"""
__version__ = "0.1.0"
