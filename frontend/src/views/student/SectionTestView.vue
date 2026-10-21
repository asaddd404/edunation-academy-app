<script setup lang="ts">
import { useRoute } from "vue-router";

import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import TestRunner from "@/components/tests/TestRunner.vue";

const route = useRoute();
const sectionId = Number(route.params.id);
</script>

<template>
  <PageContainer>
    <PageHeader title="Тест раздела" />
    <TestRunner kind="section" :id="sectionId" class="max-w-[42rem]" />
  </PageContainer>
</template>
