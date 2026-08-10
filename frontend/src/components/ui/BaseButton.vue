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
    :class="{
      'btn-primary': variant === 'primary' || variant === 'cta',
      'btn-ghost': variant === 'secondary',
      'btn-danger': variant === 'danger',
    }"
  >
    <slot />
  </button>
</template>
