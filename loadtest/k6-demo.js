// Load test for the demo: students browsing lessons, sitting course tests and
// mock ЕНТ exams, uploading homework, and the SPA's static files -- all at once.
//
//   k6 run -e BASE=https://edunationacademy.kz -e DATA=/data/lt.json -e VUS=200 k6-demo.js
//
// DATA is the JSON printed by prepare_users.py. Each virtual user is one
// student with their own token, so per-user limits behave as they would live.
import http from "k6/http";
import { check, group, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = __ENV.BASE || "https://edunationacademy.kz";
const API = `${BASE}/api/v1`;
const VUS = Number(__ENV.VUS || 200);
const DATA = JSON.parse(open(__ENV.DATA || "./lt.json"));
// A 2 MB "scan": the app checks the file's magic bytes, so it starts as a PDF.
const UPLOAD = (() => {
  const bytes = new Uint8Array(2 * 1024 * 1024).map((_, i) => 32 + (i % 90));
  [..."%PDF-1.4\n"].forEach((ch, i) => (bytes[i] = ch.charCodeAt(0)));
  return bytes.buffer;
})();

const shed = new Counter("shed_503");
const limited = new Counter("rate_limited_429");
const entSubmit = new Trend("ent_submit_ms", true);
const testSubmit = new Trend("test_submit_ms", true);

export const options = {
  scenarios: {
    students: {
      executor: "ramping-vus",
      stages: [
        { duration: "30s", target: Math.round(VUS / 4) },
        { duration: "60s", target: VUS },
        { duration: "120s", target: VUS },
        { duration: "20s", target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{kind:read}": ["p(95)<1500"],
    "http_req_duration{kind:write}": ["p(95)<3000"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "max"],
};

const pick = (a) => a[Math.floor(Math.random() * a.length)];

function headers() {
  const token = DATA.tokens[(__VU - 1) % DATA.tokens.length];
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

function track(res) {
  if (res.status === 503) shed.add(1);
  if (res.status === 429) limited.add(1);
  return res;
}

function get(path, h) {
  return track(http.get(`${API}${path}`, { headers: h, tags: { kind: "read", name: path.replace(/\d+/g, ":id") } }));
}

function post(path, body, h, name) {
  return track(http.post(`${API}${path}`, body, { headers: h, tags: { kind: "write", name: name || path.replace(/\d+/g, ":id") } }));
}

function answerFor(q) {
  if (q.qtype === "single" && q.choices.length) return { question_id: q.id, choice_id: pick(q.choices).id };
  if (q.qtype === "multiple" && q.choices.length) return { question_id: q.id, choice_ids: q.choices.slice(0, 2).map((c) => c.id) };
  if (q.qtype === "matching" && q.match_prompts) {
    const pairs = {};
    q.match_prompts.forEach((p, i) => (pairs[String(p.id)] = q.match_answers[i % q.match_answers.length].id));
    return { question_id: q.id, pairs };
  }
  return { question_id: q.id, text: "42" };
}

function browse(h) {
  group("browse", () => {
    get("/auth/me", h);
    const c = pick(DATA.categories);
    check(get(`/categories/${c}/sections`, h), { "sections 200": (r) => r.status === 200 });
    sleep(1 + Math.random() * 2);
    check(get(`/lessons/${pick(DATA.first_lessons)}`, h), { "lesson 200": (r) => r.status === 200 });
    sleep(1 + Math.random() * 2);
    get("/leaderboard", h);
    get("/notifications/unread-count", h);
  });
}

function courseTest(h) {
  group("course test", () => {
    const start = post(`/lessons/${pick(DATA.first_lessons)}/test/start`, "{}", h);
    if (!check(start, { "test start 200": (r) => r.status === 200 })) return;
    const session = start.json();
    sleep(3 + Math.random() * 5);
    const res = post(`/test-attempts/${session.attempt_id}/submit`, JSON.stringify({ answers: session.questions.map(answerFor) }), h);
    testSubmit.add(res.timings.duration);
    check(res, { "test submit 200": (r) => r.status === 200 });
  });
}

function ent(h) {
  group("ЕНТ", () => {
    const subjects = [pick(DATA.subjects), pick(DATA.subjects)].filter((v, i, a) => a.indexOf(v) === i);
    const start = post("/ent/simulations", JSON.stringify({ subject_ids: subjects, is_timed: true, duration_minutes: 48 * subjects.length, language: "ru" }), h);
    if (!check(start, { "ent start 201": (r) => r.status === 201 })) return;
    const sim = start.json();
    sleep(5 + Math.random() * 10);
    const res = post(`/ent/simulations/${sim.id}/submit`, JSON.stringify({ answers: sim.questions.map(answerFor) }), h);
    entSubmit.add(res.timings.duration);
    check(res, { "ent submit 200": (r) => r.status === 200 });
  });
}

function homework(h) {
  group("homework upload", () => {
    const body = { text_answer: "Нагрузочный тест", file: http.file(UPLOAD, "scan.pdf", "application/pdf") };
    const res = track(http.post(`${API}/lessons/${pick(DATA.first_lessons)}/homework`, body, {
      headers: { Authorization: h.Authorization },
      tags: { kind: "write", name: "/lessons/:id/homework" },
    }));
    check(res, { "homework 201": (r) => r.status === 201 });
  });
}

function staticFiles() {
  group("static", () => {
    const index = http.get(`${BASE}/`, { tags: { kind: "read", name: "index.html" } });
    const scripts = (index.body || "").match(/\/assets\/[^"]+\.(js|css)/g) || [];
    for (const path of scripts) {
      http.get(`${BASE}${path}`, { headers: { "Accept-Encoding": "br, gzip" }, tags: { kind: "read", name: "asset" } });
    }
  });
}

export default function () {
  const h = headers();
  const roll = Math.random();
  if (roll < 0.1) staticFiles();
  else if (roll < 0.6) browse(h);
  else if (roll < 0.8) courseTest(h);
  else if (roll < 0.95) ent(h);
  else homework(h);
  sleep(1 + Math.random() * 3);
}
