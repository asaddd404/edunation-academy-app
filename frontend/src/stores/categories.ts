import { defineStore } from "pinia";
import { ref } from "vue";

import * as categoriesApi from "@/api/categories";
import type { Category } from "@/types";

// The catalog page filters/searches this list entirely client-side (tag
// chips, free-text search), so it asks for one large page rather than
// exposing pager UI -- the backend still caps and paginates the response,
// which is the actual fix; a real "load more" only matters once course
// catalogs outgrow this page size.
const CATALOG_PAGE_SIZE = 100;

export const useCategoriesStore = defineStore("categories", () => {
  const list = ref<Category[]>([]);
  const loading = ref(false);

  async function fetchAll() {
    loading.value = true;
    try {
      const res = await categoriesApi.listCategories({ per_page: CATALOG_PAGE_SIZE });
      list.value = res.items;
    } finally {
      loading.value = false;
    }
  }

  return { list, loading, fetchAll };
});
