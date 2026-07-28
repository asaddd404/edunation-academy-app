<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "danger";
    type?: "button" | "submit";
    disabled?: boolean;
  }>(),
  { variant: "primary", type: "button", disabled: false },
);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="inline-flex items-center justify-center rounded-lg px-4 py-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
    :class="{
      'bg-accent text-white hover:opacity-90': variant === 'primary',
      'border border-fg/20 bg-transparent text-fg hover:bg-fg/5': variant === 'secondary',
      'bg-red-600 text-white hover:bg-red-700': variant === 'danger',
    }"
  >
    <slot />
  </button>
</template>
