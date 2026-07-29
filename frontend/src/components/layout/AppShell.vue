<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import NavBar from "@/components/layout/NavBar.vue";

const route = useRoute();

// Marketing-style pages (landing, 404) manage their own sections edge-to-edge;
// everything else keeps the narrow reading container.
const isFullWidth = computed(() => route.meta.layout === "full");
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <NavBar />
    <main :class="isFullWidth ? 'w-full flex-1' : 'mx-auto w-full max-w-3xl flex-1 px-4 py-6'">
      <slot />
    </main>
  </div>
</template>
