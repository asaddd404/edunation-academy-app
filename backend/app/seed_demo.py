"""Resets the database and fills it with the client-presentation demo.

    docker compose exec -e DEMO_PASSWORD=DemoPass123 backend python -m app.seed_demo

What it creates: five courses whose 33 lessons each have a real YouTube
lesson, notes, homework and a mini-test, plus a test per section; a 200
question ЕНТ bank (5 subjects x 40, all four question types); ten named
accounts -- an admin, three teachers, a "VIP" student with every course open
and every lesson unlocked, five students in different states -- and 24 more
students whose test attempts, ЕНТ simulations and homework fill the
leaderboards, the teachers' review queues and the admin panel.

Safety, as in the previous seed:

* It refuses to run when ENV=production unless `--force-production` is given:
  the first thing it does is TRUNCATE every table.
* The password comes from DEMO_PASSWORD, or is generated and printed once;
  it is never a constant in the repository.

Every course and ЕНТ question is validated with the API's own schemas before
anything is written, so the demo cannot contain a question the app would
refuse to save. Scores are computed with the app's grader and XP with its
rating rules, so the leaderboards add up exactly as they would live.
"""

import asyncio
import os
import random
import secrets
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.question_scoring import grade_question
from app.core.rating import compute_test_xp
from app.core.storage import UPLOAD_ROOT
from app.database import Base, async_session_factory
from app.demo.courses import COURSES
from app.demo.ent_bank import SUBJECTS
from app.models import (
    AnswerVariant,
    Application,
    ApplicationStatusEnum,
    Category,
    Choice,
    EntAnswerVariant,
    EntChoice,
    EntLanguage,
    EntMatchPair,
    EntQuestion,
    EntQuestionType,
    EntSimulation,
    EntSimulationQuestion,
    EntSimulationStatus,
    EntSubject,
    HomeworkStatusEnum,
    HomeworkSubmission,
    Lesson,
    MatchPair,
    Notification,
    Question,
    RoleEnum,
    Section,
    StudentRating,
    TestAttempt,
    TestAttemptStatus,
    User,
    UserDailyActivity,
    XpEvent,
    XpSource,
    teacher_categories,
)
from app.schemas.ent_question import EntQuestionIn
from app.schemas.question import QuestionIn
from app.security import hash_password

RNG_SEED = 20261023
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ENT_MINUTES_PER_SUBJECT = 48  # same rule as frontend/src/utils/examDuration.ts

# --- accounts -----------------------------------------------------------------

STAFF = [
    # key, phone, first, last, role, description for the final table
    ("admin", "+77001000001", "Асель", "Нурланова", RoleEnum.admin, "Администратор: пользователи, курсы, все заявки"),
    ("erlan", "+77001000002", "Ерлан", "Жумабаев", RoleEnum.teacher, "Учитель: Математика, Математическая грамотность"),
    ("gulnara", "+77001000003", "Гульнара", "Ахметова", RoleEnum.teacher, "Учитель: История Казахстана, Грамотность чтения"),
    ("nurlan", "+77001000004", "Нурлан", "Сапаров", RoleEnum.teacher, "Учитель: Физика"),
]


@dataclass
class StudentPlan:
    key: str
    phone: str
    first: str
    last: str
    note: str
    skill: float                       # chance of answering a question right
    approved: list[str]                # course keys
    pending: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    progress: float = 0.0              # share of lessons passed per approved course
    simulations: int = 0
    activity_minutes: int = 0


