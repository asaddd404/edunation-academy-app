<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { getTeacherToday } from "@/api/teacherToday";
import PageContainer from "@/components/layout/PageContainer.vue";
import TeacherTour, { type TourStep } from "@/components/teacher/TeacherTour.vue";
import { useAuthStore } from "@/stores/auth";
import { useTeacherHelpStore } from "@/stores/teacherHelp";
import type { TeacherToday } from "@/types/teacherToday";
import { describeApiError } from "@/utils/apiError";
import { pluralRu } from "@/utils/subjectTheme";

/**
 * «Сегодня» -- the teacher's start page. Instead of a menu of sections it
 * answers one question: what needs me today? Each card says what happened
 * in plain words and has one button that goes straight to the work.
 */
const auth = useAuthStore();
const help = useTeacherHelpStore();

const data = ref<TeacherToday | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    data.value = await getTeacherToday();
  } catch (e) {
    error.value = describeApiError(e, "Не удалось загрузить страницу.");
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await load();
  if (data.value) help.maybeStartTour();
});

const KZ = "Asia/Almaty";
const kzHour = Number(new Intl.DateTimeFormat("ru-RU", { hour: "numeric", hourCycle: "h23", timeZone: KZ }).format(new Date()));
const greeting = computed(() => {
  const name = auth.user?.first_name ? `, ${auth.user.first_name}` : "";
  if (kzHour >= 5 && kzHour < 12) return `Доброе утро${name}!`;
  if (kzHour >= 12 && kzHour < 18) return `Добрый день${name}!`;
  return `Добрый вечер${name}!`;
});
const dateLine = (() => {
  const s = new Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long", timeZone: KZ }).format(new Date());
  return s.charAt(0).toUpperCase() + s.slice(1);
})();

function timeKz(iso: string) {
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: KZ }).format(new Date(iso));
}

const n = (count: number, forms: [string, string, string]) => `${count} ${pluralRu(count, forms)}`;
const results = (id: number) => `/teacher/lessons/${id}/homework`;

type Tone = "done" | "attention" | "deadline" | "todo";
interface Card {
  key: string;
  tone: Tone;
  tag: string;
  title: string;
  text: string;
  links: { to: string; label: string }[];
}

