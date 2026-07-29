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
    <div class="relative">
      <span v-if="$slots.icon" class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-fg/40">
        <slot name="icon" />
      </span>
      <input
        :type="type ?? 'text'"
        :value="modelValue"
        :placeholder="placeholder"
        class="w-full rounded-xl border border-fg/20 bg-transparent px-4 py-3 text-base text-fg placeholder:text-fg/40 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
        :class="{ 'pl-10': $slots.icon }"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <span v-if="error" class="mt-1 block text-sm text-red-600 dark:text-red-500">{{ error }}</span>
  </label>
</template>