KEY_STUDENTS = [
    StudentPlan("vip", "+77001000010", "Демо Ученик", "VIP", "VIP: все 5 курсов, все уроки и тесты открыты, ЕНТ-тренажёр",
                0.9, ["math", "history", "mathlit", "reading", "physics"], progress=1.0, simulations=3, activity_minutes=34),
    StudentPlan("aigerim", "+77001000011", "Айгерим", "Оспанова", "Отличница: 3 курса, в топе рейтинга",
                0.93, ["math", "mathlit", "history"], progress=0.9, simulations=7, activity_minutes=52),
    StudentPlan("daniyar", "+77001000012", "Данияр", "Ахметов", "Физика и Математика, средний уровень",
                0.74, ["physics", "math"], progress=0.6, simulations=4, activity_minutes=21),
    StudentPlan("tomiris", "+77001000013", "Томирис", "Касымова", "История и Чтение; заявка на Математику на рассмотрении",
                0.85, ["history", "reading"], pending=["math"], progress=0.7, simulations=4, activity_minutes=17),
    StudentPlan("arman", "+77001000014", "Арман", "Серикбаев", "Новичок: заявки на Математику и Физику ждут решения",
                0.6, [], pending=["math", "physics"], activity_minutes=4),
    StudentPlan("kamila", "+77001000015", "Камила", "Дюсенова", "Математика; заявка на Чтение отклонена",
                0.62, ["math"], rejected=["reading"], progress=0.4, simulations=2, activity_minutes=9),
]

BACKGROUND_NAMES = [
    ("Нурсултан", "Байжанов"), ("Аружан", "Байжанова"), ("Дархан", "Нурпейсов"), ("Сабина", "Касымова"),
    ("Мирас", "Кенжебаев"), ("Аяна", "Нурпейсова"), ("Ерасыл", "Смагулов"), ("Диана", "Смагулова"),
    ("Бекзат", "Касымов"), ("Алия", "Ержанова"), ("Дамир", "Дюсенов"), ("Жасмин", "Даулетова"),
    ("Санжар", "Тлеубердиев"), ("Гаухар", "Мухаметжанова"), ("Асет", "Сагындыков"), ("Асель", "Абенова"),
    ("Куаныш", "Толегенов"), ("Инкар", "Искакова"), ("Тимур", "Муратов"), ("Меруерт", "Салыкова"),
    ("Азамат", "Бекенов"), ("Дильназ", "Тастанова"), ("Бауыржан", "Сериков"), ("Малика", "Райымбекова"),
]

COURSE_KEYS = [c["key"] for c in COURSES]


def background_students(rng: random.Random) -> list[StudentPlan]:
    plans = []
    for i, (first, last) in enumerate(BACKGROUND_NAMES):
        approved = rng.sample(COURSE_KEYS, rng.randint(1, 3))
        rest = [k for k in COURSE_KEYS if k not in approved]
        pending = [rng.choice(rest)] if i % 6 == 0 else []
        plans.append(StudentPlan(
            f"bg{i}", f"+7700200{i + 1:04d}", first, last, "Ученик (фон для рейтинга)",
            round(rng.uniform(0.45, 0.88), 2), approved, pending=pending,
            progress=round(rng.uniform(0.15, 0.85), 2), simulations=rng.randint(0, 5),
            activity_minutes=rng.choice([0, 0, 5, 12, 18, 27, 40]),
        ))
    return plans


# --- validation -----------------------------------------------------------------


def _as_api_payload(spec: dict) -> dict:
    qtype = spec["qtype"]
    return {
        "qtype": qtype.value,
        "text": spec["text"],
        "max_score": spec["max_score"],
        "choices": [{"text": t, "is_correct": c} for t, c in spec.get("choices", [])],
        "match_pairs": [{"prompt_text": a, "answer_text": b} for a, b in spec.get("pairs", [])],
        "answer_variants": spec.get("variants", []),
    }


