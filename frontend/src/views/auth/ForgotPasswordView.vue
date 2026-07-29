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
  <div class="relative isolate mx-auto flex min-h-[70vh] max-w-md flex-col justify-center py-10">
    <div class="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div class="glow-blob -top-16 left-1/2 h-72 w-72 -translate-x-1/2 animate-drift" />
    </div>

    <div class="glass-card animate-fade-up p-6 sm:p-8">
      <h1 class="text-2xl font-semibold">Восстановление пароля</h1>
      <p class="mt-3 text-sm leading-relaxed text-fg/60">
        Автоматическое восстановление по SMS пока не подключено. Но доступ к аккаунту можно вернуть — через
        администратора.
      </p>

      <ol class="mt-6 space-y-3">
        <li v-for="(step, index) in steps" :key="index" class="flex gap-3 text-sm">
          <span
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 text-xs font-semibold text-white"
          >
            {{ index + 1 }}
          </span>
          <span class="text-fg/70">{{ step }}</span>
        </li>
      </ol>

      <router-link
        to="/login"
        class="mt-8 inline-flex w-full items-center justify-center rounded-xl border border-fg/20 px-4 py-3 text-sm font-medium text-fg transition-colors duration-200 hover:bg-fg/5"
      >
        Вернуться ко входу
      </router-link>
    </div>
  </div>
</template>
