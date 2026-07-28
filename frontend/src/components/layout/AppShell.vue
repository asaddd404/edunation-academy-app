<script setup lang="ts">
import NavBar from "@/components/layout/NavBar.vue";
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <NavBar />
    <main class="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
      <slot />
    </main>
  </div>
</template>
