import axios from 'axios';

// Hydrate from localStorage so sessions survive page refreshes.
let accessToken = localStorage.getItem('access_token');
let refreshToken = localStorage.getItem('refresh_token');

// In dev Vite proxies /auth and /health to localhost:8000 (see vite.config.js).
// In production set VITE_API_URL to the deployed backend URL.
export const API_BASE = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// ── Token management ────────────────────────────────────────────
export function setTokens(access, refresh) {
  accessToken = access;
  refreshToken = refresh;
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

export function getAccessToken() {
  return accessToken;
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

    if (error.response?.status === 401 && !original._retry && refreshToken && !isAuthFree) {
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
        const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        setTokens(data.access_token, data.refresh_token);
        processQueue(null, data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch (err) {
        processQueue(err, null);
        clearTokens();
        // Don't hard-redirect here — let the calling component decide.
        // AuthContext / ProtectedRoute / AdminRoute each handle their own redirects.
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
