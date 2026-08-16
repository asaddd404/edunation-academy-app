<script setup lang="ts">
import {
  Atom,
  ChartColumnIncreasing,
  CircleCheck,
  Dna,
  FlaskConical,
  Globe,
  Languages,
  Lightbulb,
  Monitor,
  Scroll,
  Sigma,
  Timer,
} from "@lucide/vue";

import GlossaryTooltip from "@/components/shared/GlossaryTooltip.vue";

// Public marketing entry point. Deliberately free of API calls: `GET /categories`
// still requires auth, so everything here is static content that renders for a
// cold, unauthenticated visitor.
//
// Every number below is a fact about how the product works (subject count,
// question types, the real ЕНТ time limit), not usage statistics -- there is
// no honest way to source "10 000 учеников" from an app with no public API.

const bento = [
  {
    icon: Timer,
    title: "Умный таймер",
    text: "Время считается по правилам ЕНТ — 48 минут на предмет, до 4 часов на полный экзамен. Выбрал два предмета: получил ровно 96 минут.",
  },
  {
    icon: Lightbulb,
    title: "Словарь терминов в один клик",
    text: "Учитель отмечает термин прямо в тексте, ученик наводит курсор и сразу видит объяснение — не выходя из задания.",
  },
  {
    icon: ChartColumnIncreasing,
    title: "Аналитика и активность",
    text: "Видно, сколько времени ученик реально занимался сегодня, какие предметы просели и как меняется результат от попытки к попытке.",
  },
];

const facts = [
  { value: "5", label: "предметов ЕНТ в одной симуляции" },
  { value: "4", label: "типа заданий: выбор, множественный, соответствие, ответ" },
  { value: "240", label: "минут — полный экзамен с таймером" },
  { value: "2", label: "языка сдачи: русский и қазақша" },
];

const subjects = [
  { icon: Sigma, name: "Математика" },
  { icon: Atom, name: "Физика" },
  { icon: FlaskConical, name: "Химия" },
  { icon: Dna, name: "Биология" },
  { icon: Scroll, name: "История" },
  { icon: Globe, name: "География" },
  { icon: Monitor, name: "Информатика" },
  { icon: Languages, name: "Языки" },
];

const steps = [
  { n: "01", title: "Зарегистрируйся", text: "Нужен только номер телефона. Занимает меньше минуты." },
  { n: "02", title: "Подай заявку на предмет", text: "Выбери предмет в каталоге — учитель подтвердит доступ." },
  { n: "03", title: "Учись и решай", text: "Уроки, тесты, домашние задания — в своём темпе." },
  { n: "04", title: "Проверь себя на ЕНТ", text: "Симуляция экзамена и рейтинг покажут реальный уровень." },
];
</script>

