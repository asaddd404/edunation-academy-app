<script setup lang="ts">
import { Target, Trophy, Zap } from "@lucide/vue";
import { isAxiosError } from "axios";
import { computed, onMounted, reactive, ref } from "vue";

import { deleteAvatar, getAvatarUrl, updateProfile, uploadAvatar } from "@/api/auth";
import { getMyTodayActivity } from "@/api/activity";
import { getEntLeaderboard } from "@/api/ent";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { useAuthStore } from "@/stores/auth";
import type { EntLeaderboardEntry } from "@/types";
import { formatActivityDuration } from "@/utils/activity";
import { ROLE_LABEL } from "@/utils/roleLabel";

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

const DAILY_NORM_SECONDS = 1800;
const todayActivitySeconds = ref(0);
const activityProgress = computed(() => Math.min(100, (todayActivitySeconds.value / DAILY_NORM_SECONDS) * 100));

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
  const today = await getMyTodayActivity();
  todayActivitySeconds.value = today.total_seconds;
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

const passwordForm = reactive({ current: "", next: "", confirm: "" });
const passwordTouched = reactive({ next: false, confirm: false });
const passwordSaving = ref(false);
const passwordError = ref("");
const passwordSuccess = ref(false);

// Validated inline as the student types, rather than only after the server
// rejects the request.
const newPasswordError = computed(() => {
  if (!passwordTouched.next || !passwordForm.next) return "";
  if (passwordForm.next.length < 8) return "Минимум 8 символов";
  if (passwordForm.next === passwordForm.current) return "Новый пароль совпадает с текущим";
  return "";
});

const confirmPasswordError = computed(() => {
  if (!passwordTouched.confirm || !passwordForm.confirm) return "";
  return passwordForm.confirm === passwordForm.next ? "" : "Пароли не совпадают";
});

const canChangePassword = computed(
  () =>
    passwordForm.current.length > 0 &&
    passwordForm.next.length >= 8 &&
    passwordForm.next !== passwordForm.current &&
    passwordForm.confirm === passwordForm.next,
);

