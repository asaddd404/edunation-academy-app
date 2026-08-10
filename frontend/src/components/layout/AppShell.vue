<script setup lang="ts">
import NavBar from "@/components/layout/NavBar.vue";
</script>

<template>
  <div class="flex min-h-dvh flex-col bg-sand text-ink font-body antialiased transition-colors duration-200">
    <NavBar />
    <main class="w-full flex-1">
      <slot />
    </main>
  </div>
</template>