def validate_content() -> None:
    """Every question through the API's own schema -- fails loudly before
    the database is touched."""
    problems = []
    for course in COURSES:
        for section in course["sections"]:
            specs = [q for lesson in section["lessons"] for q in lesson["test"]] + section["test"]
            for spec in specs:
                try:
                    QuestionIn.model_validate(_as_api_payload(spec))
                except Exception as e:  # noqa: BLE001 -- collected and reported below
                    problems.append(f"{course['name']} / {spec['text'][:60]}: {e}")
    for subject in SUBJECTS:
        type_split = {}
        for language, key in (("ru", "questions"), ("kk", "questions_kk")):
            specs = subject[key]
            if len(specs) != 40:
                problems.append(f"{subject['name']} ({language}): {len(specs)} вопросов вместо 40")
            type_split[language] = sorted(spec["qtype"].value for spec in specs)
            for spec in specs:
                try:
                    EntQuestionIn.model_validate({**_as_api_payload(spec), "language": language})
                except Exception as e:  # noqa: BLE001
                    problems.append(f"ЕНТ {subject['name']} ({language}) / {spec['text'][:60]}: {e}")
        if type_split["ru"] != type_split["kk"]:
            problems.append(f"{subject['name']}: в казахском банке другое распределение типов вопросов")
    if problems:
        raise SystemExit("Контент не прошёл проверку схемами API:\n  " + "\n  ".join(problems))


# --- reset ----------------------------------------------------------------------


async def reset_database(db: AsyncSession) -> None:
    """TRUNCATE every table the app owns (not alembic_version), restarting ids."""
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await db.commit()


def clear_uploads() -> None:
    """Files belonged to rows that no longer exist.

    Empties each directory but keeps the directory itself: in production the
    uploads volume's root belongs to whoever created the volume, and the
    unprivileged app user may not be able to create a removed subdirectory
    again -- which turned every later upload into a 500.
    """
    for sub in ("homework", "avatars", "categories", "ent-questions", "lesson-content", "video_raw", "hls"):
        path = UPLOAD_ROOT / sub
        if not path.is_dir():
            continue
        for entry in path.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)


# --- builders -------------------------------------------------------------------


def build_question(spec: dict, model, choice_cls, pair_cls, variant_cls, order_index: int, **owner):
    q = model(qtype=spec["qtype"], text=spec["text"], max_score=spec["max_score"], order_index=order_index, **owner)
    # The specs list the right option first (easy to write and review); the
    # app shows options in stored order, so they are shuffled here -- or the
    # answer to every demo question would be "A". Seeded by the question text,
    # so a re-seed gives the same order.
    choices = list(spec.get("choices", []))
    random.Random(spec["text"]).shuffle(choices)
    q.choices = [choice_cls(text=t, is_correct=c, order_index=i) for i, (t, c) in enumerate(choices)]
    q.match_pairs = [pair_cls(prompt_text=a, answer_text=b, order_index=i) for i, (a, b) in enumerate(spec.get("pairs", []))]
    q.answer_variants = [variant_cls(text=v) for v in spec.get("variants", [])]
    return q


def days_ago(days: float, rng: random.Random | None = None) -> datetime:
    jitter = timedelta(minutes=rng.randint(0, 600)) if rng else timedelta()
    return NOW - timedelta(days=days) + jitter


@dataclass
class CourseRecord:
    key: str
    category: Category
    teacher: User
    sections: list[tuple[Section, list[Lesson], list[Question]]]  # section, lessons, section questions
    lesson_questions: dict[int, list[Question]]


async def create_people(db: AsyncSession, rng: random.Random):
    pw = hash_password(DEMO_PASSWORD)
    staff: dict[str, User] = {}
    for key, phone, first, last, role, _ in STAFF:
        user = User(phone=phone, password_hash=pw, first_name=first, last_name=last, role=role, created_at=days_ago(75))
        db.add(user)
        staff[key] = user
    plans = KEY_STUDENTS + background_students(rng)
    students: dict[str, User] = {}
    for i, plan in enumerate(plans):
        user = User(phone=plan.phone, password_hash=pw, first_name=plan.first, last_name=plan.last,
                    role=RoleEnum.student, created_at=days_ago(60 - (i % 20), rng))
        db.add(user)
        students[plan.key] = user
    await db.flush()
    return staff, plans, students


