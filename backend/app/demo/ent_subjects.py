"""The demo's ЕНТ subjects.

The four profile subjects (Mathematics, Physics, Chemistry, Biology) are in
the fixed 40-question profile structure (app.core.ent_structure); their
quotas are unused. The compulsory ones keep their per-type quotas:
mathematical and reading literacy are short sections on the real exam (10),
history longer (20).
"""

from app.demo.ent_bank import HISTORY_ENT, MATH_LIT_ENT, READING_ENT
from app.demo.ent_bank_kk import HISTORY_ENT_KK, MATH_LIT_ENT_KK, READING_ENT_KK
from app.demo.ent_profile_bank import BIOLOGY_PROFILE, CHEMISTRY_PROFILE, MATH_PROFILE, PHYSICS_PROFILE
from app.demo.ent_profile_bank_kk import (
    BIOLOGY_PROFILE_KK,
    CHEMISTRY_PROFILE_KK,
    MATH_PROFILE_KK,
    PHYSICS_PROFILE_KK,
)

_NO_QUOTAS = {"single": 0, "multiple": 0, "matching": 0, "short": 0}

SUBJECTS = [
    {"name": "Математика", "slug": "matematika", "teacher": "erlan", "profile": True,
     "questions": MATH_PROFILE, "questions_kk": MATH_PROFILE_KK, "quotas": _NO_QUOTAS},
    {"name": "История Казахстана", "slug": "istoriya-kazakhstana", "teacher": "gulnara", "profile": False,
     "questions": HISTORY_ENT, "questions_kk": HISTORY_ENT_KK,
     "quotas": {"single": 13, "multiple": 3, "matching": 2, "short": 2}},
    {"name": "Математическая грамотность", "slug": "matematicheskaya-gramotnost", "teacher": "erlan", "profile": False,
     "questions": MATH_LIT_ENT, "questions_kk": MATH_LIT_ENT_KK,
     "quotas": {"single": 6, "multiple": 2, "matching": 1, "short": 1}},
    {"name": "Грамотность чтения", "slug": "gramotnost-chteniya", "teacher": "gulnara", "profile": False,
     "questions": READING_ENT, "questions_kk": READING_ENT_KK,
     "quotas": {"single": 6, "multiple": 2, "matching": 1, "short": 1}},
    {"name": "Физика", "slug": "fizika", "teacher": "nurlan", "profile": True,
     "questions": PHYSICS_PROFILE, "questions_kk": PHYSICS_PROFILE_KK, "quotas": _NO_QUOTAS},
    {"name": "Химия", "slug": "himiya", "teacher": "nurlan", "profile": True,
     "questions": CHEMISTRY_PROFILE, "questions_kk": CHEMISTRY_PROFILE_KK, "quotas": _NO_QUOTAS},
    {"name": "Биология", "slug": "biologiya", "teacher": "nurlan", "profile": True,
     "questions": BIOLOGY_PROFILE, "questions_kk": BIOLOGY_PROFILE_KK, "quotas": _NO_QUOTAS},
]

PROFILE_SUBJECTS = [s for s in SUBJECTS if s["profile"]]
