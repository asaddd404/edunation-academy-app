<script setup lang="ts">
import { Trash2 } from "@lucide/vue";
import { onMounted, ref } from "vue";

import { deleteForever, listTrash, restoreFromTrash, type TrashEntry } from "@/api/trash";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import { useToastStore } from "@/stores/toast";
import { describeApiError } from "@/utils/apiError";
import { pluralRu } from "@/utils/subjectTheme";

/**
 * «Корзина»: lessons and sections deleted in the last 30 days. One button
 * brings them back -- with video, tests, homework and students' results --
 * and «Удалить навсегда» (with a second confirmation) empties one early.
 */
const toast = useToastStore();
const items = ref<TrashEntry[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const busy = ref<string | null>(null);
const confirming = ref<string | null>(null);

const keyOf = (t: TrashEntry) => `${t.kind}-${t.object_id}`;

async function load() {
  loading.value = true;
  error.value = null;
  try {
    items.value = await listTrash();
  } catch (e) {
    error.value = describeApiError(e, "Не удалось загрузить корзину.");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function restore(t: TrashEntry) {
  busy.value = keyOf(t);
  try {
    const result = await restoreFromTrash(t.kind, t.object_id);
    toast.push(result.message, "success");
    items.value = items.value.filter((i) => keyOf(i) !== keyOf(t));
  } catch (e) {
    toast.push(describeApiError(e, "Не удалось восстановить."));
    await load();
  } finally {
    busy.value = null;
  }
}

async function removeForever(t: TrashEntry) {
  busy.value = keyOf(t);
  try {
    await deleteForever(t.kind, t.object_id);
    toast.push(`«${t.title}» удалено навсегда.`, "info");
    items.value = items.value.filter((i) => keyOf(i) !== keyOf(t));
  } catch (e) {
    toast.push(describeApiError(e, "Не удалось удалить."));
  } finally {
    busy.value = null;
    confirming.value = null;
  }
}

function daysLeft(t: TrashEntry): number {
  return Math.max(0, Math.ceil((new Date(t.purge_at).getTime() - Date.now()) / 86_400_000));
}

function when(iso: string): string {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Almaty" }).format(
    new Date(iso),
  );
}
</script>

<template>
  <PageContainer>
    <PageHeader title="Корзина" />
    <p class="-mt-2 mb-6 max-w-2xl text-lg text-ink-2">
      Удалённые уроки и разделы хранятся здесь 30 дней. Их можно вернуть одной кнопкой — вместе с видео, тестами, домашкой и
      результатами учеников.
    </p>

    <div v-if="loading" class="space-y-3" aria-busy="true">
      <div v-for="i in 3" :key="i" class="h-24 animate-pulse rounded-2xl bg-paper-2" />
    </div>

    <div v-else-if="error" class="rounded-2xl bg-red-50 p-5 text-red-700 dark:bg-red-500/10 dark:text-red-300" role="alert">
      {{ error }} <button type="button" class="font-semibold underline" @click="load">Повторить</button>
    </div>

    <div v-else-if="!items.length" class="flex flex-col items-center gap-3 rounded-2xl border border-line bg-paper px-6 py-12 text-center">
      <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-moss"><Trash2 :size="26" /></span>
      <p class="text-xl font-bold text-ink">Корзина пуста</p>
      <p class="text-ink-2">Здесь появится то, что вы удалите в редакторе курса.</p>
    </div>

    <ul v-else class="space-y-3">
      <li v-for="t in items" :key="keyOf(t)" class="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-paper p-4 sm:p-5">
        <div class="min-w-0 flex-1 basis-64">
          <span class="rounded-full bg-paper-2 px-3 py-1 text-sm font-bold text-ink-2">{{ t.kind === "section" ? "Раздел" : "Урок" }}</span>
          <p class="mt-2 text-lg font-bold text-ink">{{ t.title }}</p>
          <p class="text-ink-2">
            {{ t.course }}<template v-if="t.kind === 'section'"> · {{ t.lesson_count }} {{ pluralRu(t.lesson_count, ["урок", "урока", "уроков"]) }}</template>
          </p>
          <p class="text-sm text-ink-3">
            Удалено {{ when(t.deleted_at) }}<template v-if="t.deleted_by"> · {{ t.deleted_by }}</template> · удалится навсегда через
            {{ daysLeft(t) }} {{ pluralRu(daysLeft(t), ["день", "дня", "дней"]) }}
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn-primary min-h-12 px-5 text-base" :disabled="busy === keyOf(t)" @click="restore(t)">Восстановить</button>
          <template v-if="confirming === keyOf(t)">
            <button
              type="button"
              class="min-h-12 rounded-xl bg-red-600 px-4 font-bold text-white hover:bg-red-700"
              :disabled="busy === keyOf(t)"
              @click="removeForever(t)"
            >
              Да, удалить навсегда
            </button>
            <button type="button" class="min-h-12 rounded-xl border-2 border-line px-4 font-semibold" @click="confirming = null">Не удалять</button>
          </template>
          <button
            v-else
            type="button"
            class="min-h-12 rounded-xl border-2 border-red-200 px-4 font-semibold text-red-700 hover:bg-red-50 dark:border-red-500/30 dark:text-red-400 dark:hover:bg-red-500/10"
            @click="confirming = keyOf(t)"
          >
            Удалить навсегда
          </button>
        </div>
      </li>
    </ul>
  </PageContainer>
</template>
