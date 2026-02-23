import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api, { setTokens, clearTokens, getAccessToken } from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me');
      setUser(data);
    } catch {
      setUser(null);
      clearTokens();
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
    const { data } = await api.post('/auth/login', { email, password });
    setTokens(data.access_token, data.refresh_token);
    await fetchUser();
    return data;
  }

  async function signup(email, password, full_name) {
    const { data } = await api.post('/auth/signup', { email, password, full_name });
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
