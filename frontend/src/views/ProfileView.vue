<script setup lang="ts">
import { isAxiosError } from "axios";
import { onMounted, reactive, ref } from "vue";

import { deleteAvatar, getAvatarUrl, updateProfile, uploadAvatar } from "@/api/auth";
import { getEntLeaderboard } from "@/api/ent";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { useAuthStore } from "@/stores/auth";
import type { EntLeaderboardEntry } from "@/types";

const auth = useAuthStore();

const form = reactive({
  first_name: auth.user?.first_name ?? "",
  last_name: auth.user?.last_name ?? "",
  phone: auth.user?.phone ?? "",
});

const saving = ref(false);
const saveError = ref("");
const saveSuccess = ref(false);

const avatarUploading = ref(false);
const avatarError = ref("");
const avatarCacheBust = ref(0);

const myRating = ref<EntLeaderboardEntry | null>(null);

const ROLE_LABEL: Record<string, string> = {
  student: "Ученик",
  teacher: "Учитель",
  admin: "Администратор",
};

const RANK_TIERS: { min: number; label: string }[] = [
  { min: 5000, label: "Легенда" },
  { min: 1500, label: "Мастер" },
  { min: 500, label: "Знаток" },
  { min: 100, label: "Ученик" },
  { min: 0, label: "Новичок" },
];

function rankLabel(xp: number): string {
  return RANK_TIERS.find((tier) => xp >= tier.min)?.label ?? "Новичок";
}

onMounted(async () => {
  if (auth.user?.role !== "student") return;
  try {
    const leaderboard = await getEntLeaderboard(1);
    myRating.value = leaderboard.me;
  } catch (e) {
    // A student with no approved course yet gets a 403 here -- that's fine,
    // the stat cards just render zeros.
    if (!isAxiosError(e) || e.response?.status !== 403) throw e;
  }
});

async function handleSave() {
  if (!form.first_name.trim() || !form.last_name.trim() || !form.phone.trim()) return;
  saving.value = true;
  saveError.value = "";
  saveSuccess.value = false;
  try {
    const updated = await updateProfile({
      first_name: form.first_name,
      last_name: form.last_name,
      phone: form.phone,
    });
    auth.setUser(updated);
    form.phone = updated.phone;
    saveSuccess.value = true;
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 409) {
      saveError.value = "Этот номер телефона уже занят другим пользователем.";
    } else if (isAxiosError(e) && e.response?.status === 422) {
      saveError.value = "Проверьте формат номера телефона (+7XXXXXXXXXX).";
    } else {
      saveError.value = "Не удалось сохранить изменения.";
    }
  } finally {
    saving.value = false;
  }
}

function handleAvatarFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (file) uploadAvatarFile(file);
}

async function uploadAvatarFile(file: File) {
  avatarUploading.value = true;
  avatarError.value = "";
  try {
    const updated = await uploadAvatar(file);
    auth.setUser(updated);
    avatarCacheBust.value++;
  } catch {
    avatarError.value = "Не удалось загрузить изображение.";
  } finally {
    avatarUploading.value = false;
  }
}

async function handleDeleteAvatar() {
  const updated = await deleteAvatar();
  auth.setUser(updated);
  avatarCacheBust.value++;
}
</script>

