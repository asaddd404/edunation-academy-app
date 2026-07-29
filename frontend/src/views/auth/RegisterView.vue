<script setup lang="ts">
import { isAxiosError } from "axios";
import { ref } from "vue";
import { useRouter } from "vue-router";

import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

const phone = ref("+7");
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
      phone: phone.value,
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
  <div class="mx-auto flex max-w-sm flex-col justify-center py-8 sm:py-16">
    <div class="rounded-2xl border border-fg/10 p-6 sm:p-8">
      <h1 class="mb-6 text-2xl font-semibold">Регистрация</h1>
      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div class="grid grid-cols-2 gap-3">
          <BaseInput v-model="firstName" label="Имя" />
          <BaseInput v-model="lastName" label="Фамилия" />
        </div>
        <BaseInput v-model="phone" label="Телефон" placeholder="+7XXXXXXXXXX" />
        <BaseInput v-model="password" label="Пароль" type="password" />
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
        <BaseButton type="submit" class="w-full" :disabled="submitting">Зарегистрироваться</BaseButton>
      </form>
      <p class="mt-6 text-center text-sm text-fg/60">
        Уже есть аккаунт?
        <router-link to="/login" class="text-accent underline underline-offset-2">Войти</router-link>
      </p>
    </div>
  </div>
</template>