async def create_courses(db: AsyncSession, staff: dict[str, User]) -> dict[str, CourseRecord]:
    records: dict[str, CourseRecord] = {}
    for course in COURSES:
        teacher = staff[course["teacher"]]
        category = Category(name=course["name"], slug=course["slug"], description=course["description"], is_active=True,
                            created_at=days_ago(70))
        db.add(category)
        await db.flush()
        await db.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
        sections_out = []
        lesson_questions: dict[int, list[Question]] = {}
        for s_index, spec in enumerate(course["sections"]):
            section = Section(category_id=category.id, title=spec["title"], description=spec["description"], order_index=s_index)
            db.add(section)
            await db.flush()
            lessons = []
            for l_index, ls in enumerate(spec["lessons"]):
                lesson = Lesson(section_id=section.id, title=ls["title"], description=ls["notes"], video_url=ls["video"],
                                homework_assignment=ls["homework"], order_index=l_index)
                db.add(lesson)
                await db.flush()
                questions = [build_question(q, Question, Choice, MatchPair, AnswerVariant, i, lesson_id=lesson.id)
                             for i, q in enumerate(ls["test"])]
                db.add_all(questions)
                lesson_questions[lesson.id] = questions
                lessons.append(lesson)
            section_questions = [build_question(q, Question, Choice, MatchPair, AnswerVariant, i, section_id=section.id)
                                 for i, q in enumerate(spec["test"])]
            db.add_all(section_questions)
            sections_out.append((section, lessons, section_questions))
        await db.flush()
        records[course["key"]] = CourseRecord(course["key"], category, teacher, sections_out, lesson_questions)
    return records


async def create_ent_bank(
    db: AsyncSession, staff: dict[str, User]
) -> dict[int, tuple[EntSubject, dict[EntLanguage, list[EntQuestion]]]]:
    bank = {}
    for spec in SUBJECTS:
        q = spec["quotas"]
        subject = EntSubject(name=spec["name"], slug=spec["slug"], is_active=True, created_by_id=staff[spec["teacher"]].id,
                             single_choice_count=q["single"], multiple_choice_count=q["multiple"],
                             matching_count=q["matching"], short_answer_count=q["short"])
        db.add(subject)
        await db.flush()
        by_language = {}
        for language, key in ((EntLanguage.ru, "questions"), (EntLanguage.kk, "questions_kk")):
            questions = [build_question(qs, EntQuestion, EntChoice, EntMatchPair, EntAnswerVariant, i,
                                        subject_id=subject.id, language=language, created_by_id=staff[spec["teacher"]].id)
                         for i, qs in enumerate(spec[key])]
            db.add_all(questions)
            by_language[language] = questions
        await db.flush()
        bank[subject.id] = (subject, by_language)
    return bank


# --- activity -------------------------------------------------------------------


def notify(db: AsyncSession, user: User, kind: str, message: str, link: str, at: datetime, read: bool) -> None:
    db.add(Notification(user_id=user.id, type=kind, message=message, link=link, is_read=read, created_at=at))


async def create_applications(db, plans, students, courses, staff, rng):
    admin = staff["admin"]
    for plan in plans:
        student = students[plan.key]
        name = f"{student.first_name} {student.last_name}"
        for status, keys in ((ApplicationStatusEnum.approved, plan.approved), (ApplicationStatusEnum.pending, plan.pending),
                             (ApplicationStatusEnum.rejected, plan.rejected)):
            for key in keys:
                course = courses[key]
                created = days_ago(rng.randint(1, 4) if status == ApplicationStatusEnum.pending else rng.randint(40, 58), rng)
                decided = created + timedelta(hours=rng.randint(2, 30)) if status != ApplicationStatusEnum.pending else None
                db.add(Application(student_id=student.id, category_id=course.category.id, status=status,
                                   decided_by=course.teacher.id if decided else None, decided_at=decided, created_at=created))
                if status == ApplicationStatusEnum.pending:
                    for recipient in (course.teacher, admin):
                        notify(db, recipient, "new_application", f"Новая заявка от {name} на курс «{course.category.name}»",
                               "/teacher", created, read=False)
                else:
                    word = "одобрена" if status == ApplicationStatusEnum.approved else "отклонена"
                    notify(db, student, f"application_{status.value}", f"Заявка на курс «{course.category.name}» {word}",
                           "/my-applications", decided, read=plan.key != "kamila")


