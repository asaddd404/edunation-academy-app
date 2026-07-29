<script setup lang="ts">
import { isAxiosError } from "axios";
import { reactive, ref } from "vue";

import { deleteAvatar, getAvatarUrl, updateProfile, uploadAvatar } from "@/api/auth";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { useAuthStore } from "@/stores/auth";

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

const ROLE_LABEL: Record<string, string> = {
  student: "Ученик",
  teacher: "Учитель",
  admin: "Администратор",
};

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
    <h1 class="text-2xl font-semibold">Профиль</h1>

    <div v-if="auth.user" class="flex flex-col items-center gap-3 rounded-xl border border-fg/10 p-4">
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
      <span v-if="avatarError" class="text-sm text-red-500">{{ avatarError }}</span>

      <span class="text-sm text-fg/50">{{ ROLE_LABEL[auth.user.role] }}</span>
    </div>

    <form class="space-y-4 rounded-xl border border-fg/10 p-4" @submit.prevent="handleSave">
      <BaseInput v-model="form.first_name" label="Имя" />
      <BaseInput v-model="form.last_name" label="Фамилия" />
      <BaseInput v-model="form.phone" label="Телефон" placeholder="+7XXXXXXXXXX" />

      <p v-if="saveError" class="text-sm text-red-500">{{ saveError }}</p>
      <p v-if="saveSuccess" class="text-sm text-green-500">Изменения сохранены.</p>

      <BaseButton type="submit" :disabled="saving">Сохранить</BaseButton>
    </form>
  </div>
</template>
