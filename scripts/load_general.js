// Ordinary traffic, to find where the service starts to hurt.
//
// Answers question 1 of the audit: at what request rate does p95 pass two
// seconds. Ramping rather than constant, because the number wanted is the
// point it degrades at, not a pass/fail at one arbitrary level.
//
//   k6 run -e BASE_URL=http://localhost:58080 \
//          -e STUDENT_PHONE=+77010000002 -e STUDENT_PASSWORD=... \
//          scripts/load_general.js

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:58080";
const errors = new Rate("request_errors");

export const options = {
  stages: [
    { duration: "30s", target: 10 },
    { duration: "30s", target: 25 },
    { duration: "30s", target: 50 },
    { duration: "30s", target: 100 },
    // Back to nothing: question 5 is whether the service recovers on its
    // own, which can only be seen after the load stops.
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    "http_req_duration{expected_response:true}": ["p(95)<2000"],
    request_errors: ["rate<0.01"],
  },
};

export function setup() {
  const res = http.post(
    `${BASE}/api/v1/auth/login`,
    JSON.stringify({ phone: __ENV.STUDENT_PHONE, password: __ENV.STUDENT_PASSWORD }),
    { headers: { "Content-Type": "application/json", Origin: BASE } },
  );
  if (res.status !== 200) throw new Error(`setup login failed: ${res.status} ${res.body}`);
  return { token: res.json("access_token") };
}

export default function (data) {
  const auth = { headers: { Authorization: `Bearer ${data.token}` } };

  // The leaderboard is first on purpose: it is the aggregate the 60-second
  // cache was added for, so this is where the cache either holds or does not.
  const responses = http.batch([
    ["GET", `${BASE}/api/v1/ent/leaderboard?period=week`, null, auth],
    ["GET", `${BASE}/api/v1/categories`, null, auth],
    ["GET", `${BASE}/api/v1/ent/subjects`, null, auth],
    ["GET", `${BASE}/api/v1/notifications/unread-count`, null, auth],
  ]);

  for (const res of responses) {
    // 429 is the limiter working, not an error.
    errors.add(res.status >= 500 || res.status === 0);
    check(res, { "no server error": (r) => r.status < 500 && r.status !== 0 });
  }
  sleep(1);
}
