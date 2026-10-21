
import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Buyers from "./pages/Buyers";
import BuyerDetails from "./pages/BuyerDetails";
import InvoiceIntelligence from "./pages/InvoiceIntelligence";

function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem("access_token")
  );

  useEffect(() => {
    const syncAuth = () => {
      const currentToken = localStorage.getItem("access_token");
      setToken((prev) => (prev !== currentToken ? currentToken : prev));
    };

    window.addEventListener("auth:login", syncAuth);
    window.addEventListener("auth:logout", syncAuth);
    window.addEventListener("auth:unauthorized", syncAuth);
    window.addEventListener("storage", syncAuth);

    return () => {
      window.removeEventListener("auth:login", syncAuth);
      window.removeEventListener("auth:logout", syncAuth);
      window.removeEventListener("auth:unauthorized", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  const isLoggedIn = Boolean(token);

  return (
    <BrowserRouter>
      <Routes>
        {/* Login */}
        <Route
          path="/login"
          element={
            isLoggedIn ? (
              <Navigate to="/" replace />
            ) : (
              <Login />
            )
          }
        />

        {/* Dashboard */}
        <Route
          path="/"
          element={
            isLoggedIn ? (
              <Dashboard />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Buyers directory */}
        <Route
          path="/buyers"
          element={
            isLoggedIn ? (
              <Buyers />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/invoices"
          element={
            isLoggedIn ? (
              <InvoiceIntelligence />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Individual buyer details and score preview */}
        <Route
          path="/buyers/:buyerId"
          element={
            isLoggedIn ? (
              <BuyerDetails />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Unknown routes */}
        <Route
          path="*"
          element={<Navigate to="/" replace />}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
