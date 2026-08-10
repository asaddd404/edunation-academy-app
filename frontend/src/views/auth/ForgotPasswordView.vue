<script setup lang="ts">
// Deliberately not a working reset flow: there is no SMS/email delivery
// channel yet, so issuing reset tokens would only create links nobody can
// receive. This page exists so a locked-out user sees a route forward
// instead of a dead end on the login screen.
const steps = [
  "Напишите своему учителю или администратору платформы.",
  "Назовите номер телефона, на который зарегистрирован аккаунт.",
  "Администратор задаст новый пароль и передаст его вам.",
  "Войдите с новым паролем и сразу смените его в разделе «Профиль».",
];
</script>

<template>
  <div class="flex min-h-[60vh] items-center justify-center px-4 py-10">
    <div class="card w-full max-w-md p-6 sm:p-8">
      <h1 class="font-display text-display-sm text-ink">Восстановление пароля</h1>
      <p class="mt-3 text-sm leading-relaxed text-ink-2">
        Автоматическое восстановление по SMS пока не подключено. Но доступ к аккаунту можно вернуть — через
        администратора.
      </p>

      <ol class="mt-6 space-y-3">
        <li v-for="(step, index) in steps" :key="index" class="flex gap-3 text-sm">
          <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-moss text-xs font-semibold text-moss-fg">
            {{ index + 1 }}
          </span>
          <span class="text-ink-2">{{ step }}</span>
        </li>
      </ol>

      <router-link to="/login" class="btn-ghost mt-8 w-full"> Вернуться ко входу </router-link>
    </div>
  </div>
</template>
