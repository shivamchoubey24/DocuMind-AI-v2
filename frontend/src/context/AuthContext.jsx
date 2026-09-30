import React, { createContext, useContext, useEffect, useState } from "react";
import { fetchMe, loginUser, registerUser } from "../api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // sessionStorage (not localStorage): the token only lives for this
    // browser tab/session, so closing the browser signs the user out.
    const token = sessionStorage.getItem("documind_token");
    if (!token) {
      setLoading(false);
      return;
    }
    fetchMe()
      .then(setUser)
      .catch(() => sessionStorage.removeItem("documind_token"))
      .finally(() => setLoading(false));
  }, []);

  async function login(email, password) {
    const { access_token } = await loginUser(email, password);
    sessionStorage.setItem("documind_token", access_token);
    const me = await fetchMe();
    setUser(me);
    return me;
  }

  async function register(email, password, fullName) {
    await registerUser(email, password, fullName);
    return login(email, password);
  }

  function logout() {
    sessionStorage.removeItem("documind_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
