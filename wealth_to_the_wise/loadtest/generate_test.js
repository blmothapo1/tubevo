import http from "k6/http";
import { check, sleep } from "k6";

/*
 * Tubevo – Authenticated generate + poll load test
 *
 * Run:
 *   k6 run -e AUTH_TOKEN=<jwt> loadtest/generate_test.js
 *
 * Override base URL:
 *   k6 run -e BASE_URL=https://api.tubevo.us -e AUTH_TOKEN=<jwt> loadtest/generate_test.js
 *
 * This test triggers a video generation and polls until it completes or
 * times out.  Use a LOW VU count (1-3) — each VU consumes one quota slot.
 */

const BASE  = __ENV.BASE_URL  || "http://localhost:8000";
const TOKEN = __ENV.AUTH_TOKEN || "";

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    http_req_duration: ["p(95)<5000"],
    http_req_failed:   ["rate<0.05"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

export default function () {
  if (!TOKEN) {
    console.error("AUTH_TOKEN env var is required.  Run with: k6 run -e AUTH_TOKEN=<jwt> ...");
    return;
  }

  // ── Step 1: Trigger generation ──────────────────────────────────
  const genRes = http.post(
    `${BASE}/api/videos/generate`,
    JSON.stringify({ topic: "k6 load test — compound interest explained" }),
    { headers },
  );

  const ok = check(genRes, {
    "generate 200": (r) => r.status === 200,
    "has video_id":  (r) => !!r.json("video_id"),
  });

  if (!ok || genRes.status !== 200) {
    console.error(`Generate failed: ${genRes.status} — ${genRes.body}`);
    return;
  }

  const videoId = genRes.json("video_id");
  console.log(`Video ID: ${videoId} — polling status...`);

  // ── Step 2: Poll status until terminal state or timeout ─────────
  const maxPolls = 60;
  const pollInterval = 5; // seconds

  for (let i = 0; i < maxPolls; i++) {
    sleep(pollInterval);

    const statusRes = http.get(`${BASE}/api/videos/${videoId}/status`, { headers });
    check(statusRes, { "status poll 200": (r) => r.status === 200 });

    const st = statusRes.json("status");
    console.log(`  Poll ${i + 1}: status=${st}`);

    if (st === "completed" || st === "posted" || st === "failed") {
      check(statusRes, {
        "terminal status reached": () => true,
      });
      return;
    }
  }

  console.warn("Polling timed out — video still generating.");
}
