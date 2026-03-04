import http from "k6/http";
import { check, sleep } from "k6";

/*
 * Tubevo – Metrics endpoint load test
 *
 * Run:
 *   k6 run loadtest/metrics_test.js
 *
 * Override base URL:
 *   k6 run -e BASE_URL=https://api.tubevo.us loadtest/metrics_test.js
 */

const BASE = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  stages: [
    { duration: "10s", target: 10 },
    { duration: "20s", target: 25 },
    { duration: "10s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const res = http.get(`${BASE}/health/metrics`);
  check(res, {
    "status 200": (r) => r.status === 200,
    "has total_requests": (r) => r.json("total_requests") !== undefined,
    "has p95_ms":         (r) => r.json("p95_ms") !== undefined,
  });
  sleep(0.2);
}
