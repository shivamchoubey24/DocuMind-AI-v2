import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed. Check your credentials.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-600 via-brand-700 to-slate-900 px-4 relative overflow-hidden">
      <div className="absolute -top-24 -left-24 w-72 h-72 bg-brand-400/30 rounded-full blur-3xl" />
      <div className="absolute -bottom-24 -right-24 w-72 h-72 bg-brand-300/20 rounded-full blur-3xl" />

      <div className="w-full max-w-sm bg-white/95 backdrop-blur rounded-3xl shadow-2xl p-8 relative">
        <div className="text-center mb-7">
          <div className="w-12 h-12 mx-auto mb-3 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-2xl shadow-lg shadow-brand-600/30">
            📚
          </div>
          <h1 className="text-xl font-bold text-slate-800">Welcome back</h1>
          <p className="text-sm text-slate-500 mt-0.5">Sign in to chat with your documents</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent transition"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent transition"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 flex items-center gap-1.5">
              <span>⚠️</span>
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full bg-gradient-to-br from-brand-600 to-brand-700 hover:brightness-110 disabled:opacity-60 text-white font-medium rounded-xl py-2.5 text-sm shadow-lg shadow-brand-600/25 transition"
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="text-center text-sm text-slate-500 mt-6">
          No account?{" "}
          <Link to="/register" className="text-brand-600 font-medium hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
