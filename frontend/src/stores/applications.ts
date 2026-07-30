import { defineStore } from "pinia";
import { reactive, ref } from "vue";

import * as applicationsApi from "@/api/applications";
import type { Application } from "@/types";

interface PageState {
  page: number;
  perPage: number;
  total: number;
  pages: number;
}

function freshPageState(): PageState {
  return { page: 1, perPage: 20, total: 0, pages: 0 };
}

export const useApplicationsStore = defineStore("applications", () => {
  const myApplications = ref<Application[]>([]);
  const myApplicationsPage = reactive(freshPageState());

  const pendingForTeacher = ref<Application[]>([]);
  const pendingPage = reactive(freshPageState());

  async function apply(categoryId: number) {
    const application = await applicationsApi.applyToCategory(categoryId);
    myApplications.value = [application, ...myApplications.value];
    return application;
  }

  async function fetchMine(page = 1) {
    const res = await applicationsApi.listMyApplications({ page, per_page: myApplicationsPage.perPage });
    myApplications.value = res.items;
    myApplicationsPage.page = res.page;
    myApplicationsPage.total = res.total;
    myApplicationsPage.pages = res.pages;
  }

  async function fetchPending(page = 1) {
    const res = await applicationsApi.listPendingApplications({ page, per_page: pendingPage.perPage });
    pendingForTeacher.value = res.items;
    pendingPage.page = res.page;
    pendingPage.total = res.total;
    pendingPage.pages = res.pages;
  }

  async function decide(id: number, decision: "approve" | "reject") {
    const action = decision === "approve" ? applicationsApi.approveApplication : applicationsApi.rejectApplication;
    await action(id);
    pendingForTeacher.value = pendingForTeacher.value.filter((a) => a.id !== id);
    pendingPage.total = Math.max(0, pendingPage.total - 1);
    // A removed row can leave the current page short of a full page's worth
    // (or empty entirely) without the total page count reflecting that yet.
    if (!pendingForTeacher.value.length && pendingPage.page > 1) {
      await fetchPending(pendingPage.page - 1);
    }
  }

  return {
    myApplications,
    myApplicationsPage,
    pendingForTeacher,
    pendingPage,
    apply,
    fetchMine,
    fetchPending,
    decide,
  };
});
