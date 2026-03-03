import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { setTokens, clearTokens, getAccessToken } from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    try {
      // Use raw fetch with the current access token — avoids axios interceptors
      // that can race or redirect on stale refresh-token scenarios.
      const token = getAccessToken();
      const res = await fetch('/auth/me', {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.ok) throw new Error(res.status);
      const data = await res.json();
      setUser(data);
      return data;               // ← return so callers can inspect
    } catch {
      setUser(null);
      clearTokens();
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (getAccessToken()) {
      fetchUser();
    } else {
      setLoading(false);
    }
  }, [fetchUser]);

  async function login(email, password) {
    // Use raw fetch for login — bypasses axios interceptors which can
    // interfere when stale tokens exist in localStorage.
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed.' }));
      const error = new Error(err.detail || 'Login failed.');
      error.response = { status: res.status, data: err };
      throw error;
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    const me = await fetchUser();
    return me;                   // return the user profile, not the token blob
  }

  async function signup(email, password, full_name) {
    const res = await fetch('/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Signup failed.' }));
      const error = new Error(err.detail || 'Signup failed.');
      error.response = { status: res.status, data: err };
      throw error;
    }
    const data = await res.json();
    return data;
  }

  function logout() {
    clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, fetchUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