const cards = computed<Card[]>(() => {
  const d = data.value;
  if (!d) return [];
  const out: Card[] = [];
  if (d.flagged.total) {
    out.push({
      key: "flagged",
      tone: "attention",
      tag: "Нужно ваше решение",
      title: `${n(d.flagged.total, ["работа похожа", "работы похожи", "работ похожи"])} на списывание`,
      text: "Это только подсказка. Можно оставить оценку, изменить её или дать пересдать.",
      links: d.flagged.lessons.map((l) => ({ to: results(l.lesson_id), label: `«${l.title}» — ${l.count} → Решить` })),
    });
  }
  if (d.manual_pending.total) {
    out.push({
      key: "manual",
      tone: "attention",
      tag: "Ждут вашей оценки",
      title: `${n(d.manual_pending.total, ["ученик ждёт", "ученика ждут", "учеников ждут"])} проверки эссе или файла`,
      text: "Остальные задания уже проверены автоматически.",
      links: d.manual_pending.lessons.map((l) => ({ to: results(l.lesson_id), label: `«${l.title}» — ${l.count} → Проверить` })),
    });
  }
  for (const dl of d.deadlines) {
    out.push({
      key: `deadline-${dl.lesson_id}`,
      tone: "deadline",
      tag: dl.passed ? "Срок прошёл" : dl.is_today ? "Срок сегодня" : "Срок завтра",
      title: dl.passed ? `«${dl.title}» — срок был в ${timeKz(dl.deadline)}` : `«${dl.title}» — до ${timeKz(dl.deadline)}`,
      text: dl.not_submitted
        ? `${n(dl.not_submitted, ["ученик", "ученика", "учеников"])} из ${dl.students} ещё не ${dl.not_submitted === 1 ? "сдал" : "сдали"}: ${dl.missing_names.join(", ")}${dl.not_submitted > dl.missing_names.length ? "…" : ""}`
        : `Все ${dl.students} ${pluralRu(dl.students, ["ученик", "ученика", "учеников"])} сдали.`,
      links: [{ to: results(dl.lesson_id), label: dl.not_submitted ? "Кто не сдал →" : "Результаты →" }],
    });
  }
  if (d.new_results.total) {
    out.push({
      key: "new",
      tone: "done",
      tag: "Готово",
      title: `${n(d.new_results.total, ["новый результат", "новых результата", "новых результатов"])} за сутки`,
      text: "Оценки уже поставлены автоматически.",
      links: d.new_results.lessons.map((l) => ({ to: results(l.lesson_id), label: `«${l.title}» — ${l.count} → Посмотреть` })),
    });
  }
  if (d.applications) {
    out.push({
      key: "apps",
      tone: "attention",
      tag: "Новые ученики",
      title: `${n(d.applications, ["заявка", "заявки", "заявок"])} на курсы`,
      text: "Одобрите — и ученик сразу получит доступ к урокам.",
      links: [{ to: "/teacher/applications", label: "Рассмотреть заявки →" }],
    });
  }
  if (d.old_homework_to_check) {
    out.push({
      key: "old-hw",
      tone: "attention",
      tag: "Ждут проверки",
      title: `${n(d.old_homework_to_check, ["домашка", "домашки", "домашек"])} с фото или текстом`,
      text: "Ответы, которые ученики прислали по обычному домашнему заданию.",
      links: [{ to: "/teacher/homework", label: "Проверить →" }],
    });
  }
  if (d.without_homework.total) {
    const names = d.without_homework.lessons.slice(0, 3).map((l) => `«${l.title}»`).join(", ");
    const first = d.without_homework.lessons[0];
    out.push({
      key: "no-hw",
      tone: "todo",
      tag: "Можно доделать",
      title: `В ${n(d.without_homework.total, ["уроке", "уроках", "уроках"])} нет домашки`,
      text: names + (d.without_homework.total > 3 ? " и другие" : ""),
      links: [{ to: `/teacher/categories/${first.course_id}`, label: "Добавить домашку →" }],
    });
  }
  return out;
});

