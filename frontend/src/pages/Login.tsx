
import { useState } from "react";
import { login, getCurrentUser } from "../api";

function Login() {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            // Step 1: Authenticate the user
            const data = await login(username, password);

            // Step 2: Save the access token
            localStorage.setItem("access_token", data.access_token);

            // Step 3: Fetch the authenticated user's details
            const user = await getCurrentUser(data.access_token);

            // Step 4: Save username and role
            localStorage.setItem("username", user.username);
            localStorage.setItem("role", user.role);

            // Step 5: Redirect to dashboard
            window.location.href = "/";
        } catch (err) {
            // Clear potentially stale authentication data
            localStorage.removeItem("access_token");
            localStorage.removeItem("username");
            localStorage.removeItem("role");

            setError(
                err instanceof Error ? err.message : "Login failed"
            );
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#eef3ff] p-4 md:p-6">
            <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-[1500px] overflow-hidden rounded-[32px] bg-white shadow-2xl">

                {/* LEFT VISUAL SECTION */}
                <div className="relative hidden overflow-hidden bg-[#070b18] lg:flex lg:w-[58%]">
                    <div className="absolute -left-32 -top-32 h-96 w-96 rounded-full bg-blue-600/20 blur-[100px]" />
                    <div className="absolute bottom-0 right-0 h-96 w-96 rounded-full bg-violet-600/20 blur-[100px]" />

                    {/* Brand */}
                    <div className="absolute left-10 top-9 z-20">
                        <div className="flex items-center gap-3">
                            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-xl font-bold text-white shadow-lg shadow-blue-600/30">
                                S
                            </div>

                            <div>
                                <p className="text-lg font-semibold text-white">
                                    SupplyChain AI
                                </p>
                                <p className="text-xs text-slate-400">
                                    Liquidity Intelligence Platform
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Main visual */}
                    <div className="relative z-10 flex w-full items-center justify-center px-10 pt-20">
                        <div className="relative h-[570px] w-full max-w-[700px]">

                            {/* Invoice Card */}
                            <div className="absolute left-[5%] top-[12%] w-64 -rotate-6 rounded-2xl border border-white/10 bg-white/[0.08] p-5 shadow-2xl backdrop-blur-xl">
                                <div className="mb-5 flex items-center justify-between">
                                    <span className="text-xs text-slate-400">
                                        INVOICE
                                    </span>
                                    <span className="rounded-full bg-green-400/10 px-2.5 py-1 text-[10px] font-medium text-green-400">
                                        ELIGIBLE
                                    </span>
                                </div>

                                <p className="text-2xl font-semibold text-white">
                                    ₹1,20,000
                                </p>
                                <p className="mt-1 text-xs text-slate-400">
                                    INV-1042 · Due in 18 days
                                </p>

                                <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-white/10">
                                    <div className="h-full w-[72%] rounded-full bg-blue-500" />
                                </div>
                            </div>

                            {/* Central AI Engine */}
                            <div className="absolute left-1/2 top-[25%] flex -translate-x-1/2 items-center justify-center">
                                <div className="absolute h-72 w-72 rounded-full border border-blue-500/10" />
                                <div className="absolute h-56 w-56 rounded-full border border-violet-500/10" />
                                <div className="absolute h-40 w-40 rounded-full border border-blue-400/10" />
                                <div className="absolute h-40 w-40 rounded-full bg-blue-600/20 blur-3xl" />

                                <div className="relative flex h-32 w-32 rotate-45 items-center justify-center rounded-[28px] border border-blue-400/40 bg-gradient-to-br from-blue-500 via-indigo-600 to-violet-700 shadow-2xl shadow-blue-600/40">
                                    <div className="-rotate-45 text-center">
                                        <p className="text-3xl font-bold text-white">
                                            AI
                                        </p>
                                        <p className="mt-1 text-[9px] tracking-[0.25em] text-blue-100">
                                            LIQUIDITY
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {/* Buyer Score Card */}
                            <div className="absolute right-[3%] top-[27%] w-56 rotate-6 rounded-2xl border border-white/10 bg-white/[0.08] p-5 shadow-2xl backdrop-blur-xl">
                                <div className="flex items-center justify-between">
                                    <span className="text-xs text-slate-400">
                                        BUYER SCORE
                                    </span>
                                    <span className="text-xs font-medium text-green-400">
                                        LOW RISK
                                    </span>
                                </div>

                                <div className="mt-4 flex items-end gap-2">
                                    <p className="text-4xl font-bold text-white">
                                        92
                                    </p>
                                    <span className="mb-1 text-xs text-slate-400">
                                        / 100
                                    </span>
                                </div>

                                <div className="mt-4 flex gap-1">
                                    {[1, 2, 3, 4, 5, 6, 7, 8].map((bar) => (
                                        <div
                                            key={bar}
                                            className={`h-8 flex-1 rounded-sm ${bar <= 7
                                                    ? "bg-green-400/70"
                                                    : "bg-white/10"
                                                }`}
                                        />
                                    ))}
                                </div>

                                <p className="mt-3 text-[11px] text-slate-400">
                                    Tier A · Payment reliability
                                </p>
                            </div>

                            {/* Discount Card */}
                            <div className="absolute bottom-[17%] left-[17%] w-64 rotate-3 rounded-2xl border border-white/10 bg-white/[0.09] p-5 shadow-2xl backdrop-blur-xl">
                                <div className="flex items-center justify-between">
                                    <span className="text-xs text-slate-400">
                                        RECOMMENDED DISCOUNT
                                    </span>
                                    <span className="text-green-400">↗</span>
                                </div>

                                <div className="mt-4 flex items-end justify-between">
                                    <div>
                                        <p className="text-4xl font-bold text-white">
                                            1.5%
                                        </p>
                                        <p className="mt-1 text-xs text-slate-400">
                                            Tier A offer
                                        </p>
                                    </div>

                                    <div className="rounded-xl bg-green-400/10 px-3 py-2 text-right">
                                        <p className="text-xs text-green-400">
                                            Savings
                                        </p>
                                        <p className="font-semibold text-green-300">
                                            ₹1,800
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {/* Liquidity Flow */}
                            <div className="absolute bottom-[12%] right-[7%] w-56">
                                <div className="flex items-center gap-2">
                                    <div className="h-2 w-2 rounded-full bg-blue-400 shadow-lg shadow-blue-400/70" />
                                    <div className="h-px flex-1 bg-gradient-to-r from-blue-400/70 to-violet-400/10" />
                                    <div className="h-2 w-2 rounded-full bg-violet-400 shadow-lg shadow-violet-400/70" />
                                </div>

                                <p className="mt-2 text-right text-[10px] tracking-widest text-slate-500">
                                    CASH FLOW · RISK · DISCOUNT
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Bottom Text */}
                    <div className="absolute bottom-9 left-10 z-20 max-w-md">
                        <p className="text-sm font-medium text-blue-400">
                            SMARTER WORKING CAPITAL
                        </p>

                        <h2 className="mt-2 text-3xl font-semibold leading-tight text-white">
                            Turn payment risk into
                            <span className="text-blue-400">
                                {" "}liquidity.
                            </span>
                        </h2>

                        <p className="mt-3 text-sm leading-6 text-slate-400">
                            AI-powered payment risk, buyer intelligence and
                            dynamic early-payment discounting in one platform.
                        </p>
                    </div>
                </div>

                {/* RIGHT LOGIN SECTION */}
                <div className="flex w-full items-center justify-center px-6 py-10 sm:px-12 lg:w-[42%] lg:px-16">
                    <div className="w-full max-w-md">

                        {/* Mobile Brand */}
                        <div className="mb-10 flex items-center gap-3 lg:hidden">
                            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 font-bold text-white">
                                S
                            </div>

                            <div>
                                <p className="font-semibold text-slate-900">
                                    SupplyChain AI
                                </p>
                                <p className="text-xs text-slate-500">
                                    Liquidity Intelligence Platform
                                </p>
                            </div>
                        </div>

                        {/* Heading */}
                        <div className="mb-10">
                            <p className="mb-3 text-sm font-medium text-blue-600">
                                Welcome back
                            </p>

                            <h1 className="text-4xl font-bold tracking-tight text-slate-950">
                                Sign in to your
                                <br />
                                workspace
                            </h1>

                            <p className="mt-3 text-sm leading-6 text-slate-500">
                                Access your invoices, buyer risk, liquidity
                                forecasts and discount recommendations.
                            </p>
                        </div>

                        {/* Login Form */}
                        <form onSubmit={handleSubmit} className="space-y-6">

                            {/* Username */}
                            <div>
                                <label className="mb-2 block text-sm font-medium text-slate-700">
                                    Username
                                </label>

                                <input
                                    type="text"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    placeholder="Enter your username"
                                    autoComplete="username"
                                    required
                                    className="h-14 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-500/10"
                                />
                            </div>

                            {/* Password */}
                            <div>
                                <div className="mb-2 flex items-center justify-between">
                                    <label className="block text-sm font-medium text-slate-700">
                                        Password
                                    </label>

                                    <button
                                        type="button"
                                        className="text-xs font-medium text-blue-600 transition hover:text-blue-700"
                                    >
                                        Forgot password?
                                    </button>
                                </div>

                                <div className="relative">
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="Enter your password"
                                        autoComplete="current-password"
                                        required
                                        className="h-14 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 pr-12 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-500/10"
                                    />

                                    {/* Show/Hide Password */}
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-slate-700"
                                        aria-label={
                                            showPassword
                                                ? "Hide password"
                                                : "Show password"
                                        }
                                    >
                                        {showPassword ? (
                                            <svg
                                                xmlns="http://www.w3.org/2000/svg"
                                                fill="none"
                                                viewBox="0 0 24 24"
                                                strokeWidth={1.8}
                                                stroke="currentColor"
                                                className="h-5 w-5"
                                            >
                                                <path
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    d="M3.98 8.5C2.74 10.17 2 12 2 12s3.58 6 10 6c1.88 0 3.45-.43 4.75-1.05M6.23 6.23C7.82 5.1 9.72 4.5 12 4.5c6.42 0 10 7.5 10 7.5s-.74 1.83-1.98 3.5M9.88 9.88a3 3 0 104.24 4.24M3 3l18 18"
                                                />
                                            </svg>
                                        ) : (
                                            <svg
                                                xmlns="http://www.w3.org/2000/svg"
                                                fill="none"
                                                viewBox="0 0 24 24"
                                                strokeWidth={1.8}
                                                stroke="currentColor"
                                                className="h-5 w-5"
                                            >
                                                <path
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    d="M2.25 12s3.75-6 9.75-6 9.75 6 9.75 6-3.75 6-9.75 6-9.75-6-9.75-6z"
                                                />
                                                <circle cx="12" cy="12" r="2.75" />
                                            </svg>
                                        )}
                                    </button>
                                </div>
                            </div>

                            {/* Error */}
                            {error && (
                                <div
                                    role="alert"
                                    className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600"
                                >
                                    {error}
                                </div>
                            )}

                            {/* Sign In Button */}
                            <button
                                type="submit"
                                disabled={loading}
                                className="group relative h-14 w-full overflow-hidden rounded-xl bg-slate-950 font-semibold text-white shadow-xl shadow-slate-950/20 transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                                <span className="relative z-10">
                                    {loading ? "Signing in..." : "Sign in"}
                                </span>

                                {!loading && (
                                    <span className="absolute right-5 top-1/2 -translate-y-1/2 text-lg transition-transform group-hover:translate-x-1">
                                        →
                                    </span>
                                )}
                            </button>
                        </form>

                        {/* Security Note */}
                        <div className="mt-8 flex items-start gap-3 rounded-xl bg-slate-50 p-4">
                            <div className="mt-0.5 text-sm text-green-600">
                                ●
                            </div>

                            <div>
                                <p className="text-xs font-medium text-slate-700">
                                    Secure workspace
                                </p>
                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                    Your session is protected with secure
                                    token-based authentication.
                                </p>
                            </div>
                        </div>

                        {/* Footer */}
                        <p className="mt-8 text-center text-xs text-slate-400">
                            AI-Driven Dynamic Discounting & Supply Chain
                            Liquidity Engine
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Login;
