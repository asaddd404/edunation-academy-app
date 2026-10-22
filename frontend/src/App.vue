<script setup lang="ts">
import AppShell from "@/components/layout/AppShell.vue";
</script>

<template>
  <AppShell>
    <!-- Views that take their record from a path param read it once, at
         setup. Vue reuses the instance when only the param changes -- a
         notification from /lessons/2 to /lessons/1 -- so without a key the
         old lesson stays on screen under the new URL. Keyed on the path,
         not fullPath: a query change (catalog drill-down, leaderboard tabs)
         must not remount. -->
    <router-view v-slot="{ Component, route }">
      <component :is="Component" :key="route.meta.remountOnParams ? route.path : undefined" />
    </router-view>
  </AppShell>
</template>
