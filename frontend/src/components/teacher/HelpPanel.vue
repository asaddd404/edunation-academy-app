<script setup lang="ts">
import { X } from "@lucide/vue";
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

import { useTeacherHelpStore } from "@/stores/teacherHelp";

/**
 * «Помощь»: short step-by-step answers in plain words, the way you'd explain
 * it to a colleague, plus a way to reach the administrator. Slides in from
 * the right; Esc or a click outside closes it.
 */
const help = useTeacherHelpStore();
const closeButton = ref<HTMLButtonElement | null>(null);
let returnFocus: HTMLElement | null = null;

const whatsapp = (import.meta.env.VITE_SUPPORT_WHATSAPP ?? "").replace(/\D/g, "");

interface Guide {
  id: string;
  title: string;
  steps: string[];
}

const guides: Guide[] = [
  {
    id: "gaps",
    title: "Как сделать домашку с пропусками",
    steps: [
      "Откройте «Мои курсы» → нужный курс → нажмите на урок.",
      "Внизу урока найдите «Домашнее задание с автопроверкой» и нажмите «Заполните пропуски».",
      "Вставьте текст — можно скопировать прямо из Word.",
      "Нажмите на слова, которые ученик должен вписать сам. Они станут пропусками.",
      "Всё сохраняется само — кнопку «Сохранить» искать не нужно.",
    ],
  },
  {
    id: "types",
    title: "Какие ещё бывают задания",
    steps: [
      "Выбор одного или нескольких ответов, верно/неверно, сопоставление, порядок, краткий ответ — проверяются сами.",
      "Эссе и «фото или файл» проверяете вы: ученик увидит «Ожидает проверки».",
      "Задания можно двигать кнопками «↑ Выше» и «↓ Ниже», копировать и удалять.",
    ],
  },
  {
    id: "deadline",
    title: "Как поставить срок сдачи и таймер",
    steps: [
      "Под заданиями есть блок «Когда сдавать и сколько попыток».",
      "Включите «Срок сдачи» и выберите день и время (по Казахстану).",
      "Таймер на попытку и число попыток — там же. Всё можно менять, даже когда ученики уже решают.",
    ],
  },
  {
    id: "extend",
    title: "Как продлить срок одному ученику",
    steps: [
      "Откройте «Результаты учеников» у нужного урока.",
      "Нажмите «Подробнее» (или «Продлить срок») напротив ученика.",
      "В строке «Личный срок сдачи» выберите день и время и нажмите «Продлить».",
      "Если время на попытку кончается у всех сразу — нажмите «+10 минут тем, кто решает».",
    ],
  },
  {
    id: "copy",
    title: "Что значит «похоже на списывание»",
    steps: [
      "Это только подсказка, а не приговор. Например: у двух учеников одинаковые неправильные ответы, или работа сделана за пару секунд.",
      "Откройте работу («Подробнее») и решите сами: «Всё в порядке, оставить», «Изменить оценку», «Дать пересдать» или «Обнулить».",
      "Любое решение можно отменить кнопкой «Отменить решение».",
    ],
  },
  {
    id: "essay",
    title: "Как проверить эссе или фото",
    steps: [
      "На странице «Сегодня» нажмите «Проверить» в карточке «Ждут вашей оценки».",
      "Напротив ученика нажмите «Подробнее», прочитайте ответ или откройте файл.",
      "Отметьте выполненные критерии — баллы посчитаются сами — и нажмите «Сохранить баллы».",
    ],
  },
  {
    id: "trash",
    title: "Как восстановить удалённый урок",
    steps: [
      "Сразу после удаления внизу экрана появляется кнопка «Отменить» — нажмите её.",
      "Или откройте «Корзина» в меню и нажмите «Восстановить» рядом с уроком или разделом.",
      "Урок вернётся на своё место вместе с видео, тестом, домашкой и результатами учеников. Корзина хранит всё 30 дней.",
    ],
  },
  {
    id: "font",
    title: "Как сделать текст крупнее",
    steps: ["Нажмите кнопку «A+» вверху страницы. Каждое нажатие — крупнее, после самого крупного снова обычный."],
  },
];

const openId = ref<string | null>(null);

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && help.open) help.close();
}

watch(
  () => help.open,
  async (open) => {
    if (open) {
      returnFocus = document.activeElement as HTMLElement | null;
      openId.value = help.topic;
      document.addEventListener("keydown", onKey);
      await nextTick();
      closeButton.value?.focus();
    } else {
      document.removeEventListener("keydown", onKey);
      returnFocus?.focus?.();
    }
  },
);
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <div v-if="help.open" class="fixed inset-0 z-[70]">
      <div class="absolute inset-0 bg-black/40" aria-hidden="true" @click="help.close" />
      <aside
        class="motion-safe:animate-fade-in absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-paper shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
      >
        <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 id="help-title" class="text-xl font-bold text-ink">Помощь</h2>
          <button
            ref="closeButton"
            type="button"
            class="flex min-h-11 items-center gap-1.5 rounded-xl border-2 border-line px-3 font-semibold text-ink hover:bg-paper-2"
            @click="help.close"
          >
            <X :size="18" aria-hidden="true" /> Закрыть
          </button>
        </div>

        <div class="flex-1 space-y-3 overflow-y-auto px-5 py-5">
          <div v-for="g in guides" :key="g.id" class="rounded-2xl border border-line">
            <button
              type="button"
              class="flex min-h-14 w-full items-center justify-between gap-3 px-4 py-3 text-left text-lg font-semibold text-ink"
              :aria-expanded="openId === g.id"
              @click="openId = openId === g.id ? null : g.id"
            >
              {{ g.title }}
              <span class="shrink-0 text-2xl leading-none text-moss" aria-hidden="true">{{ openId === g.id ? "−" : "+" }}</span>
            </button>
            <ol v-if="openId === g.id" class="space-y-2.5 px-4 pb-4">
              <li v-for="(step, i) in g.steps" :key="i" class="flex gap-3 text-ink-2">
                <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-moss/10 text-sm font-bold text-moss">{{ i + 1 }}</span>
                <span class="pt-0.5">{{ step }}</span>
              </li>
            </ol>
          </div>

          <button
            type="button"
            class="flex min-h-12 w-full items-center justify-center rounded-xl border-2 border-dashed border-moss/50 px-4 font-semibold text-moss hover:bg-moss/5"
            @click="help.startTour"
          >
            Показать подсказки по странице заново
          </button>
        </div>

        <div class="space-y-3 border-t border-line bg-paper-2/60 px-5 py-4">
          <p class="font-semibold text-ink">Не получается?</p>
          <p class="text-ink-2">Напишите администратору — поможем.</p>
          <a
            v-if="whatsapp"
            :href="`https://wa.me/${whatsapp}`"
            target="_blank"
            rel="noopener"
            class="flex min-h-12 items-center justify-center rounded-xl bg-[#1f8f4e] px-4 font-bold text-white hover:brightness-110"
          >
            Написать в WhatsApp
          </a>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
