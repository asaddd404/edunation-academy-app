<script setup lang="ts">
defineProps<{
  modelValue: string;
  label: string;
  type?: string;
  placeholder?: string;
  error?: string;
  inputmode?: "text" | "tel" | "numeric" | "decimal" | "email" | "url" | "search" | "none";
}>();

defineEmits<{ (e: "update:modelValue", value: string): void }>();
</script>

<template>
  <label class="block">
    <span class="mb-1.5 block text-label text-ink-2">{{ label }}</span>
    <div class="relative">
      <span
        v-if="$slots.icon"
        class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-sm text-ink-3"
      >
        <slot name="icon" />
      </span>
      <input
        :type="type ?? 'text'"
        :value="modelValue"
        :placeholder="placeholder"
        :inputmode="inputmode"
        class="input"
        :class="{ 'pl-10': $slots.icon }"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <span v-if="error" class="mt-1 block text-caption text-clay">{{ error }}</span>
  </label>
</template>
