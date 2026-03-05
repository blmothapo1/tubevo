import axios from 'axios';

// Access token lives in memory only — never in localStorage.
// The refresh token lives in an httpOnly cookie set by the backend.
let accessToken = localStorage.getItem('access_token');

// In dev Vite proxies /auth and /health to localhost:8000 (see vite.config.js).
// In production set VITE_API_URL to the deployed backend URL.
export const API_BASE = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,   // send httpOnly cookies on every request
});

// ── Token management ────────────────────────────────────────────
export function setAccessToken(token) {
  accessToken = token;
  if (token) {
    localStorage.setItem('access_token', token);
  } else {
    localStorage.removeItem('access_token');
  }
}

export function clearTokens() {
  accessToken = null;
  localStorage.removeItem('access_token');
  // refresh token cookie is cleared by POST /auth/logout on the backend
}

export function getAccessToken() {
  return accessToken;
}

// Keep the old name as a thin wrapper so any stragglers still compile.
export function setTokens(access, _refresh) {
  setAccessToken(access);
}

// Auth-free endpoints — never attach Authorization header to these.
const AUTH_FREE = ['/auth/login', '/auth/signup', '/auth/refresh', '/auth/forgot-password'];

// ── Request interceptor: attach Bearer token ────────────────────
api.interceptors.request.use((config) => {
  const skip = AUTH_FREE.some((p) => config.url?.endsWith(p));
  if (accessToken && !skip) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// ── Response interceptor: auto-refresh on 401 ──────────────────
let isRefreshing = false;
let failedQueue = [];

function processQueue(error, token) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token);
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;

    // Don't try to refresh for auth-free endpoints (login returns 401 on bad creds — that's expected).
    const isAuthFree = AUTH_FREE.some((p) => original.url?.endsWith(p));

    if (error.response?.status === 401 && !original._retry && !isAuthFree) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`;
          return api(original);
        });
      }

      original._retry = true;
      isRefreshing = true;

      try {
        // The httpOnly cookie is sent automatically (withCredentials).
        // Backend reads the refresh token from the cookie.
        const { data } = await axios.post(
          `${API_BASE}/auth/refresh`,
          {},
          { withCredentials: true },
        );
        setAccessToken(data.access_token);
        processQueue(null, data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch (err) {
        processQueue(err, null);
        clearTokens();
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
