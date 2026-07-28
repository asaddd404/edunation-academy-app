import { defineStore } from "pinia";
import { ref } from "vue";

import * as applicationsApi from "@/api/applications";
import type { Application } from "@/types";

export const useApplicationsStore = defineStore("applications", () => {
  const myApplications = ref<Application[]>([]);
  const pendingForTeacher = ref<Application[]>([]);

  async function apply(categoryId: number) {
    const application = await applicationsApi.applyToCategory(categoryId);
    myApplications.value = [application, ...myApplications.value];
    return application;
  }

  async function fetchMine() {
    myApplications.value = await applicationsApi.listMyApplications();
  }

  async function fetchPending() {
    pendingForTeacher.value = await applicationsApi.listPendingApplications();
  }

  async function decide(id: number, decision: "approve" | "reject") {
    const action = decision === "approve" ? applicationsApi.approveApplication : applicationsApi.rejectApplication;
    await action(id);
    pendingForTeacher.value = pendingForTeacher.value.filter((a) => a.id !== id);
  }

  return { myApplications, pendingForTeacher, apply, fetchMine, fetchPending, decide };
});
