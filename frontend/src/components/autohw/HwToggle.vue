<script setup lang="ts">
/** An on/off switch: a real button with role="switch", so keyboards and
 * screen readers get it, and a 48x32 target that's easy to hit. */
defineProps<{ modelValue: boolean; label: string; disabled?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="label"
    :disabled="disabled"
    class="relative inline-flex h-8 w-14 shrink-0 items-center rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss focus-visible:ring-offset-2 disabled:opacity-50"
    :class="modelValue ? 'bg-moss' : 'bg-line-strong'"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span
      class="inline-block h-6 w-6 rounded-full bg-paper shadow transition-transform duration-200"
      :class="modelValue ? 'translate-x-7' : 'translate-x-1'"
    />
  </button>
</template>
