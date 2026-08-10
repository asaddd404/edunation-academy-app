<script setup lang="ts">
// Public marketing entry point. Deliberately free of API calls: `GET /categories`
// still requires auth, so everything here is static content that renders for a
// cold, unauthenticated visitor.

const features = [
  {
    icon: "🎬",
    title: "Видеоуроки",
    text: "Адаптивное HLS-видео, которое не рвётся на слабом интернете. Смотри с телефона или ноутбука.",
  },
  {
    icon: "✍️",
    title: "Тесты с автопроверкой",
    text: "Мини-тест после каждого урока и итоговый тест раздела. Результат — сразу, без ожидания.",
  },
  {
    icon: "🎯",
    title: "ЕНТ-симулятор",
    text: "Полноценная симуляция экзамена с таймером и реальным форматом заданий.",
  },
  {
    icon: "📝",
    title: "Домашние задания",
    text: "Учитель ставит задания и проверяет их лично — с комментариями и оценкой.",
  },
  {
    icon: "📈",
    title: "Прогресс и рейтинг",
    text: "Видно, сколько уроков пройдено и на каком ты месте среди других учеников.",
  },
  {
    icon: "🔔",
    title: "Уведомления",
    text: "Заявку одобрили, домашку проверили, вышел новый урок — ничего не пропустишь.",
  },
];

const steps = [
  { n: "01", title: "Зарегистрируйся", text: "Нужен только номер телефона. Занимает меньше минуты." },
  { n: "02", title: "Подай заявку на предмет", text: "Выбери предмет в каталоге — учитель подтвердит доступ." },
  { n: "03", title: "Учись и решай", text: "Уроки, тесты, домашние задания — в своём темпе." },
  { n: "04", title: "Проверь себя на ЕНТ", text: "Симуляция экзамена и рейтинг покажут реальный уровень." },
];

const subjects = [
  { icon: "📐", name: "Математика" },
  { icon: "⚛️", name: "Физика" },
  { icon: "🧪", name: "Химия" },
  { icon: "🧬", name: "Биология" },
  { icon: "📜", name: "История" },
  { icon: "🌍", name: "География" },
  { icon: "💻", name: "Информатика" },
  { icon: "🔤", name: "Английский" },
];

const stats = [
  { value: "8+", label: "предметов" },
  { value: "100%", label: "онлайн" },
  { value: "24/7", label: "доступ к урокам" },
];
</script>

