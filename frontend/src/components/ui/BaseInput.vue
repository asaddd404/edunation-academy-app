<script setup lang="ts">
defineProps<{
  modelValue: string;
  label: string;
  type?: string;
  placeholder?: string;
  error?: string;
}>();

defineEmits<{ (e: "update:modelValue", value: string): void }>();
</script>

<template>
  <label class="block">
    <span class="mb-1.5 block text-sm font-medium text-fg/80">{{ label }}</span>
    <input
      :type="type ?? 'text'"
      :value="modelValue"
      :placeholder="placeholder"
      class="w-full rounded-lg border border-fg/20 bg-transparent px-4 py-3 text-base text-fg placeholder:text-fg/40 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="error" class="mt-1 block text-sm text-red-500">{{ error }}</span>
  </label>
</template>
