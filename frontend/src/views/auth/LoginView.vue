<script setup lang="ts">
import { isAxiosError } from "axios";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const phone = ref("+7");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function handleSubmit() {
  error.value = "";
  submitting.value = true;
  try {
    await auth.login({ phone: phone.value, password: password.value });
    const redirect = (route.query.redirect as string) || undefined;
    router.push(redirect ?? "/");
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
  <div class="mx-auto flex max-w-sm flex-col justify-center py-8 sm:py-16">
    <div class="rounded-2xl border border-fg/10 p-6 sm:p-8">
      <h1 class="mb-6 text-2xl font-semibold">Вход</h1>
      <form class="space-y-4" @submit.prevent="handleSubmit">
        <BaseInput v-model="phone" label="Телефон" placeholder="+7XXXXXXXXXX" />
        <BaseInput v-model="password" label="Пароль" type="password" />
        <p v-if="error" class="text-sm text-red-600 dark:text-red-500">{{ error }}</p>
        <BaseButton type="submit" class="w-full" :disabled="submitting">Войти</BaseButton>
      </form>
      <p class="mt-6 text-center text-sm text-fg/60">
        Нет аккаунта?
        <router-link to="/register" class="text-accent underline underline-offset-2">Зарегистрироваться</router-link>
      </p>
    </div>
  </div>
</template>
