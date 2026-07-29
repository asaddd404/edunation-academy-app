<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "danger" | "cta";
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
    class="inline-flex items-center justify-center rounded-xl px-4 py-3 text-sm font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
    :class="{
      'bg-accent text-bg hover:opacity-90': variant === 'primary',
      'border border-fg/20 bg-transparent text-fg hover:bg-fg/5': variant === 'secondary',
      'bg-red-600 text-white hover:bg-red-700': variant === 'danger',
      'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-500/20 hover:scale-[1.02] hover:shadow-indigo-500/40 active:scale-[0.98] disabled:hover:scale-100 disabled:hover:shadow-indigo-500/20':
        variant === 'cta',
    }"
  >
    <slot />
  </button>
</template>