<template>
  <div class="overflow-x-hidden bg-sand">
    <!-- ── Hero ─────────────────────────────────────────────────────── -->
    <section class="px-4 pb-20 pt-14 sm:pb-28 sm:pt-20">
      <div class="mx-auto grid max-w-[90rem] items-center gap-12 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <span
            class="inline-flex motion-safe:animate-fade-up items-center gap-2 rounded-full border border-line bg-paper px-3.5 py-1.5 text-xs font-medium text-ink-2"
          >
            <span class="relative flex h-2 w-2">
              <span class="motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full bg-moss opacity-75" />
              <span class="relative inline-flex h-2 w-2 rounded-full bg-moss" />
            </span>
            Онлайн-подготовка к ЕНТ и школьным предметам
          </span>

          <h1
            class="mt-6 motion-safe:animate-fade-up font-display text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl"
            style="animation-delay: 80ms"
          >
            Учись так, как<br class="hidden sm:block" />
            <span class="text-moss">удобно тебе</span>
          </h1>

          <p
            class="mt-5 max-w-xl motion-safe:animate-fade-up text-body-lg text-ink-2"
            style="animation-delay: 160ms"
          >
            Edunation Academy — платформа, где видеоуроки, тесты, домашние задания и полноценная
            симуляция ЕНТ собраны в одном месте. Без бумажных тетрадей и потерянных дедлайнов.
          </p>

          <div class="mt-8 flex motion-safe:animate-fade-up flex-wrap gap-3" style="animation-delay: 240ms">
            <router-link to="/register" class="btn-primary px-6 py-3.5">
              Начать бесплатно
              <span aria-hidden="true">→</span>
            </router-link>
            <router-link to="/login" class="btn-ghost px-6 py-3.5"> У меня есть аккаунт </router-link>
          </div>

          <dl class="mt-12 flex motion-safe:animate-fade-up flex-wrap gap-8" style="animation-delay: 320ms">
            <!-- flex-col-reverse keeps the dt-before-dd source order the spec
                 wants while showing the number above its label. -->
            <div v-for="stat in stats" :key="stat.label" class="flex flex-col-reverse">
              <dt class="text-caption text-ink-3">{{ stat.label }}</dt>
              <dd class="font-display text-2xl font-semibold text-ink sm:text-3xl">{{ stat.value }}</dd>
            </div>
          </dl>
        </div>

        <!-- Decorative product mock: a miniature of the real lesson UI. -->
        <div class="relative motion-safe:animate-fade-up lg:justify-self-end" style="animation-delay: 200ms" aria-hidden="true">
          <div class="card p-5 sm:p-6">
            <div class="flex items-center gap-3">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-moss/15 text-xl">📐</div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold text-ink">Математика · Раздел 3</p>
                <p class="truncate text-xs text-ink-3">Квадратные уравнения</p>
              </div>
              <span class="rounded-full bg-paper-2 px-2.5 py-1 text-[10px] font-medium text-ink-2">В процессе</span>
            </div>

            <div class="mt-5 flex aspect-video items-center justify-center rounded-xl bg-paper-2">
              <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss pl-1 text-xl text-moss-fg shadow-lg">
                ▶
              </span>
            </div>

            <div class="mt-5">
              <div class="flex items-center justify-between text-xs text-ink-3">
                <span>Прогресс раздела</span>
                <span class="font-medium text-ink-2">7 / 10</span>
              </div>
              <div class="mt-2 h-2 overflow-hidden rounded-full bg-paper-2">
                <div class="h-full w-[70%] rounded-full bg-moss" />
              </div>
            </div>

            <div class="mt-5 space-y-2">
              <div
                v-for="item in [
                  { label: 'Урок 6 · Дискриминант', done: true },
                  { label: 'Урок 7 · Теорема Виета', done: true },
                  { label: 'Тест раздела', done: false },
                ]"
                :key="item.label"
                class="flex items-center gap-2.5 rounded-lg border border-line px-3 py-2.5 text-xs"
              >
                <span
                  class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px]"
                  :class="item.done ? 'bg-moss text-moss-fg' : 'border border-dashed border-line-strong text-ink-3'"
                >
                  {{ item.done ? "✓" : "" }}
                </span>
                <span :class="item.done ? 'text-ink-3 line-through' : 'text-ink-2'">{{ item.label }}</span>
              </div>
            </div>
          </div>

          <div class="card absolute -bottom-5 -left-4 px-4 py-3 sm:-left-8">
            <p class="text-[10px] uppercase tracking-wide text-ink-3">Результат теста</p>
            <p class="text-lg font-bold text-moss">92%</p>
          </div>

          <div class="card absolute -right-2 -top-5 px-4 py-3 sm:-right-6">
            <p class="text-[10px] uppercase tracking-wide text-ink-3">Рейтинг ЕНТ</p>
            <p class="text-lg font-bold text-ink">#12</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Features ─────────────────────────────────────────────────── -->
    <section class="border-t border-line px-4 py-20 sm:py-24">
      <div class="mx-auto max-w-[90rem]">
        <div class="max-w-2xl">
          <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Всё для учёбы — в одном месте
          </h2>
          <p class="mt-3 text-ink-2">
            Не нужно жонглировать мессенджерами, облаками и таблицами. Платформа закрывает весь путь
            от первого урока до пробного ЕНТ.
          </p>
        </div>

        <div class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          <article v-for="feature in features" :key="feature.title" class="card p-6">
            <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-moss/15 text-2xl">
              {{ feature.icon }}
            </div>
            <h3 class="mt-5 text-lg font-semibold text-ink">{{ feature.title }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-ink-2">{{ feature.text }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ── How it works ─────────────────────────────────────────────── -->
    <section class="border-t border-line px-4 py-20 sm:py-24">
      <div class="mx-auto max-w-[90rem]">
        <h2 class="max-w-2xl font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
          Как это работает
        </h2>
        <p class="mt-3 max-w-2xl text-ink-2">Четыре шага от регистрации до первого пробного экзамена.</p>

        <ol class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <li v-for="step in steps" :key="step.n" class="card p-6">
            <span class="text-sm font-bold text-moss">{{ step.n }}</span>
            <h3 class="mt-3 text-base font-semibold text-ink">{{ step.title }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-ink-2">{{ step.text }}</p>
          </li>
        </ol>
      </div>
    </section>

    <!-- ── Subjects ─────────────────────────────────────────────────── -->
    <section class="border-t border-line px-4 py-20 sm:py-24">
      <div class="mx-auto max-w-[90rem]">
        <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Предметы</h2>
        <p class="mt-3 max-w-2xl text-ink-2">
          Каталог пополняется. После регистрации подай заявку на любой предмет — учитель откроет доступ.
        </p>

        <div class="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          <div v-for="subject in subjects" :key="subject.name" class="card flex items-center gap-3 px-4 py-3.5">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-moss/15 text-lg">
              {{ subject.icon }}
            </span>
            <span class="truncate text-sm font-medium text-ink">{{ subject.name }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Final CTA ────────────────────────────────────────────────── -->
    <section class="px-4 pb-24 pt-4">
      <div class="mx-auto max-w-[90rem]">
        <div class="card px-6 py-14 text-center sm:px-12 sm:py-20">
          <h2 class="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Готов начать? Это бесплатно
          </h2>
          <p class="mx-auto mt-4 max-w-xl text-ink-2">
            Регистрация занимает меньше минуты — нужен только номер телефона.
          </p>
          <div class="mt-8 flex flex-wrap justify-center gap-3">
            <router-link to="/register" class="btn-primary px-7 py-3.5">
              Создать аккаунт
              <span aria-hidden="true">→</span>
            </router-link>
            <router-link to="/login" class="btn-ghost px-7 py-3.5"> Войти </router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
