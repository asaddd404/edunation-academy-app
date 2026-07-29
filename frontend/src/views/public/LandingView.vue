<script setup lang="ts">
// Public marketing entry point. Deliberately free of API calls: `GET /categories`
// still requires auth, so everything here is static content that renders for a
// cold, unauthenticated visitor.

const features = [
  {
    icon: "🎬",
    title: "Видеоуроки",
    text: "Адаптивное HLS-видео, которое не рвётся на слабом интернете. Смотри с телефона или ноутбука.",
    gradient: "from-indigo-500 to-blue-500",
  },
  {
    icon: "✍️",
    title: "Тесты с автопроверкой",
    text: "Мини-тест после каждого урока и итоговый тест раздела. Результат — сразу, без ожидания.",
    gradient: "from-violet-500 to-purple-500",
  },
  {
    icon: "🎯",
    title: "ЕНТ-симулятор",
    text: "Полноценная симуляция экзамена с таймером и реальным форматом заданий.",
    gradient: "from-fuchsia-500 to-pink-500",
  },
  {
    icon: "📝",
    title: "Домашние задания",
    text: "Учитель ставит задания и проверяет их лично — с комментариями и оценкой.",
    gradient: "from-rose-500 to-orange-500",
  },
  {
    icon: "📈",
    title: "Прогресс и рейтинг",
    text: "Видно, сколько уроков пройдено и на каком ты месте среди других учеников.",
    gradient: "from-emerald-500 to-teal-500",
  },
  {
    icon: "🔔",
    title: "Уведомления",
    text: "Заявку одобрили, домашку проверили, вышел новый урок — ничего не пропустишь.",
    gradient: "from-amber-500 to-yellow-500",
  },
];

const steps = [
  { n: "01", title: "Зарегистрируйся", text: "Нужен только номер телефона. Занимает меньше минуты." },
  { n: "02", title: "Подай заявку на предмет", text: "Выбери предмет в каталоге — учитель подтвердит доступ." },
  { n: "03", title: "Учись и решай", text: "Уроки, тесты, домашние задания — в своём темпе." },
  { n: "04", title: "Проверь себя на ЕНТ", text: "Симуляция экзамена и рейтинг покажут реальный уровень." },
];

const subjects = [
  { icon: "📐", name: "Математика", gradient: "from-sky-500 to-cyan-400" },
  { icon: "⚛️", name: "Физика", gradient: "from-blue-600 to-indigo-500" },
  { icon: "🧪", name: "Химия", gradient: "from-fuchsia-500 to-pink-500" },
  { icon: "🧬", name: "Биология", gradient: "from-emerald-500 to-lime-400" },
  { icon: "📜", name: "История", gradient: "from-amber-500 to-orange-500" },
  { icon: "🌍", name: "География", gradient: "from-teal-500 to-emerald-400" },
  { icon: "💻", name: "Информатика", gradient: "from-indigo-600 to-blue-500" },
  { icon: "🔤", name: "Английский", gradient: "from-violet-500 to-purple-500" },
];

const stats = [
  { value: "8+", label: "предметов" },
  { value: "100%", label: "онлайн" },
  { value: "24/7", label: "доступ к урокам" },
];
</script>

