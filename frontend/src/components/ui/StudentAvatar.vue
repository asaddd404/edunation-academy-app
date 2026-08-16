<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { getAvatarUrl } from "@/api/auth";

/**
 * Student avatar with an initials fallback.
 *
 * `hasAvatar` comes from the API so the common case (no photo) never fires a
 * request that would 404. `failed` covers the rarer case of a stored path
 * whose file has gone missing -- without it a broken-image icon would show.
 */
const props = withDefaults(
  defineProps<{
    studentId: number;
    firstName: string;
    lastName: string;
    hasAvatar?: boolean;
    size?: number;
  }>(),
  { size: 40, hasAvatar: false },
);

const failed = ref(false);
watch(() => props.studentId, () => (failed.value = false));

const initials = computed(() =>
  `${props.lastName.charAt(0)}${props.firstName.charAt(0)}`.toUpperCase().trim() || "?",
);
const showImage = computed(() => props.hasAvatar && !failed.value);
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-paper-2 font-semibold text-ink-2 ring-1 ring-line"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.36)}px` }"
  >
    <img
      v-if="showImage"
      :src="getAvatarUrl(studentId)"
      :alt="`${lastName} ${firstName}`"
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <span v-else aria-hidden="true">{{ initials }}</span>
  </span>
</template>