<template>
  <div class="mx-auto max-w-lg space-y-6">
    <h1 class="text-2xl font-semibold">
      <span class="text-gradient-brand">Профиль</span>
    </h1>

    <div v-if="auth.user" class="glass-card flex flex-col items-center gap-3 p-5">
      <div class="rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-[3px] shadow-lg shadow-indigo-500/20">
        <div class="rounded-full bg-card p-1">
          <img
            v-if="auth.user.has_avatar"
            :src="`${getAvatarUrl(auth.user.id)}?v=${avatarCacheBust}`"
            alt=""
            class="h-24 w-24 rounded-full object-cover"
          />
          <div
            v-else
            class="flex h-24 w-24 items-center justify-center rounded-full bg-fg/10 text-2xl font-medium text-fg/60"
          >
            {{ auth.user.first_name[0] }}{{ auth.user.last_name[0] }}
          </div>
        </div>
      </div>

      <span
        v-if="auth.user.role === 'student'"
        class="inline-flex items-center rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1 text-xs font-semibold text-white shadow-md shadow-indigo-500/20"
      >
        {{ rankLabel(myRating?.total_xp ?? 0) }} • {{ myRating?.total_xp ?? 0 }} XP
      </span>
      <span v-else class="text-sm text-fg/50">{{ ROLE_LABEL[auth.user.role] }}</span>

      <div class="flex flex-wrap items-center justify-center gap-2">
        <label class="cursor-pointer text-sm text-accent underline">
          {{ auth.user.has_avatar ? "Заменить фото" : "Загрузить фото" }}
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            class="hidden"
            :disabled="avatarUploading"
            @change="handleAvatarFileChange"
          />
        </label>
        <BaseButton v-if="auth.user.has_avatar" variant="secondary" @click="handleDeleteAvatar">
          Удалить фото
        </BaseButton>
      </div>
      <span v-if="avatarUploading" class="text-sm text-fg/60">Загрузка…</span>
      <span v-if="avatarError" class="text-sm text-red-600 dark:text-red-500">{{ avatarError }}</span>
    </div>

    <div v-if="auth.user?.role === 'student'" class="grid grid-cols-3 gap-3">
      <div class="glass-card flex flex-col items-center gap-1 p-4 text-center">
        <span class="text-2xl">🎯</span>
        <span class="text-xl font-bold">{{ myRating?.simulations_completed ?? 0 }}</span>
        <span class="text-xs text-fg/60">Симуляций</span>
      </div>
      <div class="glass-card flex flex-col items-center gap-1 p-4 text-center">
        <span class="text-2xl">🏅</span>
        <span class="text-xl font-bold">{{ myRating?.best_score ?? 0 }}</span>
        <span class="text-xs text-fg/60">Лучший балл</span>
      </div>
      <div class="glass-card flex flex-col items-center gap-1 p-4 text-center">
        <span class="text-2xl">⚡</span>
        <span class="text-xl font-bold">{{ myRating?.total_xp ?? 0 }}</span>
        <span class="text-xs text-fg/60">Всего XP</span>
      </div>
    </div>

    <form class="glass-card space-y-4 p-4" @submit.prevent="handleSave">
      <BaseInput v-model="form.first_name" label="Имя">
        <template #icon>
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              d="M10 8a3 3 0 100-6 3 3 0 000 6zM3.465 14.493a1.23 1.23 0 00.41 1.412A9.957 9.957 0 0010 18c2.31 0 4.438-.784 6.131-2.1.43-.333.604-.903.408-1.41a7.002 7.002 0 00-13.074.003z"
            />
          </svg>
        </template>
      </BaseInput>
      <BaseInput v-model="form.last_name" label="Фамилия">
        <template #icon>
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              d="M10 8a3 3 0 100-6 3 3 0 000 6zM3.465 14.493a1.23 1.23 0 00.41 1.412A9.957 9.957 0 0010 18c2.31 0 4.438-.784 6.131-2.1.43-.333.604-.903.408-1.41a7.002 7.002 0 00-13.074.003z"
            />
          </svg>
        </template>
      </BaseInput>
      <BaseInput v-model="form.phone" label="Телефон" placeholder="+7XXXXXXXXXX">
        <template #icon>
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              d="M2 3.5A1.5 1.5 0 013.5 2h1.148a1.5 1.5 0 011.465 1.175l.716 3.223a1.5 1.5 0 01-.464 1.415L4.5 9.5c-.11.11.108.5.398 1.01a9 9 0 004.593 4.593c.51.29.9.508 1.01.398l1.687-1.865a1.5 1.5 0 011.415-.464l3.223.716a1.5 1.5 0 011.175 1.465V16.5a1.5 1.5 0 01-1.5 1.5h-1C7.663 18 2 12.337 2 4.5v-1z"
            />
          </svg>
        </template>
      </BaseInput>

      <p v-if="saveError" class="text-sm text-red-600 dark:text-red-500">{{ saveError }}</p>
      <p v-if="saveSuccess" class="text-sm text-green-700 dark:text-green-500">Изменения сохранены.</p>

      <BaseButton type="submit" variant="cta" class="w-full" :disabled="saving">Сохранить</BaseButton>
    </form>
  </div>
</template>