<template>
  <div class="overflow-x-hidden">
    <!-- ── Hero ─────────────────────────────────────────────────────── -->
    <section class="relative isolate px-4 pb-20 pt-14 sm:pb-28 sm:pt-20">
      <div class="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div class="glow-blob -left-24 -top-32 h-[28rem] w-[28rem] animate-drift" />
        <div
          class="glow-blob -right-24 top-24 h-[26rem] w-[26rem] animate-drift"
          style="animation-delay: -6s; background: radial-gradient(circle, hsl(330 81% 60% / 0.5), transparent 70%)"
        />
        <div
          class="glow-blob bottom-0 left-1/3 h-[22rem] w-[22rem] animate-drift"
          style="animation-delay: -12s; background: radial-gradient(circle, hsl(199 89% 55% / 0.45), transparent 70%)"
        />
      </div>

      <div class="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <span
            class="inline-flex animate-fade-up items-center gap-2 rounded-full border border-border bg-card/70 px-3.5 py-1.5 text-xs font-medium text-fg/70 backdrop-blur"
          >
            <span class="relative flex h-2 w-2">
              <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-pop opacity-75" />
              <span class="relative inline-flex h-2 w-2 rounded-full bg-pop" />
            </span>
            Онлайн-подготовка к ЕНТ и школьным предметам
          </span>

          <h1
            class="mt-6 animate-fade-up text-4xl font-bold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl"
            style="animation-delay: 80ms"
          >
            Учись так, как<br class="hidden sm:block" />
            <span class="text-gradient-brand">удобно тебе</span>
          </h1>

          <p
            class="mt-5 max-w-xl animate-fade-up text-base leading-relaxed text-fg/60 sm:text-lg"
            style="animation-delay: 160ms"
          >
            Edunation Academy — платформа, где видеоуроки, тесты, домашние задания и полноценная
            симуляция ЕНТ собраны в одном месте. Без бумажных тетрадей и потерянных дедлайнов.
          </p>

          <div class="mt-8 flex animate-fade-up flex-wrap gap-3" style="animation-delay: 240ms">
            <router-link
              to="/register"
              class="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-3.5 text-sm font-medium text-white shadow-lg shadow-indigo-500/25 transition-all duration-200 hover:scale-[1.02] hover:shadow-indigo-500/40 active:scale-[0.98]"
            >
              Начать бесплатно
              <span aria-hidden="true">→</span>
            </router-link>
            <router-link
              to="/login"
              class="inline-flex items-center justify-center rounded-xl border border-fg/20 px-6 py-3.5 text-sm font-medium text-fg transition-colors duration-200 hover:bg-fg/5"
            >
              У меня есть аккаунт
            </router-link>
          </div>

          <dl class="mt-12 flex animate-fade-up flex-wrap gap-8" style="animation-delay: 320ms">
            <!-- flex-col-reverse keeps the dt-before-dd source order the spec
                 wants while showing the number above its label. -->
            <div v-for="stat in stats" :key="stat.label" class="flex flex-col-reverse">
              <dt class="text-xs text-fg/50 sm:text-sm">{{ stat.label }}</dt>
              <dd class="text-2xl font-bold sm:text-3xl">{{ stat.value }}</dd>
            </div>
          </dl>
        </div>

        <!-- Decorative product mock: a miniature of the real lesson UI. -->
        <div class="relative animate-fade-up lg:justify-self-end" style="animation-delay: 200ms" aria-hidden="true">
          <div class="glass-card animate-float p-5 shadow-2xl shadow-indigo-500/10 sm:p-6">
            <div class="flex items-center gap-3">
              <div
                class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-cyan-400 text-xl"
              >
                📐
              </div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold">Математика · Раздел 3</p>
                <p class="truncate text-xs text-fg/50">Квадратные уравнения</p>
              </div>
              <span class="rounded-full bg-pop/15 px-2.5 py-1 text-[10px] font-medium text-fg/70">В процессе</span>
            </div>

            <div class="mt-5 flex aspect-video items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500/20 via-violet-500/15 to-pink-500/20">
              <span
                class="flex h-14 w-14 items-center justify-center rounded-full bg-white/90 pl-1 text-xl text-indigo-600 shadow-lg"
              >
                ▶
              </span>
            </div>

            <div class="mt-5">
              <div class="flex items-center justify-between text-xs text-fg/50">
                <span>Прогресс раздела</span>
                <span class="font-medium text-fg/70">7 / 10</span>
              </div>
              <div class="mt-2 h-2 overflow-hidden rounded-full bg-fg/10">
                <div class="h-full w-[70%] rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
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
                class="flex items-center gap-2.5 rounded-lg border border-border/60 px-3 py-2.5 text-xs"
              >
                <span
                  class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px]"
                  :class="item.done ? 'bg-emerald-500 text-white' : 'border border-dashed border-fg/30 text-fg/40'"
                >
                  {{ item.done ? "✓" : "" }}
                </span>
                <span :class="item.done ? 'text-fg/50 line-through' : 'text-fg/80'">{{ item.label }}</span>
              </div>
            </div>
          </div>

          <div
            class="glass-card absolute -bottom-5 -left-4 animate-float px-4 py-3 shadow-xl sm:-left-8"
            style="animation-delay: -3s"
          >
            <p class="text-[10px] uppercase tracking-wide text-fg/45">Результат теста</p>
            <p class="text-lg font-bold text-emerald-500">92%</p>
          </div>

          <div
            class="glass-card absolute -right-2 -top-5 animate-float px-4 py-3 shadow-xl sm:-right-6"
            style="animation-delay: -1.5s"
          >
            <p class="text-[10px] uppercase tracking-wide text-fg/45">Рейтинг ЕНТ</p>
            <p class="text-lg font-bold text-gradient-brand">#12</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Features ─────────────────────────────────────────────────── -->
    <section class="border-t border-border/60 px-4 py-20 sm:py-24">
      <div class="mx-auto max-w-6xl">
        <div class="max-w-2xl">
          <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">
            Всё для учёбы — <span class="text-gradient-brand">в одном месте</span>
          </h2>
          <p class="mt-3 text-fg/60">
            Не нужно жонглировать мессенджерами, облаками и таблицами. Платформа закрывает весь путь
            от первого урока до пробного ЕНТ.
          </p>
        </div>

        <div class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <article
            v-for="feature in features"
            :key="feature.title"
            class="group rounded-2xl border border-border bg-card p-6 transition-all duration-200 hover:-translate-y-1 hover:border-indigo-500/40 hover:shadow-xl hover:shadow-indigo-500/5"
          >
            <div
              class="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br text-2xl transition-transform duration-200 group-hover:scale-110"
              :class="feature.gradient"
            >
              {{ feature.icon }}
            </div>
            <h3 class="mt-5 text-lg font-semibold">{{ feature.title }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-fg/60">{{ feature.text }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ── How it works ─────────────────────────────────────────────── -->
    <section class="relative isolate border-t border-border/60 px-4 py-20 sm:py-24">
      <div class="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div class="glow-blob left-1/2 top-1/4 h-[24rem] w-[24rem] -translate-x-1/2 opacity-25" />
      </div>

      <div class="mx-auto max-w-6xl">
        <h2 class="max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">Как это работает</h2>
        <p class="mt-3 max-w-2xl text-fg/60">Четыре шага от регистрации до первого пробного экзамена.</p>

        <ol class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <li
            v-for="step in steps"
            :key="step.n"
            class="relative rounded-2xl border border-border bg-card p-6"
          >
            <span class="text-sm font-bold text-gradient-brand">{{ step.n }}</span>
            <h3 class="mt-3 text-base font-semibold">{{ step.title }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-fg/60">{{ step.text }}</p>
          </li>
        </ol>
      </div>
    </section>

    <!-- ── Subjects ─────────────────────────────────────────────────── -->
    <section class="border-t border-border/60 px-4 py-20 sm:py-24">
      <div class="mx-auto max-w-6xl">
        <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">Предметы</h2>
        <p class="mt-3 max-w-2xl text-fg/60">
          Каталог пополняется. После регистрации подай заявку на любой предмет — учитель откроет доступ.
        </p>

        <div class="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <div
            v-for="subject in subjects"
            :key="subject.name"
            class="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3.5 transition-colors duration-200 hover:border-indigo-500/40"
          >
            <span
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-lg"
              :class="subject.gradient"
            >
              {{ subject.icon }}
            </span>
            <span class="truncate text-sm font-medium">{{ subject.name }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Final CTA ────────────────────────────────────────────────── -->
    <section class="px-4 pb-24 pt-4">
      <div class="mx-auto max-w-6xl">
        <div class="relative isolate overflow-hidden rounded-3xl border border-border bg-card px-6 py-14 text-center sm:px-12 sm:py-20">
          <div class="pointer-events-none absolute inset-0 -z-10">
            <div class="glow-blob -left-10 -top-20 h-72 w-72 animate-drift" />
            <div
              class="glow-blob -bottom-24 -right-10 h-72 w-72 animate-drift"
              style="animation-delay: -9s; background: radial-gradient(circle, hsl(330 81% 60% / 0.5), transparent 70%)"
            />
          </div>

          <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">
            Готов начать? <span class="text-gradient-brand">Это бесплатно</span>
          </h2>
          <p class="mx-auto mt-4 max-w-xl text-fg/60">
            Регистрация занимает меньше минуты — нужен только номер телефона.
          </p>
          <div class="mt-8 flex flex-wrap justify-center gap-3">
            <router-link
              to="/register"
              class="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-7 py-3.5 text-sm font-medium text-white shadow-lg shadow-indigo-500/25 transition-all duration-200 hover:scale-[1.02] hover:shadow-indigo-500/40 active:scale-[0.98]"
            >
              Создать аккаунт
              <span aria-hidden="true">→</span>
            </router-link>
            <router-link
              to="/login"
              class="inline-flex items-center justify-center rounded-xl border border-fg/20 px-7 py-3.5 text-sm font-medium text-fg transition-colors duration-200 hover:bg-fg/5"
            >
              Войти
            </router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
