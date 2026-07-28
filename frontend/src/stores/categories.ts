import { defineStore } from "pinia";
import { ref } from "vue";

import * as categoriesApi from "@/api/categories";
import type { Category } from "@/types";

export const useCategoriesStore = defineStore("categories", () => {
  const list = ref<Category[]>([]);
  const loading = ref(false);

  async function fetchAll() {
    loading.value = true;
    try {
      list.value = await categoriesApi.listCategories();
    } finally {
      loading.value = false;
    }
  }

  return { list, loading, fetchAll };
});