def simulate_points(questions: list[Question], skill: float, rng: random.Random) -> tuple[int, int, int]:
    earned = correct = 0
    for q in questions:
        if rng.random() < skill:
            earned += q.max_score
            correct += 1
        elif q.max_score == 2 and rng.random() < 0.35:
            earned += 1
    return earned, sum(q.max_score for q in questions), correct


class XpLedger:
    """Mirrors core.rating: course tests pay only their improvement."""

    def __init__(self) -> None:
        self.awarded: dict[tuple[int, str, int], int] = {}
        self.total: dict[int, int] = {}

    def add(self, student_id: int, xp: int) -> None:
        self.total[student_id] = self.total.get(student_id, 0) + xp


def add_attempt(db, ledger: XpLedger, student: User, questions: list[Question], skill: float, at: datetime,
                rng: random.Random, *, lesson_id=None, section_id=None, must_pass: bool) -> TestAttempt:
    at = min(at, NOW - timedelta(hours=1))
    for _ in range(50):
        earned, max_points, correct = simulate_points(questions, skill, rng)
        score = round(earned / max_points * 100)
        if (score >= 50) == must_pass:
            break
    duration = sum(rng.randint(18, 75) for _ in questions)
    attempt = TestAttempt(
        student_id=student.id, lesson_id=lesson_id, section_id=section_id, status=TestAttemptStatus.completed,
        started_at=at - timedelta(seconds=duration), submitted_at=at, score=score, passed=score >= 50,
        earned_points=earned, max_points=max_points, correct_count=correct, question_count=len(questions),
        duration_seconds=duration, xp_earned=0, created_at=at - timedelta(seconds=duration),
    )
    db.add(attempt)
    return attempt


async def create_progress(db, plans, students, courses, ledger: XpLedger, rng):
    """Lesson mini-tests and section tests, in course order, so each student's
    unlocked lessons are exactly the ones a real student would have."""
    pending_xp: list[tuple[TestAttempt, User, XpSource, tuple]] = []
    passed_lessons: dict[str, list[tuple[Lesson, datetime]]] = {}
    for plan in plans:
        student = students[plan.key]
        passed_lessons[plan.key] = []
        for key in plan.approved:
            course = courses[key]
            all_lessons = [lesson for _, lessons, _ in course.sections for lesson in lessons]
            n_pass = len(all_lessons) if plan.progress >= 1 else int(round(len(all_lessons) * plan.progress))
            clock = days_ago(rng.randint(30, 45), rng)
            done = 0
            for section, lessons, section_questions in course.sections:
                section_done = True
                for lesson in lessons:
                    if done >= n_pass:
                        section_done = False
                        break
                    questions = course.lesson_questions[lesson.id]
                    clock += timedelta(hours=rng.randint(10, 40))
                    if rng.random() < (1 - plan.skill) * 0.9:
                        add_attempt(db, ledger, student, questions, plan.skill, clock, rng, lesson_id=lesson.id, must_pass=False)
                        clock += timedelta(minutes=rng.randint(20, 300))
                    attempt = add_attempt(db, ledger, student, questions, plan.skill, clock, rng, lesson_id=lesson.id, must_pass=True)
                    pending_xp.append((attempt, student, XpSource.lesson_test, ("lesson", lesson.id)))
                    passed_lessons[plan.key].append((lesson, clock))
                    done += 1
                if section_done and (plan.key == "vip" or rng.random() < 0.8):
                    clock += timedelta(hours=rng.randint(5, 30))
                    attempt = add_attempt(db, ledger, student, section_questions, plan.skill, clock, rng,
                                          section_id=section.id, must_pass=True)
                    pending_xp.append((attempt, student, XpSource.section_test, ("section", section.id)))
                if not section_done:
                    break
    await db.flush()
    for attempt, student, source, scope in pending_xp:
        worth = compute_test_xp(attempt.earned_points, attempt.max_points, attempt.question_count, attempt.duration_seconds).total
        k = (student.id, *scope)
        gain = max(0, worth - ledger.awarded.get(k, 0))
        if gain:
            ledger.awarded[k] = ledger.awarded.get(k, 0) + gain
            attempt.xp_earned = gain
            ledger.add(student.id, gain)
            db.add(XpEvent(student_id=student.id, source=source.value, source_id=attempt.id, xp=gain, created_at=attempt.submitted_at))
    return passed_lessons


