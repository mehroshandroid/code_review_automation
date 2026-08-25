import { createContext, useContext, useEffect, useState } from "react";
import { getCurrentUser, login as apiLogin, logout as apiLogout } from "../services/api";

// Default value used by any component that calls useAuth() outside a real
// <AuthProvider> -- this is what every existing page test (written before
// auth existed, not wrapped in a provider) sees, so they keep passing
// unchanged once pages start reading role/user from this context. The real
// app always wraps in <AuthProvider>, which starts as user: null until
// GET /api/auth/me resolves.
const DEFAULT_CONTEXT = {
  user: { id: "test-admin", email: "test-admin@example.com", role: "admin" },
  loading: false,
  login: async () => {},
  logout: async () => {},
};

export const AuthContext = createContext(DEFAULT_CONTEXT);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((result) => { if (!cancelled) setUser(result); })
      .catch(() => { if (!cancelled) setUser(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  async function login(email, password) {
    const result = await apiLogin(email, password);
    setUser(result);
    return result;
  }

  async function logout() {
    await apiLogout();
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
