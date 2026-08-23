// The load test the semaphore was built for.
//
// Two scenarios run at once, and the second one is the point. Hammering the
// import endpoint on its own only tells you that the import endpoint gets
// slow. What has to be proved is that *everything else keeps working while
// it does* -- that a teacher's heavy upload cannot take the login page down
// with it. So a light login probe runs throughout, and its failure rate is
// the assertion that matters.
//
//   k6 run -e BASE_URL=http://localhost:58080 \
//          -e TEACHER_PHONE=+77010000001 -e TEACHER_PASSWORD=... \
//          -e STUDENT_PHONE=+77010000002 -e STUDENT_PASSWORD=... \
//          scripts/load_import_pdf.js

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:58080";

const importShed = new Counter("import_shed_429");
const importServerError = new Counter("import_server_error_5xx");
const importDuration = new Trend("import_duration_ms");
const loginAvailable = new Rate("login_available_during_load");
const loginDuration = new Trend("login_duration_ms");

export const options = {
  scenarios: {
    // The attack: concurrent imports, well inside the 10/hour rate limit
    // per user but with no gap between them.
    imports: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "importPdf",
    },
    // The victim: an ordinary user trying to sign in, once a second.
    login_probe: {
      executor: "constant-arrival-rate",
      rate: 1,
      timeUnit: "1s",
      duration: "120s",
      preAllocatedVUs: 5,
      exec: "loginProbe",
    },
  },
  thresholds: {
    // A shed request (429) is a success: the limiter did its job. A 5xx is
    // not -- it means a worker died or a timeout escaped as an error.
    import_server_error_5xx: ["count==0"],
    // The whole justification for the semaphore, as a number.
    login_available_during_load: ["rate>0.99"],
    "login_duration_ms": ["p(95)<2000"],
  },
};

// Built once per VU: a PDF large enough to cost real CPU, small enough to
// upload instantly. That asymmetry is the finding this test exercises --
// 0.35 MB buys ten seconds of parsing.
function heavyPdf() {
  const pages = [];
  for (let i = 1; i <= 300; i++) {
    pages.push(
      `BT /F1 9 Tf 50 800 Td (${i}. Question text with options listed below) Tj ET`,
    );
  }
  // Not a real PDF structure -- the endpoint rejects it on magic bytes
  // unless it starts with %PDF. Generating a valid multi-page PDF in k6 is
  // impractical, so point at a fixture instead when one is available.
  return open(__ENV.PDF_FIXTURE || "./fixtures/heavy.pdf", "b");
}

const PDF = heavyPdf();

function token(phone, password) {
  const res = http.post(
    `${BASE}/api/v1/auth/login`,
    JSON.stringify({ phone, password }),
    { headers: { "Content-Type": "application/json", Origin: BASE } },
  );
  return res.status === 200 ? res.json("access_token") : null;
}

export function importPdf() {
  const access = token(__ENV.TEACHER_PHONE, __ENV.TEACHER_PASSWORD);
  if (!access) {
    sleep(1);
    return;
  }

  const res = http.post(
    `${BASE}/api/v1/teacher/ent/questions/import-pdf`,
    { subject_id: __ENV.SUBJECT_ID || "1", file: http.file(PDF, "heavy.pdf", "application/pdf") },
    { headers: { Authorization: `Bearer ${access}` }, timeout: "180s" },
  );

  importDuration.add(res.timings.duration);
  if (res.status === 429) importShed.add(1);
  if (res.status >= 500) importServerError.add(1);

  check(res, {
    "import answered without a server error": (r) => r.status < 500,
    "import answered at all (no dropped connection)": (r) => r.status !== 0,
  });
}

export function loginProbe() {
  const started = Date.now();
  const res = http.post(
    `${BASE}/api/v1/auth/login`,
    JSON.stringify({ phone: __ENV.STUDENT_PHONE, password: __ENV.STUDENT_PASSWORD }),
    { headers: { "Content-Type": "application/json", Origin: BASE }, timeout: "10s" },
  );
  loginDuration.add(Date.now() - started);
  // 429 counts as available: the rate limiter answering is the service
  // working, not failing. Only a timeout, a dropped connection or a 5xx
  // means the import load reached the login path.
  loginAvailable.add(res.status === 200 || res.status === 429);
}
