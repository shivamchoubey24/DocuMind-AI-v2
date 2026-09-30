import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Workspace from "./pages/Workspace.jsx";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <FullScreenSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function FullScreenSpinner() {
  return (
    <div className="h-screen w-screen flex items-center justify-center bg-slate-50">
      <div className="animate-spin h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent" />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Workspace />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
