
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Buyers from "./pages/Buyers";
import BuyerDetails from "./pages/BuyerDetails";

function App() {
  const isLoggedIn = Boolean(localStorage.getItem("access_token"));

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
