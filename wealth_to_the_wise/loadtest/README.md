# Tubevo Load Tests

Lightweight load tests using [k6](https://k6.io).

## Prerequisites

Install k6:

```bash
# macOS
brew install k6

# Linux (Debian/Ubuntu)
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

## Tests

### 1. Health endpoint (no auth)

```bash
k6 run loadtest/health_test.js
```

Override the base URL for staging/production:

```bash
k6 run -e BASE_URL=https://api.tubevo.us loadtest/health_test.js
```

### 2. Metrics endpoint (no auth)

```bash
k6 run loadtest/metrics_test.js
```

### 3. Authenticated generate + poll

Requires a valid JWT token:

```bash
k6 run -e AUTH_TOKEN=eyJhbGciOi... loadtest/generate_test.js
```

Override base URL:

```bash
k6 run -e BASE_URL=https://api.tubevo.us -e AUTH_TOKEN=eyJhbGciOi... loadtest/generate_test.js
```

> **Warning:** Each VU iteration consumes one video quota slot.  Use `vus: 1` and `iterations: 1` for production.

## Pass Criteria

| Test | p95 latency | Error rate |
|------|-------------|------------|
| `health_test.js` | < 300ms | < 1% |
| `metrics_test.js` | < 500ms | < 1% |
| `generate_test.js` | < 5s (trigger) | < 5% |

k6 will exit with code 0 if all thresholds pass, non-zero otherwise.
