<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { HOME_BY_ROLE } from "@/router";
import { useAuthStore } from "@/stores/auth";
import type { Role } from "@/types";
import { localDigitsToPhone, sanitizeLocalPhoneDigits } from "@/utils/phone";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const localPhone = ref("");
// Sanitizes on every keystroke (and on paste) so the field can never hold
// anything but digits -- there is no "+7" in this input for a pasted
// number to collide with.
const localPhoneInput = computed({
  get: () => localPhone.value,
  set: (v: string) => {
    localPhone.value = sanitizeLocalPhoneDigits(v);
  },
});
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function handleSubmit() {
  error.value = "";
  submitting.value = true;
  try {
    await auth.login({ phone: localDigitsToPhone(localPhone.value), password: password.value });
    const redirect = (route.query.redirect as string) || undefined;
    // "/" is public now (the navbar brand link needs it reachable while
    // signed in too), so it no longer bounces a fresh login to the
    // dashboard on its own -- send it there explicitly.
    router.push(redirect ?? HOME_BY_ROLE[auth.role as Role]);
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 401) {
      error.value = "Неверный номер телефона или пароль";
    } else {
      error.value = "Не удалось войти. Попробуйте ещё раз.";
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-[60vh] items-center justify-center px-4 py-10">
    <div class="card w-full max-w-sm p-6 sm:p-8">
      <h1 class="font-display text-display-sm text-ink">Вход</h1>
      <form class="mt-6 space-y-4" @submit.prevent="handleSubmit">
        <BaseInput v-model="localPhoneInput" label="Телефон" placeholder="7XXXXXXXXX" inputmode="tel">
          <template #icon>+7</template>
        </BaseInput>
        <BaseInput v-model="password" label="Пароль" type="password" />
        <div class="flex justify-end">
          <router-link to="/forgot-password" class="text-sm text-ink-2 underline underline-offset-2 hover:text-ink">
            Забыли пароль?
          </router-link>
        </div>
        <p v-if="error" class="text-sm text-clay">{{ error }}</p>
        <BaseButton type="submit" class="w-full" :disabled="submitting">Войти</BaseButton>
      </form>
      <p class="mt-6 text-center text-sm text-ink-2">
        Нет аккаунта?
        <router-link to="/register" class="text-moss underline underline-offset-2">Зарегистрироваться</router-link>
      </p>
    </div>
  </div>
</template>