HOMEWORK_ANSWERS = [
    "Решила все задания, проверку сделала подстановкой. В последнем примере сомневаюсь в знаке.",
    "Выполнил задание, решение в прикреплённом файле. Ответы: см. конспект.",
    "Сделал все пункты. Второй пример решал двумя способами — ответ совпал.",
    "Готово. Самым сложным оказался третий пункт, расписал ход рассуждений подробно.",
]
ACCEPTED = ["Отличная работа, всё верно!", "Хорошо, решение аккуратное и полное.", "Молодец! Ход решения понятен, ответы верные."]
REVISION = ["Проверьте третий пункт — ошибка в вычислениях.", "Распишите решение второго задания подробнее и отправьте снова."]


async def create_homework(db, plans, students, courses, passed_lessons, rng):
    lesson_course = {lesson.id: c for c in courses.values() for _, lessons, _ in c.sections for lesson in lessons}
    for plan in plans:
        student = students[plan.key]
        name = f"{student.first_name} {student.last_name}"
        submitted = [x for x in passed_lessons[plan.key] if rng.random() < (0.55 if plan.key in ("aigerim", "tomiris", "daniyar") else 0.3)]
        for index, (lesson, at) in enumerate(submitted):
            course = lesson_course[lesson.id]
            created = at + timedelta(hours=rng.randint(1, 20))
            if index == len(submitted) - 1:  # the newest one waits in the teacher's queue
                status, feedback, reviewed_at = HomeworkStatusEnum.submitted, None, None
                created = NOW - timedelta(hours=rng.randint(2, 72))
            else:
                status = HomeworkStatusEnum.revision_requested if rng.random() < 0.2 else HomeworkStatusEnum.accepted
                feedback = rng.choice(REVISION if status == HomeworkStatusEnum.revision_requested else ACCEPTED)
                reviewed_at = min(created + timedelta(hours=rng.randint(3, 36)), NOW - timedelta(hours=1))
            created = min(created, NOW - timedelta(hours=2))
            db.add(HomeworkSubmission(lesson_id=lesson.id, student_id=student.id, text_answer=rng.choice(HOMEWORK_ANSWERS),
                                      status=status, teacher_feedback=feedback,
                                      reviewed_by=course.teacher.id if reviewed_at else None, reviewed_at=reviewed_at,
                                      created_at=created))
            if status == HomeworkStatusEnum.submitted:
                notify(db, course.teacher, "new_homework", f"{name} сдал(а) домашнее задание по уроку «{lesson.title}»",
                       "/teacher/homework", created, read=False)
            else:
                label = "принята" if status == HomeworkStatusEnum.accepted else "отправлена на доработку"
                notify(db, student, "homework_reviewed", f"Домашняя работа по уроку «{lesson.title}» {label}",
                       f"/lessons/{lesson.id}", reviewed_at, read=reviewed_at < NOW - timedelta(days=3))