<template>
  <div class="overflow-x-hidden bg-sand">
    <!-- ── Hero ─────────────────────────────────────────────────────── -->
    <section class="px-4 pb-20 pt-14 sm:pb-28 sm:pt-20">
      <div class="mx-auto grid max-w-[80rem] items-center gap-12 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <span
            class="inline-flex items-center gap-2 rounded-full border border-line bg-paper px-3.5 py-1.5 text-xs font-medium text-ink-2 motion-safe:animate-fade-up"
          >
            <span class="relative flex h-2 w-2">
              <span class="absolute inline-flex h-full w-full rounded-full bg-moss opacity-75 motion-safe:animate-ping" />
              <span class="relative inline-flex h-2 w-2 rounded-full bg-moss" />
            </span>
            Онлайн-подготовка к ЕНТ
          </span>

          <h1
            class="mt-6 font-display text-4xl font-semibold leading-[1.1] tracking-tight text-ink motion-safe:animate-fade-up sm:text-5xl lg:text-6xl"
            style="animation-delay: 80ms"
          >
            Готовься к ЕНТ<br class="hidden sm:block" />
            <span class="text-gradient-brand">без зубрёжки вслепую</span>
          </h1>

          <p
            class="mt-5 max-w-xl text-body-lg text-ink-2 motion-safe:animate-fade-up"
            style="animation-delay: 160ms"
          >
            Настоящий формат экзамена с таймером, разбор каждой ошибки по предметам и объяснение
            непонятного термина прямо в задании.
          </p>

          <div class="mt-8 flex flex-wrap gap-3 motion-safe:animate-fade-up" style="animation-delay: 240ms">
            <router-link to="/register" class="btn-primary px-6 py-3 text-base">Начать подготовку</router-link>
            <router-link to="/login" class="btn-ghost px-6 py-3 text-base">Демо-тест</router-link>
          </div>

          <p class="mt-4 text-caption text-ink-3 motion-safe:animate-fade-up" style="animation-delay: 300ms">
            Регистрация по номеру телефона — без карты и подписки.
          </p>
        </div>

        <!-- Not a screenshot: this is the real glossary component, so the
             hover hint on the landing behaves exactly as it does in a lesson. -->
        <div class="motion-safe:animate-fade-up lg:justify-self-end" style="animation-delay: 200ms">
          <div class="card w-full max-w-md p-5 shadow-lg">
            <div class="mb-4 flex items-center justify-between">
              <span class="badge bg-moss/10 text-moss">Химия · вопрос 3 из 15</span>
              <span class="flex items-center gap-1.5 text-sm font-semibold tabular-nums text-ink">
                <Timer :size="15" :stroke-width="1.8" class="text-ink-3" />
                47:12
              </span>
            </div>

            <p class="text-body-lg font-medium text-ink">
              Сколько электронов содержит нейтральный атом, если его
              <GlossaryTooltip
                term="атомный номер"
                explanation="Число протонов в ядре. У нейтрального атома электронов ровно столько же."
              />
              равен 16?
            </p>

            <div class="mt-4 space-y-2">
              <div
                v-for="(opt, i) in [
                  { letter: 'А', text: '8' },
                  { letter: 'Б', text: '16', correct: true },
                  { letter: 'В', text: '32' },
                ]"
                :key="i"
                class="flex items-center gap-3 rounded-xl border px-3.5 py-2.5 text-sm transition-all duration-200 ease-out"
                :class="opt.correct ? 'border-moss bg-moss/10' : 'border-line'"
              >
                <span
                  class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold"
                  :class="opt.correct ? 'bg-moss text-moss-fg' : 'bg-paper-2 text-ink-2'"
                >
                  {{ opt.letter }}
                </span>
                <span class="flex-1 text-ink">{{ opt.text }}</span>
                <CircleCheck v-if="opt.correct" :size="17" :stroke-width="2" class="shrink-0 text-moss" />
              </div>
            </div>

            <p class="mt-4 text-caption text-ink-3">Наведите на подчёркнутый термин — подсказка работает по-настоящему.</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Bento: what makes it different ───────────────────────────── -->
    <section class="px-4 pb-20 sm:pb-28">
      <div class="mx-auto max-w-[80rem]">
        <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
          Не просто тесты
        </h2>
        <p class="mt-3 max-w-2xl text-body-lg text-ink-2">
          Три вещи, которых обычно не хватает при самостоятельной подготовке.
        </p>

        <div class="mt-10 grid gap-4 md:grid-cols-3">
          <article
            v-for="card in bento"
            :key="card.title"
            class="group rounded-2xl border border-line bg-paper p-6 transition-all duration-200 ease-out hover:-translate-y-1 hover:border-moss/40 hover:shadow-lg"
          >
            <span
              class="flex h-11 w-11 items-center justify-center rounded-xl bg-moss/10 text-moss transition-colors duration-200 group-hover:bg-moss group-hover:text-moss-fg"
            >
              <component :is="card.icon" :size="21" :stroke-width="1.7" />
            </span>
            <h3 class="mt-4 font-display text-lg font-semibold text-ink">{{ card.title }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-ink-2">{{ card.text }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ── Product facts ────────────────────────────────────────────── -->
    <section class="px-4 pb-20 sm:pb-28">
      <div class="mx-auto max-w-[80rem]">
        <div class="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          <div v-for="fact in facts" :key="fact.label" class="bg-paper p-6">
            <p class="font-display text-4xl font-semibold text-moss">{{ fact.value }}</p>
            <p class="mt-2 text-sm leading-snug text-ink-2">{{ fact.label }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Subjects ─────────────────────────────────────────────────── -->
    <section class="px-4 pb-20 sm:pb-28">
      <div class="mx-auto max-w-[80rem]">
        <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Предметы</h2>
        <div class="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div
            v-for="subject in subjects"
            :key="subject.name"
            class="flex items-center gap-3 rounded-2xl border border-line bg-paper p-4 transition-all duration-200 ease-out hover:border-moss/40 hover:shadow-sm"
          >
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-paper-2 text-ink-2">
              <component :is="subject.icon" :size="19" :stroke-width="1.7" />
            </span>
            <span class="truncate text-sm font-medium text-ink">{{ subject.name }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ── How it works ─────────────────────────────────────────────── -->
    <section class="px-4 pb-20 sm:pb-28">
      <div class="mx-auto max-w-[80rem]">
        <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Как начать</h2>
        <div class="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div
            v-for="step in steps"
            :key="step.n"
            class="rounded-2xl border border-line bg-paper p-6 transition-all duration-200 ease-out hover:border-moss/40 hover:shadow-sm"
          >
            <span class="font-display text-2xl font-semibold text-moss/40">{{ step.n }}</span>
            <h3 class="mt-3 font-medium text-ink">{{ step.title }}</h3>
            <p class="mt-1.5 text-sm leading-relaxed text-ink-2">{{ step.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Closing CTA ──────────────────────────────────────────────── -->
    <section class="px-4 pb-24">
      <div class="mx-auto max-w-[80rem]">
        <div class="rounded-3xl border border-line bg-paper px-6 py-14 text-center sm:px-12">
          <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Начни с одной пробной симуляции
          </h2>
          <p class="mx-auto mt-4 max-w-xl text-body-lg text-ink-2">
            Она покажет реальный балл и то, какой предмет тянет вниз — этого достаточно, чтобы понять,
            с чего начинать.
          </p>
          <div class="mt-8 flex flex-wrap justify-center gap-3">
            <router-link to="/register" class="btn-primary px-6 py-3 text-base">Создать аккаунт</router-link>
            <router-link to="/login" class="btn-ghost px-6 py-3 text-base">У меня уже есть аккаунт</router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
