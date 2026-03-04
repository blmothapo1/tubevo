import http from "k6/http";
import { check, sleep } from "k6";

/*
 * Tubevo – Health endpoint load test
 *
 * Run:
 *   k6 run loadtest/health_test.js
 *
 * Override base URL:
 *   k6 run -e BASE_URL=https://api.tubevo.us loadtest/health_test.js
 */

const BASE = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  stages: [
    { duration: "10s", target: 20 },
    { duration: "30s", target: 50 },
    { duration: "10s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<300"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const res = http.get(`${BASE}/health`);
  check(res, {
    "status 200": (r) => r.status === 200,
    "body has ok":  (r) => r.json("status") === "ok",
  });
  sleep(0.1);
}
