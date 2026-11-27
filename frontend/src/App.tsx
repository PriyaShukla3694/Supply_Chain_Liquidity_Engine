
import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Buyers from "./pages/Buyers";
import BuyerDetails from "./pages/BuyerDetails";
import InvoiceIntelligence from "./pages/InvoiceIntelligence";
import RiskAnalysis from "./pages/RiskAnalysis";
import Discounts from "./pages/Discounts";
import ComingSoon from "./pages/ComingSoon";

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

        {/* Risk analysis */}
        <Route
          path="/risk"
          element={
            isLoggedIn ? (
              <RiskAnalysis />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Dynamic discounts */}
        <Route
          path="/discounts"
          element={
            isLoggedIn ? (
              <Discounts />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Forecast (coming soon) */}
        <Route
          path="/forecast"
          element={
            isLoggedIn ? (
              <ComingSoon title="Cash Flow Forecast" />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* AI Assistant (coming soon) */}
        <Route
          path="/assistant"
          element={
            isLoggedIn ? (
              <ComingSoon title="AI Assistant" />
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