def ent_answer(question: EntQuestion, right: bool, rng: random.Random) -> dict:
    if question.qtype == EntQuestionType.single:
        good = next(c for c in question.choices if c.is_correct)
        bad = [c for c in question.choices if not c.is_correct]
        return {"choice_id": (good if right else rng.choice(bad)).id}
    if question.qtype == EntQuestionType.multiple:
        good = [c.id for c in question.choices if c.is_correct]
        return {"choice_ids": good if right else good[:1]}
    if question.qtype == EntQuestionType.matching:
        ids = [p.id for p in question.match_pairs]
        if right:
            return {"pairs": {str(i): i for i in ids}}
        shuffled = ids[1:] + ids[:1]
        return {"pairs": {str(i): j for i, j in zip(ids, shuffled)}}
    return {"text": question.answer_variants[0].text if right else "не знаю"}


async def create_simulations(db, plans, students, bank, ledger: XpLedger, rng):
    stats: dict[int, dict] = {}
    subject_ids = list(bank)
    for plan in plans:
        student = students[plan.key]
        for n in range(plan.simulations):
            chosen = rng.sample(subject_ids, rng.randint(1, 3))
            timed = rng.random() < 0.7
            duration = ENT_MINUTES_PER_SUBJECT * len(chosen) if timed else None
            started = days_ago(rng.uniform(1, 40), rng)
            took = timedelta(minutes=rng.randint(15, (duration or 90) - 3))
            expired = timed and rng.random() < 0.1
            submitted = started + (timedelta(minutes=duration + rng.randint(1, 6)) if expired else took)
            # About a third sat in Kazakh -- the VIP's first one always, so the
            # demo account has a Kazakh result to open.
            kazakh = (plan.key == "vip" and n == 0) or rng.random() < 0.3
            language = EntLanguage.kk if kazakh else EntLanguage.ru
            sim = EntSimulation(student_id=student.id, is_timed=timed, duration_minutes=duration, language=language,
                                status=EntSimulationStatus.submitted, started_at=started,
                                expires_at=started + timedelta(minutes=duration) if timed else None,
                                submitted_at=submitted, time_expired=expired, created_at=started)
            db.add(sim)
            await db.flush()
            order, total, max_total = 0, 0, 0
            skill = min(0.97, plan.skill + rng.uniform(-0.08, 0.05))
            for sid in chosen:
                subject, by_language = bank[sid]
                questions = by_language[language]
                drawn = []
                for qtype, count in ((EntQuestionType.single, subject.single_choice_count), (EntQuestionType.multiple, subject.multiple_choice_count),
                                     (EntQuestionType.matching, subject.matching_count), (EntQuestionType.short_answer, subject.short_answer_count)):
                    drawn += rng.sample([q for q in questions if q.qtype == qtype], count)
                rng.shuffle(drawn)
                for q in drawn:
                    answer = ent_answer(q, rng.random() < skill, rng)
                    score = grade_question(q, answer)
                    db.add(EntSimulationQuestion(simulation_id=sim.id, question_id=q.id, order_index=order,
                                                 answer_data=answer, score_awarded=score))
                    order += 1
                    total += score
                    max_total += q.max_score
            xp = total + (total // 5 if timed and not expired else 0)
            sim.total_score, sim.max_score, sim.xp_earned = total, max_total, xp
            db.add(XpEvent(student_id=student.id, source=XpSource.ent.value, source_id=sim.id, xp=xp, created_at=submitted))
            ledger.add(student.id, xp)
            s = stats.setdefault(student.id, {"count": 0, "best": 0, "last": submitted})
            s["count"] += 1
            s["best"] = max(s["best"], total)
            s["last"] = max(s["last"], submitted)
    return stats


async def create_ratings_and_activity(db, plans, students, ledger: XpLedger, sim_stats):
    for plan in plans:
        student = students[plan.key]
        xp = ledger.total.get(student.id, 0)
        s = sim_stats.get(student.id)
        if xp or s:
            db.add(StudentRating(student_id=student.id, total_xp=xp, simulations_completed=s["count"] if s else 0,
                                 best_score=s["best"] if s else None, last_simulation_at=s["last"] if s else None))
        for back in range(7):
            minutes = plan.activity_minutes if back == 0 else max(0, plan.activity_minutes + (back * 7 % 23) - 10)
            if minutes:
                db.add(UserDailyActivity(user_id=student.id, date=date.today() - timedelta(days=back), total_seconds=minutes * 60))


# --- main -----------------------------------------------------------------------


def print_accounts(plans: list[StudentPlan]) -> None:
    rows = [(phone, DEMO_PASSWORD, {"admin": "Админ", "teacher": "Учитель"}[role.value], desc)
            for _, phone, _, _, role, desc in STAFF]
    rows += [(p.phone, DEMO_PASSWORD, "Ученик", p.note) for p in KEY_STUDENTS]
    w = [max(len(r[i]) for r in rows + [("Телефон", "Пароль", "Роль", "Доступ")]) for i in range(4)]
    line = "+" + "+".join("-" * (x + 2) for x in w) + "+"
    print(line)
    print("| " + " | ".join(h.ljust(w[i]) for i, h in enumerate(("Телефон", "Пароль", "Роль", "Доступ"))) + " |")
    print(line)
    for r in rows:
        print("| " + " | ".join(v.ljust(w[i]) for i, v in enumerate(r)) + " |")
    print(line)
    bg = [p for p in plans if p.key.startswith("bg")]
    print(f"Ещё {len(bg)} учеников для рейтинга: {bg[0].phone} … {bg[-1].phone}, тот же пароль.")


async def main() -> None:
    validate_content()
    rng = random.Random(RNG_SEED)
    async with async_session_factory() as db:
        print("1/8 Очистка базы (TRUNCATE … RESTART IDENTITY) и загрузок…")
        await reset_database(db)
        clear_uploads()
        print("2/8 Пользователи…")
        staff, plans, students = await create_people(db, rng)
        print("3/8 Курсы, уроки с YouTube, конспекты и тесты…")
        courses = await create_courses(db, staff)
        print("4/8 Банк ЕНТ: 5 предметов × 40 вопросов на русском и казахском…")
        bank = await create_ent_bank(db, staff)
        print("5/8 Заявки и уведомления…")
        await create_applications(db, plans, students, courses, staff, rng)
        ledger = XpLedger()
        print("6/8 Прохождение уроков и тестов разделов…")
        passed = await create_progress(db, plans, students, courses, ledger, rng)
        print("7/8 Домашние задания и симуляции ЕНТ…")
        await create_homework(db, plans, students, courses, passed, rng)
        sim_stats = await create_simulations(db, plans, students, bank, ledger, rng)
        print("8/8 Рейтинг и активность…")
        await create_ratings_and_activity(db, plans, students, ledger, sim_stats)
        await db.commit()
    lessons = sum(len(s["lessons"]) for c in COURSES for s in c["sections"])
    print(f"\nГотово: {len(COURSES)} курсов, {lessons} уроков, {sum(len(s['questions']) for s in SUBJECTS)} + {sum(len(s['questions_kk']) for s in SUBJECTS)} вопросов ЕНТ (рус. + каз.), "
          f"{len(plans) + len(STAFF)} пользователей.\n")
    print_accounts(plans)


def _guard_environment() -> None:
    if not settings.is_production:
        return
    if "--force-production" in sys.argv:
        print("ENV=production и --force-production: база будет полностью очищена.", file=sys.stderr)
        return
    print("ОТКАЗАНО: ENV=production. Скрипт удаляет все данные. Передайте --force-production, если уверены.", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    _guard_environment()
    asyncio.run(main())