async function handleChangePassword() {
  if (!canChangePassword.value) return;
  passwordSaving.value = true;
  passwordError.value = "";
  passwordSuccess.value = false;
  try {
    await auth.changePassword({ old_password: passwordForm.current, new_password: passwordForm.next });
    passwordForm.current = "";
    passwordForm.next = "";
    passwordForm.confirm = "";
    passwordTouched.next = false;
    passwordTouched.confirm = false;
    passwordSuccess.value = true;
  } catch (e) {
    const detail = isAxiosError(e) ? e.response?.data?.detail : null;
    passwordError.value = typeof detail === "string" ? detail : "Не удалось сменить пароль.";
  } finally {
    passwordSaving.value = false;
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
  <PageContainer>
    <PageHeader title="Профиль" />
    <div class="mx-auto max-w-lg space-y-6">
    <div v-if="auth.user" class="card flex flex-col items-center gap-3 p-5">
      <div class="rounded-full border-2 border-moss p-1">
        <img
          v-if="auth.user.has_avatar"
          :src="`${getAvatarUrl(auth.user.id)}?v=${avatarCacheBust}`"
          alt=""
          class="h-24 w-24 rounded-full object-cover"
        />
        <div
          v-else
          class="flex h-24 w-24 items-center justify-center rounded-full bg-paper-2 text-2xl font-medium text-ink-2"
        >
          {{ auth.user.first_name[0] }}{{ auth.user.last_name[0] }}
        </div>
      </div>

      <span
        v-if="auth.user.role === 'student'"
        class="inline-flex items-center rounded-full bg-moss px-3 py-1 text-xs font-semibold text-moss-fg"
      >
        {{ rankLabel(myRating?.total_xp ?? 0) }} • {{ myRating?.total_xp ?? 0 }} XP
      </span>
      <span v-else class="text-sm text-ink-3">{{ ROLE_LABEL[auth.user.role] }}</span>

      <div class="flex flex-wrap items-center justify-center gap-2">
        <label class="cursor-pointer text-sm text-moss underline">
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
      <span v-if="avatarUploading" class="text-sm text-ink-2">Загрузка…</span>
      <span v-if="avatarError" class="text-sm text-clay">{{ avatarError }}</span>
    </div>

    <div v-if="auth.user?.role === 'student'" class="grid grid-cols-3 gap-3">
      <div class="card flex flex-col items-center gap-1 p-4 text-center">
        <Target :size="22" :stroke-width="1.7" class="text-moss" />
        <span class="text-xl font-bold text-ink">{{ myRating?.simulations_completed ?? 0 }}</span>
        <span class="text-xs text-ink-2">Симуляций</span>
      </div>
      <div class="card flex flex-col items-center gap-1 p-4 text-center">
        <Trophy :size="22" :stroke-width="1.7" class="text-moss" />
        <span class="text-xl font-bold text-ink">{{ myRating?.best_score ?? 0 }}</span>
        <span class="text-xs text-ink-2">Лучший балл</span>
      </div>
      <div class="card flex flex-col items-center gap-1 p-4 text-center">
        <Zap :size="22" :stroke-width="1.7" class="text-moss" />
        <span class="text-xl font-bold text-ink">{{ myRating?.total_xp ?? 0 }}</span>
        <span class="text-xs text-ink-2">Всего XP</span>
      </div>
    </div>

    <div v-if="auth.user?.role === 'student'" class="card space-y-2 p-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium text-ink">Активность сегодня</h2>
        <span class="text-sm font-semibold text-ink">{{ formatActivityDuration(todayActivitySeconds) }}</span>
      </div>
      <div class="h-2 w-full overflow-hidden rounded-full bg-paper-2">
        <div class="h-full rounded-full bg-moss transition-all duration-500" :style="{ width: `${activityProgress}%` }" />
      </div>
      <p class="text-xs text-ink-2">Дневная норма — 30 минут.</p>
    </div>

    <form class="card space-y-4 p-4" @submit.prevent="handleSave">
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

      <p v-if="saveError" class="text-sm text-clay">{{ saveError }}</p>
      <p v-if="saveSuccess" class="text-sm text-moss">Изменения сохранены.</p>

      <BaseButton type="submit" variant="cta" class="w-full" :disabled="saving">Сохранить</BaseButton>
    </form>

    <form class="card space-y-4 p-4" @submit.prevent="handleChangePassword">
      <div>
        <h2 class="text-lg font-semibold text-ink">Смена пароля</h2>
        <p class="mt-1 text-sm text-ink-2">
          После смены пароля вы останетесь в системе на этом устройстве, а на остальных нужно будет войти заново.
        </p>
      </div>

      <BaseInput v-model="passwordForm.current" label="Текущий пароль" type="password">
        <template #icon>
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              fill-rule="evenodd"
              d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z"
              clip-rule="evenodd"
            />
          </svg>
        </template>
      </BaseInput>

      <div @input="passwordTouched.next = true">
        <BaseInput
          v-model="passwordForm.next"
          label="Новый пароль"
          type="password"
          placeholder="Минимум 8 символов"
          :error="newPasswordError"
        >
          <template #icon>
            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path
                fill-rule="evenodd"
                d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z"
                clip-rule="evenodd"
              />
            </svg>
          </template>
        </BaseInput>
      </div>

      <div @input="passwordTouched.confirm = true">
        <BaseInput
          v-model="passwordForm.confirm"
          label="Повторите новый пароль"
          type="password"
          :error="confirmPasswordError"
        >
          <template #icon>
            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path
                fill-rule="evenodd"
                d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z"
                clip-rule="evenodd"
              />
            </svg>
          </template>
        </BaseInput>
      </div>

      <p v-if="passwordError" class="text-sm text-clay">{{ passwordError }}</p>
      <p v-if="passwordSuccess" class="text-sm text-moss">Пароль изменён.</p>

      <BaseButton type="submit" class="w-full" :disabled="passwordSaving || !canChangePassword">
        Сменить пароль
      </BaseButton>
    </form>
    </div>
  </PageContainer>
</template>
