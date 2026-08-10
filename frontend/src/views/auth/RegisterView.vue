<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { useAuthStore } from "@/stores/auth";
import { localDigitsToPhone, sanitizeLocalPhoneDigits } from "@/utils/phone";

const auth = useAuthStore();
const router = useRouter();

const localPhone = ref("");
const localPhoneInput = computed({
  get: () => localPhone.value,
  set: (v: string) => {
    localPhone.value = sanitizeLocalPhoneDigits(v);
  },
});
const password = ref("");
const firstName = ref("");
const lastName = ref("");
const error = ref("");
const submitting = ref(false);

async function handleSubmit() {
  error.value = "";
  submitting.value = true;
  try {
    await auth.register({
      phone: localDigitsToPhone(localPhone.value),
      password: password.value,
      first_name: firstName.value,
      last_name: lastName.value,
    });
    router.push("/catalog");
  } catch (e) {
    if (isAxiosError(e) && e.response?.data?.detail) {
      error.value = String(e.response.data.detail);
    } else {
      error.value = "Не удалось зарегистрироваться. Попробуйте ещё раз.";
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-[60vh] items-center justify-center px-4 py-10">
    <div class="card w-full max-w-sm p-6 sm:p-8">
      <h1 class="font-display text-display-sm text-ink">Регистрация</h1>
      <form class="mt-6 space-y-4" @submit.prevent="handleSubmit">
        <div class="grid grid-cols-2 gap-3">
          <BaseInput v-model="firstName" label="Имя" />
          <BaseInput v-model="lastName" label="Фамилия" />
        </div>
        <BaseInput v-model="localPhoneInput" label="Телефон" placeholder="7XXXXXXXXX" inputmode="tel">
          <template #icon>+7</template>
        </BaseInput>
        <BaseInput v-model="password" label="Пароль" type="password" />
        <p v-if="error" class="text-sm text-clay">{{ error }}</p>
        <BaseButton type="submit" class="w-full" :disabled="submitting">Зарегистрироваться</BaseButton>
      </form>
      <p class="mt-6 text-center text-sm text-ink-2">
        Уже есть аккаунт?
        <router-link to="/login" class="text-moss underline underline-offset-2">Войти</router-link>
      </p>
    </div>
  </div>
</template>