const TONE: Record<Tone, { tag: string; border: string }> = {
  done: { tag: "bg-moss/15 text-moss", border: "border-l-moss" },
  attention: { tag: "bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200", border: "border-l-amber-500" },
  deadline: { tag: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300", border: "border-l-red-500" },
  todo: { tag: "bg-paper-2 text-ink-2", border: "border-l-line-strong" },
};

const tourSteps: TourStep[] = [
  {
    target: "today-cards",
    title: "Всё важное — на одной странице",
    text: "Здесь появляется то, что требует вашего внимания сегодня. Нажмите на кнопку в карточке — и сразу попадёте к делу.",
  },
  { target: "nav-courses", title: "Ваши курсы и уроки", text: "В «Мои курсы» вы добавляете уроки, видео, тесты и домашние задания." },
  { target: "font-size", title: "Текст крупнее", text: "Кнопка «A+» делает текст крупнее на всём сайте. Нажмите ещё раз — будет ещё крупнее." },
  { target: "help", title: "Если что-то непонятно", text: "Нажмите «Помощь» — там короткие инструкции и связь с администратором." },
];
</script>

<template>
  <PageContainer>
    <div class="mb-6 space-y-1">
      <h1 class="font-display text-display-lg text-ink">{{ greeting }}</h1>
      <p class="text-lg text-ink-2">{{ dateLine }}. Вот что требует внимания сегодня.</p>
    </div>

    <div v-if="loading" class="grid gap-4 md:grid-cols-2" aria-busy="true">
      <div v-for="i in 4" :key="i" class="h-40 animate-pulse rounded-2xl bg-paper-2" />
    </div>

    <div v-else-if="error" class="rounded-2xl bg-red-50 p-5 text-red-700 dark:bg-red-500/10 dark:text-red-300" role="alert">
      {{ error }} <button type="button" class="font-semibold underline" @click="load">Повторить</button>
    </div>

    <template v-else-if="data">
      <section aria-label="Что требует внимания">
        <div v-if="!cards.length" data-tour="today-cards" class="rounded-2xl border border-line bg-paper p-8 text-center">
          <p class="text-2xl font-bold text-ink">Всё спокойно ✓</p>
          <p class="mt-2 text-lg text-ink-2">Новых работ, заявок и сроков на сегодня нет.</p>
        </div>
        <div v-else class="grid gap-4 md:grid-cols-2">
          <article
            v-for="(c, i) in cards"
            :key="c.key"
            :data-tour="i === 0 ? 'today-cards' : undefined"
            class="flex flex-col gap-2 rounded-2xl border border-l-[6px] border-line bg-paper p-5"
            :class="TONE[c.tone].border"
          >
            <span class="self-start rounded-full px-3 py-1 text-sm font-bold" :class="TONE[c.tone].tag">{{ c.tag }}</span>
            <h2 class="text-xl font-bold leading-snug text-ink">{{ c.title }}</h2>
            <p class="text-ink-2">{{ c.text }}</p>
            <div class="mt-auto flex flex-col gap-2 pt-2">
              <router-link
                v-for="link in c.links"
                :key="link.to + link.label"
                :to="link.to"
                class="flex min-h-12 items-center rounded-xl border-2 border-moss/30 px-4 font-semibold text-moss transition-colors hover:border-moss hover:bg-moss/5"
              >
                {{ link.label }}
              </router-link>
            </div>
          </article>
        </div>
      </section>

      <section v-if="data.problems.length" class="mt-10 space-y-3" aria-labelledby="problems-title">
        <h2 id="problems-title" class="text-2xl font-bold text-ink">Проблемные места на этой неделе</h2>
        <p class="text-ink-2">Задания, в которых ошиблась половина класса или больше. Возможно, тему стоит объяснить ещё раз.</p>
        <ul class="space-y-3">
          <li v-for="(p, i) in data.problems" :key="i">
            <router-link
              :to="{ path: results(p.lesson_id), query: { tab: 'problems' } }"
              class="flex items-center gap-4 rounded-2xl border border-line bg-paper p-4 hover:border-moss/50"
            >
              <span class="w-16 shrink-0 text-center text-2xl font-bold text-red-700 dark:text-red-400">{{ p.percent }}%</span>
              <span class="min-w-0">
                <span class="block text-ink">
                  ошиблись в «{{ p.title }}», задание {{ p.task_number }}<template v-if="p.item_label">: {{ p.item_label }}</template>
                </span>
                <span class="block text-sm text-ink-3">
                  {{ p.wrong }} из {{ p.total }}<template v-if="p.common_wrong"> · чаще всего отвечали «{{ p.common_wrong }}»</template>
                </span>
              </span>
            </router-link>
          </li>
        </ul>
      </section>

      <section v-if="data.courses.length" class="mt-10 space-y-3" aria-labelledby="courses-title">
        <h2 id="courses-title" class="text-2xl font-bold text-ink">Мои курсы</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <router-link
            v-for="c in data.courses"
            :key="c.id"
            :to="`/teacher/categories/${c.id}`"
            class="flex flex-col gap-1 rounded-2xl border border-line bg-paper p-5 hover:border-moss/50"
          >
            <span class="text-lg font-bold text-ink">{{ c.name }}</span>
            <span class="text-ink-2">
              {{ n(c.lessons, ["урок", "урока", "уроков"]) }} · с домашкой {{ c.with_homework }} из {{ c.lessons }}
            </span>
            <span class="mt-2 font-semibold text-moss">Открыть курс →</span>
          </router-link>
        </div>
      </section>
    </template>

    <TeacherTour :steps="tourSteps" />
  </PageContainer>
</template>
