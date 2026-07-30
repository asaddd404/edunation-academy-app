"""Populates the database with realistic demo data for client presentations.

Idempotent: wipes every table this script owns (users, categories, courses,
ENT bank, applications, homework, simulations, ratings) and recreates them
from scratch, so it can be re-run safely at any time.

Run via Docker:
    docker compose exec backend python -m app.seed_demo_data
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import (
    AnswerVariant,
    Application,
    ApplicationStatusEnum,
    Category,
    Choice,
    EntAnswerVariant,
    EntChoice,
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
    User,
    teacher_categories,
)
from app.security import hash_password

RNG_SEED = 2026
DEMO_PASSWORD = "TestPass123"
ENT_SCALE_MAX = 140  # standard ENT total; simulation scores are rescaled onto this

SAMPLE_VIDEO_URLS = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/Sintel.mp4",
]

DESCRIPTION_TEMPLATES = [
    "На этом занятии подробно разбираем тему «{t}»: теория, примеры и разбор типовых заданий ЕНТ.",
    "Урок посвящён теме «{t}». Рассмотрим ключевые понятия, решим практические задачи и разберём частые ошибки.",
    "В этом видеоуроке изучаем «{t}» — от базовых определений до сложных примеров из реального ЕНТ.",
    "Погружаемся в тему «{t}»: пошаговый разбор теории и практика на реальных заданиях.",
]
HOMEWORK_TEMPLATES = [
    "Решите 8-10 задач по теме «{t}» из сборника, оформите решение в тетради и загрузите фото или текст ответа.",
    "Выполните практическое задание по теме «{t}»: разберите 5 примеров и опишите ход решения.",
    "Закрепите тему «{t}»: решите предложенные задачи и кратко опишите, какие трудности возникли.",
    "Домашнее задание по теме «{t}»: выполните тренировочный тест и приложите решения ключевых задач.",
]

ACCEPTED_FEEDBACK = [
    "Отличная работа! Продолжайте в том же духе.",
    "Отличная работа! Все задачи решены верно.",
    "Хорошо сделано, видно, что тема усвоена.",
    "Молодец! Небольшие недочёты в оформлении, но решение верное.",
]
REVISION_FEEDBACK = [
    "Переделай задачу №3 — там ошибка в вычислениях.",
    "Переделайте, пожалуйста, задачу №2, ответ не совпадает.",
    "Хорошее начало, но нужно исправить последний пример и отправить снова.",
    "Проверьте ход решения задачи №1, там неверно применена формула.",
]

MALE_FIRST_NAMES = [
    "Алихан", "Данияр", "Диас", "Ерасыл", "Нурсултан", "Азамат", "Бекзат", "Санжар",
    "Ануар", "Тимур", "Ерлан", "Максат", "Дамир", "Арман", "Асхат", "Бауыржан",
    "Ильяс", "Мирас", "Рустам", "Айдар", "Жандос", "Куаныш", "Нурлан", "Дархан", "Асет",
]
FEMALE_FIRST_NAMES = [
    "Амина", "Мадина", "Айгерим", "Диана", "Аружан", "Дана", "Сабина", "Жанна",
    "Гульнур", "Асель", "Алия", "Инкар", "Камила", "Айым", "Меруерт", "Дильназ",
    "Айзере", "Салтанат", "Гаухар", "Жасмин", "Малика", "Томирис", "Нургуль", "Аяна", "Балжан",
]
SURNAME_PAIRS = [
    ("Нурланов", "Нурланова"), ("Ахметов", "Ахметова"), ("Оспанов", "Оспанова"),
    ("Смагулов", "Смагулова"), ("Байжанов", "Байжанова"), ("Жумабаев", "Жумабаева"),
    ("Касымов", "Касымова"), ("Тлеубердиев", "Тлеубердиева"), ("Сатыбалдиев", "Сатыбалдиева"),
    ("Абенов", "Абенова"), ("Ержанов", "Ержанова"), ("Муратов", "Муратова"),
    ("Дюсенов", "Дюсенова"), ("Салыков", "Салыкова"), ("Искаков", "Искакова"),
    ("Бекенов", "Бекенова"), ("Тастанов", "Тастанова"), ("Кенжебаев", "Кенжебаева"),
    ("Мухаметжанов", "Мухаметжанова"), ("Даулетов", "Даулетова"), ("Сериков", "Серикова"),
    ("Толегенов", "Толегенова"), ("Райымбеков", "Райымбекова"), ("Нурпейсов", "Нурпейсова"),
    ("Сагындыков", "Сагындыкова"),
]


# ---------------------------------------------------------------------------
# Question-bank helpers
# ---------------------------------------------------------------------------

def q_single(text, options, correct_index, max_score=1):
    return {
        "qtype": EntQuestionType.single,
        "text": text,
        "max_score": max_score,
        "choices": [(opt, i == correct_index) for i, opt in enumerate(options)],
    }


def q_multiple(text, options, correct_indices, max_score=2):
    return {
        "qtype": EntQuestionType.multiple,
        "text": text,
        "max_score": max_score,
        "choices": [(opt, i in correct_indices) for i, opt in enumerate(options)],
    }


def q_matching(text, pairs, max_score=2):
    return {"qtype": EntQuestionType.matching, "text": text, "max_score": max_score, "pairs": pairs}


def q_short(text, variants, max_score=1):
    return {"qtype": EntQuestionType.short_answer, "text": text, "max_score": max_score, "variants": variants}


def build_question(question_cls, choice_cls, pair_cls, variant_cls, spec, order_index, **owner):
    q = question_cls(
        qtype=spec["qtype"], text=spec["text"], max_score=spec["max_score"], order_index=order_index, **owner
    )
    if spec["qtype"] in (EntQuestionType.single, EntQuestionType.multiple):
        q.choices = [choice_cls(text=t, is_correct=c, order_index=i) for i, (t, c) in enumerate(spec["choices"])]
    elif spec["qtype"] == EntQuestionType.matching:
        q.match_pairs = [pair_cls(prompt_text=p, answer_text=a, order_index=i) for i, (p, a) in enumerate(spec["pairs"])]
    else:
        q.answer_variants = [variant_cls(text=v) for v in spec["variants"]]
    return q


def build_course_question(spec, order_index, **owner):
    return build_question(Question, Choice, MatchPair, AnswerVariant, spec, order_index, **owner)


def build_ent_question(spec, order_index, **owner):
    return build_question(EntQuestion, EntChoice, EntMatchPair, EntAnswerVariant, spec, order_index, **owner)


class PoolCycler:
    """Yields items from a pool in shuffled order, reshuffling once exhausted
    so nearby draws rarely repeat the same question."""

    def __init__(self, pool, rng):
        self.pool = pool
        self.rng = rng
        self._order: list[int] = []

    def next(self):
        if not self._order:
            self._order = list(range(len(self.pool)))
            self.rng.shuffle(self._order)
        return self.pool[self._order.pop()]


# ---------------------------------------------------------------------------
# ENT subject question banks (also reused for course lesson/section tests)
# ---------------------------------------------------------------------------

MATH_POOL = [
    q_single("Чему равен корень уравнения 2x + 6 = 0?", ["-3", "3", "-2", "2"], 0),
    q_single("Найдите значение выражения 3² + 4²", ["25", "7", "12", "49"], 0),
    q_single("Решите неравенство x - 5 > 0", ["x>5", "x<5", "x≥5", "x=5"], 0),
    q_multiple("Какие из чисел являются простыми?", ["2", "4", "7", "9", "11"], [0, 2, 4]),
    q_single("Чему равна площадь квадрата со стороной 6 см?", ["36 см²", "12 см²", "24 см²", "18 см²"], 0),
    q_single("Найдите производную функции f(x)=x²", ["2x", "x", "2", "x²"], 0),
    q_matching(
        "Сопоставьте функцию с типом её графика",
        [("y=kx", "прямая линия"), ("y=x²", "парабола"), ("y=k/x", "гипербола"), ("y=√x", "ветвь параболы")],
    ),
    q_short("Чему равен log₂8? (число)", ["3"]),
    q_single("Какое из чисел является иррациональным?", ["√2", "4", "0.5", "1/3"], 0),
    q_multiple(
        "Выберите верные свойства арифметической прогрессии",
        ["Разность постоянна", "Отношение соседних членов постоянно", "Может быть возрастающей", "Является геометрической"],
        [0, 2],
    ),
    q_single("Чему равен синус 90°?", ["1", "0", "-1", "0.5"], 0),
    q_short("Решите уравнение x² = 49. Укажите положительный корень.", ["7"]),
    q_single(
        "Сколько решений имеет уравнение x²+1=0 на множестве действительных чисел?",
        ["0", "1", "2", "бесконечно много"], 0,
    ),
    q_matching(
        "Сопоставьте геометрическую фигуру с формулой площади",
        [("Круг", "πr²"), ("Треугольник", "½·a·h"), ("Прямоугольник", "a·b"), ("Трапеция", "½(a+b)·h")],
    ),
    q_single("Найдите значение выражения (2+3)×4", ["20", "14", "24", "9"], 0),
]

PHYSICS_POOL = [
    q_single("Чему равно ускорение свободного падения (округлённо)?", ["9.8 м/с²", "3.8 м/с²", "10.8 м/с²", "1 м/с²"], 0),
    q_single(
        "Первый закон Ньютона также называют законом:",
        ["Инерции", "Всемирного тяготения", "Сохранения энергии", "Действия и противодействия"], 0,
    ),
    q_short("Чему равна скорость света в вакууме, км/с (округлённо, тыс.)?", ["300000", "3*10^5", "3×10^5"]),
    q_single("Единица измерения силы в СИ:", ["Ньютон", "Джоуль", "Ватт", "Паскаль"], 0),
    q_multiple("Какие величины являются векторными?", ["Скорость", "Масса", "Сила", "Температура", "Ускорение"], [0, 2, 4]),
    q_single("Формула второго закона Ньютона:", ["F=ma", "F=mg", "E=mc²", "p=mv"], 0),
    q_matching(
        "Сопоставьте физическую величину с единицей измерения",
        [("Сила", "Ньютон"), ("Работа", "Джоуль"), ("Мощность", "Ватт"), ("Давление", "Паскаль")],
    ),
    q_single(
        "Как называется явление сохранения скорости тела при отсутствии внешних сил?",
        ["Инерция", "Гравитация", "Трение", "Резонанс"], 0,
    ),
    q_single(
        "Что происходит с давлением газа при увеличении температуры (объём постоянен)?",
        ["Увеличивается", "Уменьшается", "Не изменяется", "Становится равным нулю"], 0,
    ),
    q_multiple(
        "Какие из перечисленных являются агрегатными состояниями вещества?",
        ["Твёрдое", "Жидкое", "Газообразное", "Кристаллическое", "Плазма"], [0, 1, 2, 4],
    ),
    q_short("Как называется процесс перехода вещества из жидкого состояния в газообразное?", ["испарение", "парообразование"]),
    q_single(
        "Закон сохранения энергии гласит, что энергия:",
        ["Не исчезает и не создаётся, а переходит из одной формы в другую", "Всегда увеличивается",
         "Всегда уменьшается", "Существует только в виде тепла"], 0,
    ),
    q_matching(
        "Сопоставьте раздел физики с изучаемым явлением",
        [("Механика", "Движение тел"), ("Термодинамика", "Тепловые процессы"),
         ("Электродинамика", "Электрические и магнитные поля"), ("Оптика", "Свет")],
    ),
    q_single("Что измеряет амперметр?", ["Силу тока", "Напряжение", "Сопротивление", "Мощность"], 0),
    q_single("Чему равна масса тела, если его вес на Земле 100 Н (g=10 м/с²)?", ["10 кг", "100 кг", "1000 кг", "1 кг"], 0),
]

CHEMISTRY_POOL = [
    q_single("Сколько протонов в ядре атома водорода?", ["1", "2", "0", "3"], 0),
    q_single("Химическая формула воды:", ["H2O", "CO2", "NaCl", "O2"], 0),
    q_multiple("Какие из веществ являются кислотами?", ["HCl", "H2SO4", "NaOH", "HNO3", "KCl"], [0, 1, 3]),
    q_single(
        "Как называется наименьшая частица химического элемента, сохраняющая его свойства?",
        ["Атом", "Молекула", "Ион", "Электрон"], 0,
    ),
    q_matching(
        "Сопоставьте класс соединений с примером",
        [("Оксид", "CO2"), ("Кислота", "H2SO4"), ("Основание", "NaOH"), ("Соль", "NaCl")],
    ),
    q_single("Сколько элементов расположено в первом периоде таблицы Менделеева?", ["2", "8", "18", "32"], 0),
    q_short("Какой газ выделяется при взаимодействии металлов с кислотами?", ["водород", "H2"]),
    q_single("Валентность кислорода в большинстве соединений:", ["2", "1", "3", "4"], 0),
    q_single(
        "Реакция нейтрализации происходит между:",
        ["Кислотой и основанием", "Двумя кислотами", "Двумя основаниями", "Металлом и неметаллом"], 0,
    ),
    q_multiple("Какие из перечисленных являются щелочными металлами?", ["Li", "Na", "K", "Ca", "Mg"], [0, 1, 2]),
    q_single("Формула поваренной соли:", ["NaCl", "KCl", "CaCl2", "NaOH"], 0),
    q_matching(
        "Сопоставьте элемент с его символом",
        [("Углерод", "C"), ("Азот", "N"), ("Кислород", "O"), ("Железо", "Fe")],
    ),
    q_short("Сколько атомов кислорода в формуле H2O?", ["1"]),
    q_single(
        "Тип химической связи в молекуле NaCl:",
        ["Ионная", "Ковалентная неполярная", "Ковалентная полярная", "Металлическая"], 0,
    ),
    q_single(
        "Какой класс органических соединений содержит функциональную группу –OH?",
        ["Спирты", "Альдегиды", "Кислоты", "Амины"], 0,
    ),
]

HISTORY_POOL = [
    q_single("В каком году была принята Конституция Республики Казахстан?", ["1995", "1991", "1993", "2000"], 0),
    q_single(
        "Столица Казахстана в настоящее время называется:",
        ["Астана", "Алматы", "Целиноград", "Акмола"], 0,
    ),
    q_single(
        "Кто является автором книги «Слова назидания» (Қара сөздер)?",
        ["Абай Кунанбаев", "Шокан Уалиханов", "Ыбырай Алтынсарин", "Магжан Жумабаев"], 0,
    ),
    q_multiple(
        "Какие ханства существовали на территории Казахстана в XV-XVI веках?",
        ["Казахское ханство", "Ногайская Орда", "Сибирское ханство", "Османская империя", "Джунгарское ханство"],
        [0, 1, 2, 4],
    ),
    q_single("В каком году была провозглашена независимость Республики Казахстан?", ["1991", "1990", "1986", "1993"], 0),
    q_short("Назовите год образования Казахского ханства.", ["1465", "1465 год"]),
    q_matching(
        "Сопоставьте историческую личность с её деятельностью",
        [("Абылай хан", "Объединение казахских жузов"), ("Кенесары Касымов", "Национально-освободительное восстание"),
         ("Динмухамед Кунаев", "Руководитель Казахской ССР"), ("Нурсултан Назарбаев", "Первый Президент РК")],
    ),
    q_single("Событие «Желтоксан» (Декабрьские события) произошло в:", ["1986 году", "1991 году", "1979 году", "2001 году"], 0),
    q_single(
        "Первый Президент Республики Казахстан:",
        ["Нурсултан Назарбаев", "Касым-Жомарт Токаев", "Динмухамед Кунаев", "Кенесары Касымов"], 0,
    ),
    q_multiple(
        "Какие жузы входят в традиционное деление казахских земель?",
        ["Старший жуз", "Средний жуз", "Младший жуз", "Восточный жуз", "Северный жуз"], [0, 1, 2],
    ),
    q_single(
        "Национально-освободительное восстание 1916 года было направлено против:",
        ["Мобилизации на тыловые работы Российской империи", "Коллективизации", "Целинной кампании", "Продразвёрстки"], 0,
    ),
    q_matching(
        "Сопоставьте период с историческим событием",
        [("1920-е", "Образование Казахской АССР"), ("1930-е", "Коллективизация и голод"),
         ("1950-е", "Освоение целины"), ("1990-е", "Обретение независимости")],
    ),
    q_short("В каком году Казахстан вступил в ООН?", ["1992"]),
    q_single(
        "Кто из казахских ханов известен как объединитель трёх жузов в XVIII веке?",
        ["Абылай хан", "Тауке хан", "Есим хан", "Абулхаир хан"], 0,
    ),
    q_single(
        "Голод в Казахстане в начале 1930-х годов связан с:",
        ["Насильственной коллективизацией", "Целинной кампанией", "Гражданской войной", "Второй мировой войной"], 0,
    ),
]

MATH_LITERACY_POOL = [
    q_single(
        "В магазине скидка 20% на товар стоимостью 5000 тенге. Сколько будет стоить товар со скидкой?",
        ["4000 тенге", "4500 тенге", "3500 тенге", "4800 тенге"], 0,
    ),
    q_single(
        "Автомобиль едет со скоростью 60 км/ч. Сколько километров он проедет за 2.5 часа?",
        ["150 км", "120 км", "135 км", "100 км"], 0,
    ),
    q_short("У Айгерим было 3500 тенге. Она потратила 1200 тенге. Сколько тенге у неё осталось?", ["2300"]),
    q_single("Курс доллара 480 тенге. Сколько тенге стоят 50 долларов?", ["24000 тенге", "480 тенге", "2400 тенге", "48000 тенге"], 0),
    q_multiple(
        "Какие из следующих утверждений верны для процентов?",
        ["50% равно половине", "25% равно четверти", "100% равно всей величине", "10% всегда равно 10 единицам", "1% равен одной сотой"],
        [0, 1, 2, 4],
    ),
    q_single("В классе 30 учеников, из них 40% — мальчики. Сколько девочек в классе?", ["18", "12", "15", "20"], 0),
    q_matching(
        "Сопоставьте дробь с её процентным значением",
        [("1/2", "50%"), ("1/4", "25%"), ("3/4", "75%"), ("1/5", "20%")],
    ),
    q_single("Если 1 кг яблок стоит 600 тенге, сколько будут стоить 3.5 кг?", ["2100 тенге", "1800 тенге", "2400 тенге", "1500 тенге"], 0),
    q_short("Периметр прямоугольника со сторонами 5 см и 8 см равен? (см)", ["26"]),
    q_single(
        "Продажи выросли со 100 до 150 единиц. Какой вывод верен?",
        ["Продажи выросли на 50%", "Продажи выросли на 100%", "Продажи выросли на 15%", "Продажи не изменились"], 0,
    ),
    q_single("Средний балл ученика по 5 предметам: 4,5,3,5,4. Чему равен средний балл?", ["4.2", "4", "4.5", "3.8"], 0),
    q_multiple("Какие единицы измерения используются для измерения площади?", ["м²", "км²", "см²", "кг", "литр"], [0, 1, 2]),
    q_matching(
        "Сопоставьте единицу измерения с величиной",
        [("Километр", "Расстояние"), ("Килограмм", "Масса"), ("Секунда", "Время"), ("Литр", "Объём")],
    ),
    q_short("Поезд прошёл 240 км за 4 часа. Какова его средняя скорость, км/ч?", ["60"]),
    q_single("Товар подорожал с 2000 до 2400 тенге. На сколько процентов выросла цена?", ["20%", "40%", "10%", "25%"], 0),
]

BIOLOGY_POOL = [
    q_single(
        "Основной структурной и функциональной единицей живого организма является:",
        ["Клетка", "Ткань", "Орган", "Система органов"], 0,
    ),
    q_single("Процесс деления соматических клеток называется:", ["Митоз", "Мейоз", "Оплодотворение", "Транскрипция"], 0),
    q_multiple(
        "Какие органоиды клетки участвуют в производстве энергии?",
        ["Митохондрии", "Хлоропласты", "Рибосомы", "Лизосомы", "Ядро"], [0, 1],
    ),
    q_single(
        "Наука, изучающая наследственность и изменчивость организмов:",
        ["Генетика", "Экология", "Цитология", "Систематика"], 0,
    ),
    q_matching(
        "Сопоставьте органоид клетки с его функцией",
        [("Митохондрия", "Синтез АТФ"), ("Рибосома", "Синтез белка"),
         ("Ядро", "Хранение генетической информации"), ("Хлоропласт", "Фотосинтез")],
    ),
    q_short("Кто сформулировал законы наследственности, изучая горох?", ["Мендель", "Грегор Мендель"]),
    q_single(
        "Какой процесс лежит в основе эволюции по Дарвину?",
        ["Естественный отбор", "Мутагенез", "Партеногенез", "Регенерация"], 0,
    ),
    q_single("Молекула, хранящая наследственную информацию:", ["ДНК", "АТФ", "РНК", "Белок"], 0),
    q_multiple(
        "Какие из перечисленных являются царствами живой природы?",
        ["Животные", "Растения", "Грибы", "Минералы", "Бактерии"], [0, 1, 2, 4],
    ),
    q_short(
        "Как называется процесс образования половых клеток с уменьшением числа хромосом вдвое?",
        ["мейоз"],
    ),
    q_single("Обмен веществ и энергии в организме называется:", ["Метаболизм", "Катализ", "Фотосинтез", "Диффузия"], 0),
    q_matching(
        "Сопоставьте систему органов с её функцией",
        [("Кровеносная", "Транспорт веществ"), ("Дыхательная", "Газообмен"),
         ("Пищеварительная", "Расщепление пищи"), ("Нервная", "Регуляция и координация")],
    ),
]

ENT_SUBJECTS = [
    ("Математика", "matematika", MATH_POOL),
    ("Физика", "fizika", PHYSICS_POOL),
    ("Химия", "himiya", CHEMISTRY_POOL),
    ("История Казахстана", "istoriya-kazahstana", HISTORY_POOL),
    ("Математическая грамотность", "matematicheskaya-gramotnost", MATH_LITERACY_POOL),
]

# ---------------------------------------------------------------------------
# Course structure
# ---------------------------------------------------------------------------

COURSES = [
    {
        "name": "Математика: Подготовка к ЕНТ 2026",
        "slug": "matematika-ent-2026",
        "description": "Полный курс подготовки к ЕНТ по математике: от базовых уравнений до сложных задач профильного уровня.",
        "teacher": "math",
        "pool": MATH_POOL,
        "sections": [
            {"title": "Алгебраические выражения и уравнения",
             "lessons": ["Линейные уравнения", "Квадратные уравнения", "Системы уравнений", "Неравенства"]},
            {"title": "Функции и графики",
             "lessons": ["Линейная функция", "Квадратичная функция", "Исследование функций"]},
            {"title": "Планиметрия",
             "lessons": ["Треугольники", "Четырёхугольники", "Окружность", "Площади фигур"]},
        ],
    },
    {
        "name": "Химия: С нуля до 40+ баллов",
        "slug": "himiya-s-nulya",
        "description": "Курс химии для тех, кто начинает с нуля и хочет набрать 40+ баллов на ЕНТ.",
        "teacher": "chem",
        "pool": CHEMISTRY_POOL,
        "sections": [
            {"title": "Основы химии", "lessons": ["Строение атома", "Периодический закон Менделеева", "Химическая связь"]},
            {"title": "Неорганическая химия",
             "lessons": ["Оксиды", "Кислоты", "Основания и соли", "Реакции ионного обмена"]},
            {"title": "Органическая химия", "lessons": ["Алканы и алкены", "Спирты и кислоты", "Полимеры"]},
        ],
    },
    {
        "name": "Физика: Механика и Молекулярная физика",
        "slug": "fizika-mehanika",
        "description": "Механика и молекулярная физика — разбор теории и практики для успешной сдачи ЕНТ.",
        "teacher": "math",
        "pool": PHYSICS_POOL,
        "sections": [
            {"title": "Механика",
             "lessons": ["Кинематика", "Динамика. Законы Ньютона", "Законы сохранения", "Статика и гидростатика"]},
            {"title": "Молекулярная физика и термодинамика",
             "lessons": ["МКТ. Уравнение состояния", "Термодинамика", "Агрегатные состояния вещества"]},
        ],
    },
    {
        "name": "Биология: Подготовка к ЕНТ",
        "slug": "biologiya-ent",
        "description": "Подготовка к ЕНТ по биологии: клетка, генетика, эволюция и не только.",
        "teacher": "chem",
        "pool": BIOLOGY_POOL,
        "sections": [
            {"title": "Клетка и организм", "lessons": ["Строение клетки", "Обмен веществ", "Деление клетки"]},
            {"title": "Генетика и эволюция", "lessons": ["Основы генетики", "Законы Менделя", "Теория эволюции"]},
        ],
    },
]


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------

async def wipe(db: AsyncSession) -> None:
    for model in [
        EntSimulationQuestion, EntSimulation, StudentRating, HomeworkSubmission, TestAttempt,
        Choice, MatchPair, AnswerVariant, Question,
        EntChoice, EntMatchPair, EntAnswerVariant, EntQuestion,
        EntSubject, Application, Notification, Lesson, Section,
    ]:
        await db.execute(delete(model))
    await db.execute(delete(teacher_categories))
    await db.execute(delete(Category))
    await db.execute(delete(User))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def create_users(db: AsyncSession, rng: random.Random) -> tuple[dict[str, User], User, list[User]]:
    pw_hash = hash_password(DEMO_PASSWORD)

    teachers = {
        "math": User(
            phone="+77002223344", password_hash=pw_hash, first_name="Ерлан", last_name="Жумабаев",
            role=RoleEnum.teacher,
        ),
        "chem": User(
            phone="+77002223355", password_hash=pw_hash, first_name="Гульнара", last_name="Ахметова",
            role=RoleEnum.teacher,
        ),
    }
    admin = User(
        phone="+77001112233", password_hash=pw_hash, first_name="Асан", last_name="Байжанов",
        role=RoleEnum.admin,
    )
    db.add_all([*teachers.values(), admin])

    students_data = [(name, SURNAME_PAIRS[i][0]) for i, name in enumerate(MALE_FIRST_NAMES)]
    students_data += [(name, SURNAME_PAIRS[i][1]) for i, name in enumerate(FEMALE_FIRST_NAMES)]
    rng.shuffle(students_data)

    students = []
    for i, (first_name, last_name) in enumerate(students_data, start=1):
        phone = f"+770700000{i:02d}"
        students.append(User(phone=phone, password_hash=pw_hash, first_name=first_name, last_name=last_name, role=RoleEnum.student))
    db.add_all(students)

    await db.flush()
    return teachers, admin, students


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

async def create_courses(db: AsyncSession, teachers: dict[str, User], rng: random.Random) -> list[dict]:
    course_records = []
    for course in COURSES:
        category = Category(name=course["name"], slug=course["slug"], description=course["description"])
        db.add(category)
        await db.flush()

        teacher = teachers[course["teacher"]]
        await db.execute(insert(teacher_categories).values(teacher_id=teacher.id, category_id=category.id))

        cycler = PoolCycler(course["pool"], rng)
        lessons: list[Lesson] = []

        for s_idx, section_spec in enumerate(course["sections"]):
            section = Section(category_id=category.id, title=section_spec["title"], order_index=s_idx)
            db.add(section)
            await db.flush()

            for l_idx, lesson_title in enumerate(section_spec["lessons"]):
                lesson = Lesson(
                    section_id=section.id,
                    title=lesson_title,
                    description=rng.choice(DESCRIPTION_TEMPLATES).format(t=lesson_title),
                    video_url=rng.choice(SAMPLE_VIDEO_URLS),
                    homework_assignment=rng.choice(HOMEWORK_TEMPLATES).format(t=lesson_title),
                    order_index=l_idx,
                )
                db.add(lesson)
                await db.flush()
                lessons.append(lesson)

                for q_idx in range(2):
                    db.add(build_course_question(cycler.next(), q_idx, lesson_id=lesson.id))

            for q_idx in range(4):
                db.add(build_course_question(cycler.next(), q_idx, section_id=section.id))

        course_records.append({"category": category, "lessons": lessons})

    await db.flush()
    return course_records


# ---------------------------------------------------------------------------
# ENT subjects & question bank
# ---------------------------------------------------------------------------

async def create_ent_bank(db: AsyncSession, teachers: dict[str, User], admin: User) -> dict[str, list[EntQuestion]]:
    creator_by_slug = {
        "matematika": teachers["math"],
        "fizika": teachers["math"],
        "matematicheskaya-gramotnost": teachers["math"],
        "himiya": teachers["chem"],
        "istoriya-kazahstana": admin,
    }
    questions_by_subject: dict[str, list[EntQuestion]] = {}

    for name, slug, pool in ENT_SUBJECTS:
        subject = EntSubject(name=name, slug=slug, created_by_id=creator_by_slug[slug].id)
        db.add(subject)
        await db.flush()

        subject_questions = []
        for order_index, spec in enumerate(pool):
            eq = build_ent_question(spec, order_index, subject_id=subject.id, created_by_id=creator_by_slug[slug].id)
            db.add(eq)
            subject_questions.append(eq)
        questions_by_subject[slug] = subject_questions

    await db.flush()
    return questions_by_subject


# ---------------------------------------------------------------------------
# Course applications
# ---------------------------------------------------------------------------

async def create_applications(
    db: AsyncSession, students: list[User], course_records: list[dict], teachers: dict[str, User], rng: random.Random
) -> dict[str, list[User]]:
    now = datetime.now(timezone.utc)
    approved_students = students[0:20]
    pending_students = students[20:26]
    rejected_students = students[26:30]

    teacher_by_category_id = {}
    for course, record in zip(COURSES, course_records):
        teacher_by_category_id[record["category"].id] = teachers[course["teacher"]]

    categories = [r["category"] for r in course_records]

    for i, student in enumerate(approved_students):
        category = categories[i % len(categories)]
        teacher = teacher_by_category_id[category.id]
        decided_at = now - timedelta(days=rng.randint(3, 90))
        db.add(Application(
            student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved,
            decided_by=teacher.id, decided_at=decided_at, created_at=decided_at - timedelta(days=1),
        ))

    for student in pending_students:
        category = rng.choice(categories)
        db.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.pending))

    for student in rejected_students:
        category = rng.choice(categories)
        teacher = teacher_by_category_id[category.id]
        decided_at = now - timedelta(days=rng.randint(3, 60))
        db.add(Application(
            student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.rejected,
            decided_by=teacher.id, decided_at=decided_at, created_at=decided_at - timedelta(days=1),
        ))

    await db.flush()
    return {
        "approved": approved_students,
        "pending": pending_students,
        "rejected": rejected_students,
    }


# ---------------------------------------------------------------------------
# Homework submissions
# ---------------------------------------------------------------------------

async def create_homework_submissions(
    db: AsyncSession, approved_students: list[User], course_records: list[dict],
    teachers: dict[str, User], rng: random.Random,
) -> None:
    now = datetime.now(timezone.utc)
    teacher_by_category_id = {}
    for course, record in zip(COURSES, course_records):
        teacher_by_category_id[record["category"].id] = teachers[course["teacher"]]

    # Pair each of the 20 approved students with a lesson from their course.
    pairs = []
    for i, student in enumerate(approved_students):
        record = course_records[i % len(course_records)]
        lesson = rng.choice(record["lessons"])
        pairs.append((student, lesson, record["category"].id))

    statuses = (
        [HomeworkStatusEnum.accepted] * 8
        + [HomeworkStatusEnum.revision_requested] * 4
        + [HomeworkStatusEnum.submitted] * 6
    )
    rng.shuffle(statuses)

    for (student, lesson, category_id), status in zip(pairs, statuses):
        created_at = now - timedelta(days=rng.randint(1, 30))
        submission = HomeworkSubmission(
            lesson_id=lesson.id,
            student_id=student.id,
            text_answer=f"Решение домашнего задания по теме «{lesson.title}»: выполнил(а) все предложенные задачи, ответы приложены ниже.",
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )
        if status in (HomeworkStatusEnum.accepted, HomeworkStatusEnum.revision_requested):
            teacher = teacher_by_category_id[category_id]
            submission.teacher_feedback = rng.choice(
                ACCEPTED_FEEDBACK if status == HomeworkStatusEnum.accepted else REVISION_FEEDBACK
            )
            submission.reviewed_by = teacher.id
            submission.reviewed_at = created_at + timedelta(hours=rng.randint(2, 48))
            submission.updated_at = submission.reviewed_at
        db.add(submission)


# ---------------------------------------------------------------------------
# ENT simulations, XP & leaderboard
# ---------------------------------------------------------------------------

def _answer_for(question: EntQuestion, correct_roll: bool, rng: random.Random) -> tuple[int, dict]:
    if question.qtype == EntQuestionType.single:
        correct_choice = next(c for c in question.choices if c.is_correct)
        if correct_roll:
            chosen = correct_choice
        else:
            wrong = [c for c in question.choices if not c.is_correct] or question.choices
            chosen = rng.choice(wrong)
        awarded = question.max_score if chosen.id == correct_choice.id else 0
        return awarded, {"choice_id": chosen.id}

    if question.qtype == EntQuestionType.multiple:
        correct_ids = {c.id for c in question.choices if c.is_correct}
        if correct_roll:
            chosen_ids = set(correct_ids)
        else:
            pool = [c.id for c in question.choices]
            k = rng.randint(1, max(1, len(pool) - 1))
            chosen_ids = set(rng.sample(pool, k))
        awarded = question.max_score if chosen_ids == correct_ids else (1 if chosen_ids & correct_ids else 0)
        return awarded, {"choice_ids": sorted(chosen_ids)}

    if question.qtype == EntQuestionType.matching:
        pair_ids = [p.id for p in question.match_pairs]
        if correct_roll:
            mapping = {str(pid): pid for pid in pair_ids}
            awarded = question.max_score
        else:
            shuffled = pair_ids[:]
            rng.shuffle(shuffled)
            mapping = {str(pid): aid for pid, aid in zip(pair_ids, shuffled)}
            correct_count = sum(1 for pid, aid in zip(pair_ids, shuffled) if pid == aid)
            awarded = question.max_score if correct_count == len(pair_ids) else (1 if correct_count > 0 else 0)
        return awarded, {"matches": mapping}

    # short_answer
    variant = question.answer_variants[0]
    if correct_roll:
        return question.max_score, {"text": variant.text}
    return 0, {"text": "не знаю"}


def create_simulation(
    db: AsyncSession, student_id: int, skill: float, rng: random.Random,
    all_questions: list[EntQuestion], now: datetime,
) -> EntSimulation:
    sample_size = rng.randint(20, min(45, len(all_questions)))
    items = rng.sample(all_questions, sample_size)

    is_timed = rng.random() < 0.7
    time_expired = is_timed and rng.random() < 0.1
    duration_minutes = 180 if is_timed else None
    submitted_at = now - timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 23))
    started_at = submitted_at - timedelta(minutes=rng.randint(20, duration_minutes or 150))

    sim = EntSimulation(
        student_id=student_id,
        is_timed=is_timed,
        duration_minutes=duration_minutes,
        status=EntSimulationStatus.submitted,
        started_at=started_at,
        expires_at=(started_at + timedelta(minutes=duration_minutes)) if is_timed else None,
        submitted_at=submitted_at,
        time_expired=time_expired,
    )

    raw_score = 0
    raw_max = 0
    sim_items = []
    for order_index, question in enumerate(items):
        raw_max += question.max_score
        correct_roll = rng.random() < skill
        awarded, answer_data = _answer_for(question, correct_roll, rng)
        raw_score += awarded
        sim_items.append(EntSimulationQuestion(
            question_id=question.id, order_index=order_index, answer_data=answer_data, score_awarded=awarded,
        ))

    # Rescale onto the standard 140-point ENT total (rather than the smaller
    # sum of the sampled subset's max_score) so headline scores/XP land in a
    # realistic, demo-worthy range instead of being capped by the bank size.
    ratio = raw_score / raw_max if raw_max else 0
    total_score = max(15, min(135, round(ratio * ENT_SCALE_MAX)))

    sim.total_score = total_score
    sim.max_score = ENT_SCALE_MAX
    bonus = total_score // 5 if is_timed and not time_expired else 0
    sim.xp_earned = total_score + bonus
    sim.items = sim_items
    db.add(sim)
    return sim


async def create_ent_simulations(
    db: AsyncSession, students: list[User], approved_students: list[User],
    questions_by_subject: dict[str, list[EntQuestion]], rng: random.Random,
) -> None:
    now = datetime.now(timezone.utc)
    all_questions = [q for qs in questions_by_subject.values() for q in qs]

    remaining = [s for s in students if s not in approved_students]
    sim_students = list(approved_students) + rng.sample(remaining, min(22, len(remaining)))
    star_ids = {s.id for s in approved_students[:3]}

    ratings: dict[int, dict] = {}

    def record(sim: EntSimulation) -> None:
        r = ratings.setdefault(sim.student_id, {"total_xp": 0, "count": 0, "best": 0, "last_at": sim.submitted_at})
        r["total_xp"] += sim.xp_earned
        r["count"] += 1
        r["best"] = max(r["best"], sim.total_score)
        if sim.submitted_at > r["last_at"]:
            r["last_at"] = sim.submitted_at

    for student in sim_students:
        is_star = student.id in star_ids
        n_sims = rng.randint(5, 8) if is_star else rng.randint(1, 4)
        skill_floor, skill_span = (0.85, 0.13) if is_star else (0.3, 0.55)
        for _ in range(n_sims):
            skill = min(0.98, skill_floor + rng.random() * skill_span)
            sim = create_simulation(db, student.id, skill, rng, all_questions, now)
            record(sim)

    # Guarantee the 3 "star" students clearly top the leaderboard.
    non_star_max = max((r["total_xp"] for sid, r in ratings.items() if sid not in star_ids), default=0)
    for sid in star_ids:
        attempts = 0
        while ratings[sid]["total_xp"] <= non_star_max + 50 and attempts < 5:
            sim = create_simulation(db, sid, 0.97, rng, all_questions, now)
            record(sim)
            attempts += 1

    for student_id, r in ratings.items():
        db.add(StudentRating(
            student_id=student_id, total_xp=r["total_xp"], simulations_completed=r["count"],
            best_score=r["best"], last_simulation_at=r["last_at"],
        ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    rng = random.Random(RNG_SEED)
    async with async_session_factory() as db:
        print("Wiping existing demo data...")
        await wipe(db)

        print("Creating teachers, admin and 50 students...")
        teachers, admin, students = await create_users(db, rng)

        print("Creating courses, sections, lessons, mini-tests and section tests...")
        course_records = await create_courses(db, teachers, rng)

        print("Creating ENT subjects and question bank...")
        questions_by_subject = await create_ent_bank(db, teachers, admin)

        print("Creating course applications...")
        application_groups = await create_applications(db, students, course_records, teachers, rng)

        print("Creating homework submissions...")
        await create_homework_submissions(db, application_groups["approved"], course_records, teachers, rng)

        print("Creating ENT simulations, XP and leaderboard...")
        await create_ent_simulations(db, students, application_groups["approved"], questions_by_subject, rng)

        await db.commit()
        print("Demo data seeded successfully.")
        print(f"  Teachers: {len(teachers)}, Admin: 1, Students: {len(students)}")
        print(f"  Courses: {len(course_records)}")
        print(f"  ENT subjects: {len(questions_by_subject)}")
        print(f"  Applications: {len(application_groups['approved']) + len(application_groups['pending']) + len(application_groups['rejected'])}")


if __name__ == "__main__":
    asyncio.run(main())
