import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
    Activity,
    ArrowDownRight,
    ArrowUpRight,
    BadgePercent,
    Bell,
    Bot,
    CheckCircle2,
    ChevronDown,
    Clock3,
    CircleDollarSign,
    FileText,
    LayoutDashboard,
    LogOut,
    Menu,
    MoreHorizontal,
    Search,
    Settings,
    ShieldAlert,
    TrendingUp,
    Users,
    Wallet,
    X,
} from "lucide-react";

import {
    getCurrentUser,
    getDashboardSummary,
    getDashboardInvoices,
    getBuyerScore,
    logout,
    type DashboardSummary,
    type DashboardInvoice,
    type BuyerScore,
    type UserProfile,
} from "../api";

const navigation = [
    { label: "Dashboard", icon: LayoutDashboard, path: "/" },
    { label: "Invoices", icon: FileText, path: "/invoices" },
    { label: "Buyers", icon: Users, path: "/buyers" },
    { label: "Risk Analysis", icon: ShieldAlert, path: "/risk" },
    { label: "Forecast", icon: TrendingUp, path: "/forecast" },
    { label: "Discounts", icon: BadgePercent, path: "/discounts" },
    { label: "AI Assistant", icon: Bot, path: "/assistant" },
];

const chartValues = [
    32, 42, 36, 48, 43, 58, 49, 63, 54, 68, 61, 75,
    65, 70, 57, 67, 73, 62, 80, 71, 85, 75, 90, 82,
];

function LiquidityChart() {
    const points = chartValues
        .map((value, index) => {
            const x = (index / (chartValues.length - 1)) * 700;
            const y = 180 - value * 1.65;
            return `${x},${y}`;
        })
        .join(" ");

    return (
        <div className="mt-5">
            <div className="flex flex-wrap gap-5 text-xs text-slate-400">
                <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-blue-400" />
                    Eligible invoice value
                </span>
                <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-violet-400" />
                    Discount budget
                </span>
            </div>

            <svg
                viewBox="0 0 700 205"
                className="mt-4 h-auto w-full"
                role="img"
                aria-label="Illustrative liquidity trend chart"
            >
                <defs>
                    <linearGradient
                        id="liquidityFill"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                    >
                        <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.28" />
                        <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
                    </linearGradient>
                </defs>

                {[20, 60, 100, 140, 180].map((y) => (
                    <line
                        key={y}
                        x1="0"
                        y1={y}
                        x2="700"
                        y2={y}
                        stroke="#253249"
                        strokeDasharray="4 6"
                    />
                ))}

                <polygon
                    points={`0,180 ${points} 700,180`}
                    fill="url(#liquidityFill)"
                />

                <polyline
                    points={points}
                    fill="none"
                    stroke="#60A5FA"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />

                {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                    (day, index) => (
                        <text
                            key={day}
                            x={index * (700 / 6)}
                            y="202"
                            fill="#64748B"
                            fontSize="10"
                            textAnchor={
                                index === 0
                                    ? "start"
                                    : index === 6
                                        ? "end"
                                        : "middle"
                            }
                        >
                            {day}
                        </text>
                    )
                )}
            </svg>

            <p className="mt-3 text-xs text-slate-500">
                Illustrative chart only. Historical time-series API is not yet
                available.
            </p>
        </div>
    );
}

function formatINR(value: string | number): string {
    const amount = Number(value);

    if (!Number.isFinite(amount)) return "₹0";

    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0,
    }).format(amount);
}

function formatDate(value: string): string {
    if (!value) return "—";

    const date = new Date(`${value}T00:00:00`);

    if (Number.isNaN(date.getTime())) return value;

    return date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

function getStatusStyle(status: string): string {
    switch (status.toLowerCase()) {
        case "eligible":
            return "bg-emerald-500/10 text-emerald-300";
        case "settled":
            return "bg-blue-500/10 text-blue-300";
        case "disputed":
            return "bg-rose-500/10 text-rose-300";
        default:
            return "bg-amber-500/10 text-amber-300";
    }
}

export default function Dashboard() {
    const navigate = useNavigate();

    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [profileOpen, setProfileOpen] = useState(false);
    const [period, setPeriod] = useState("7 days");
    const [search, setSearch] = useState("");

    const [summary, setSummary] = useState<DashboardSummary | null>(null);
    const [invoices, setInvoices] = useState<DashboardInvoice[]>([]);
    const [profile, setProfile] = useState<UserProfile | null>(null);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // Buyer Score Preview states
    const [buyerId, setBuyerId] = useState("0187-ERLSR");
    const [scoreDate, setScoreDate] = useState("2015-04-15");
    const [buyerScore, setBuyerScore] = useState<BuyerScore | null>(null);
    const [scoreLoading, setScoreLoading] = useState(false);
    const [scoreError, setScoreError] = useState("");

    const username =
        profile?.username ||
        localStorage.getItem("username") ||
        "Workspace User";

    const role =
        profile?.role ||
        localStorage.getItem("role") ||
        "User";

    const initial = username.charAt(0).toUpperCase() || "U";

    const loadDashboard = useCallback(async () => {
        const token = localStorage.getItem("access_token");

        if (!token) {
            navigate("/login", { replace: true });
            return;
        }

        setLoading(true);
        setError("");

        try {
            const [summaryData, invoiceData, userData] = await Promise.all([
                getDashboardSummary(token),
                getDashboardInvoices(token, 10),
                getCurrentUser(token),
            ]);

            setSummary(summaryData);
            setInvoices(invoiceData);
            setProfile(userData);

            localStorage.setItem("username", userData.username);
            localStorage.setItem("role", userData.role);
        } catch (err) {
            const message =
                err instanceof Error
                    ? err.message
                    : "Unable to load dashboard data.";

            if (
                message.toLowerCase().includes("session expired") ||
                message.toLowerCase().includes("401") ||
                message.toLowerCase().includes("not authenticated")
            ) {
                logout();
                navigate("/login", { replace: true });
                return;
            }

            setError(message);
        } finally {
            setLoading(false);
        }
    }, [navigate]);

    useEffect(() => {
        void loadDashboard();
    }, [loadDashboard]);

    function handleLogout() {
        logout();
        setProfileOpen(false);
        navigate("/login", { replace: true });
    }

    async function handleBuyerScorePreview() {
        const token = localStorage.getItem("access_token");

        if (!token) {
            navigate("/login", { replace: true });
            return;
        }

        if (!buyerId.trim()) {
            setScoreError("Please enter a buyer ID.");
            setBuyerScore(null);
            return;
        }

        if (!scoreDate) {
            setScoreError("Please select an as-of date.");
            setBuyerScore(null);
            return;
        }

        setScoreLoading(true);
        setScoreError("");
        setBuyerScore(null);

        try {
            const result = await getBuyerScore(
                token,
                buyerId.trim(),
                scoreDate
            );

            setBuyerScore(result);
        } catch (err) {
            const message =
                err instanceof Error
                    ? err.message
                    : "Unable to load buyer score.";

            if (
                message.toLowerCase().includes("session expired") ||
                message.toLowerCase().includes("401") ||
                message.toLowerCase().includes("not authenticated")
            ) {
                logout();
                navigate("/login", { replace: true });
                return;
            }

            setScoreError(message);
        } finally {
            setScoreLoading(false);
        }
    }

    const filteredInvoices = useMemo(() => {
        const query = search.trim().toLowerCase();

        if (!query) return invoices;

        return invoices.filter((invoice) =>
            [
                invoice.invoice_id,
                invoice.buyer_id,
                invoice.invoice_amount,
                invoice.tier ?? "",
                invoice.invoice_status,
                invoice.eligibility_status,
            ]
                .join(" ")
                .toLowerCase()
                .includes(query)
        );
    }, [invoices, search]);

    const kpis = [
        {
            label: "Eligible Invoice Value",
            value: formatINR(summary?.eligible_invoice_value ?? 0),
            change: `${summary?.eligible_invoice_count ?? 0} eligible invoices`,
            icon: Wallet,
            color: "text-blue-400",
            bg: "bg-blue-500/10",
        },
        {
            label: "Historical Late Rate",
            value: `${summary?.historical_late_rate ?? 0}%`,
            change: "Based on settled invoices",
            icon: Clock3,
            color: "text-amber-400",
            bg: "bg-amber-500/10",
        },
        {
            label: "Weekly Discount Budget",
            value: formatINR(summary?.weekly_discount_budget ?? 0),
            change: "Calculated policy budget",
            icon: CircleDollarSign,
            color: "text-violet-400",
            bg: "bg-violet-500/10",
        },
        {
            label: "Total Buyers",
            value: String(summary?.total_buyers ?? 0),
            change: "Across available buyer records",
            icon: Users,
            color: "text-emerald-400",
            bg: "bg-emerald-500/10",
        },
    ];

    const tierColors: Record<string, string> = {
        A: "bg-blue-400",
        B: "bg-violet-400",
        C: "bg-amber-400",
    };

    const tierTextColors: Record<string, string> = {
        A: "text-blue-300",
        B: "text-violet-300",
        C: "text-amber-300",
    };

    const totalBuyers = summary?.total_buyers ?? 0;

    return (
        <div className="min-h-screen bg-[#0B1120] text-slate-100">
            {sidebarOpen && (
                <button
                    aria-label="Close sidebar overlay"
                    onClick={() => setSidebarOpen(false)}
                    className="fixed inset-0 z-40 bg-black/60 lg:hidden"
                />
            )}

            <aside
                className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-800 bg-[#0D1628] transition-transform duration-300 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
                    } lg:translate-x-0`}
            >
                <div className="flex h-[76px] items-center justify-between border-b border-slate-800 px-5">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600">
                            <Activity size={22} />
                        </div>
                        <div>
                            <h1 className="text-sm font-bold tracking-wide">
                                LIQUIDITY
                            </h1>
                            <p className="text-[10px] tracking-[0.2em] text-blue-400">
                                ENGINE
                            </p>
                        </div>
                    </div>

                    <button
                        onClick={() => setSidebarOpen(false)}
                        className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 lg:hidden"
                        aria-label="Close navigation"
                    >
                        <X size={20} />
                    </button>
                </div>

                <div className="px-4 pb-2 pt-7">
                    <p className="px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                        Workspace
                    </p>
                </div>

                <nav className="flex-1 space-y-1 px-3">
                    {navigation.map(({ label, icon: Icon, path }) => (
                        <NavLink
                            key={label}
                            to={path}
                            end={path === "/"}
                            onClick={() => setSidebarOpen(false)}
                            className={({ isActive }) =>
                                `group flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition ${isActive
                                    ? "border border-blue-500/20 bg-blue-500/10 font-medium text-blue-400"
                                    : "text-slate-400 hover:bg-slate-800/70 hover:text-white"
                                }`
                            }
                        >
                            <Icon size={18} />
                            <span>{label}</span>
                            {label === "Risk Analysis" && (
                                <span className="ml-auto h-2 w-2 rounded-full bg-amber-400" />
                            )}
                        </NavLink>
                    ))}
                </nav>

                <div className="mx-4 mb-4 rounded-xl border border-blue-500/20 bg-blue-500/[0.06] p-4">
                    <div className="flex items-center gap-2">
                        <Bot size={18} className="text-blue-400" />
                        <p className="text-xs font-semibold">AI Insights</p>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-400">
                        Review buyer risk and discount eligibility in one place.
                    </p>
                    <NavLink
                        to="/assistant"
                        className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-400"
                    >
                        Explore assistant <ArrowUpRight size={13} />
                    </NavLink>
                </div>

                <div className="border-t border-slate-800 p-3">
                    <button
                        onClick={() =>
                            alert("Settings page integration is pending.")
                        }
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm text-slate-400 hover:bg-slate-800 hover:text-white"
                    >
                        <Settings size={18} />
                        Settings
                    </button>

                    <div className="mt-2 flex items-center gap-3 rounded-xl bg-slate-800/60 p-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold">
                            {initial}
                        </div>
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">
                                {username}
                            </p>
                            <p className="truncate text-xs text-slate-500">
                                {role}
                            </p>
                        </div>
                        <MoreHorizontal size={18} className="text-slate-500" />
                    </div>
                </div>
            </aside>

            <main className="min-h-screen lg:pl-64">
                <header className="sticky top-0 z-30 flex h-[76px] items-center justify-between gap-3 border-b border-slate-800 bg-[#0B1120]/95 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
                    <div className="flex min-w-0 items-center gap-3">
                        <button
                            onClick={() => setSidebarOpen(true)}
                            className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:bg-slate-800 lg:hidden"
                            aria-label="Open navigation"
                        >
                            <Menu size={20} />
                        </button>

                        <div className="min-w-0">
                            <div className="flex items-center gap-2 text-xs text-slate-500">
                                <span>Workspace</span>
                                <span>/</span>
                                <span className="text-blue-400">Dashboard</span>
                            </div>
                            <h2 className="mt-1 truncate text-lg font-semibold sm:text-xl">
                                Overview
                            </h2>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 sm:gap-4">
                        <div className="hidden items-center gap-2 rounded-xl border border-slate-700 bg-[#111C30] px-3 py-2 md:flex">
                            <Search size={16} className="text-slate-500" />
                            <input
                                aria-label="Search invoices"
                                placeholder="Search invoices..."
                                value={search}
                                onChange={(event) =>
                                    setSearch(event.target.value)
                                }
                                className="w-36 bg-transparent text-xs text-white outline-none placeholder:text-slate-500"
                            />
                        </div>

                        <button
                            aria-label="Notifications"
                            onClick={() =>
                                alert("Notifications integration is pending.")
                            }
                            className="relative rounded-xl border border-slate-700 p-2.5 text-slate-400 hover:bg-slate-800"
                        >
                            <Bell size={18} />
                            <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-blue-400" />
                        </button>

                        <div className="hidden h-8 w-px bg-slate-800 sm:block" />

                        <div className="relative">
                            <button
                                aria-label={`Signed in as ${username}`}
                                aria-expanded={profileOpen}
                                onClick={() => setProfileOpen((open) => !open)}
                                className="flex items-center gap-2 rounded-xl px-1 py-1 hover:bg-slate-800"
                            >
                                <div className="flex h-9 w-9 items-center justify-center rounded-full border border-blue-400/30 bg-blue-500/15 text-sm font-semibold text-blue-300">
                                    {initial}
                                </div>
                                <ChevronDown
                                    size={15}
                                    className="hidden text-slate-400 sm:block"
                                />
                            </button>

                            {profileOpen && (
                                <>
                                    <button
                                        aria-label="Close profile menu"
                                        className="fixed inset-0 z-40 cursor-default"
                                        onClick={() => setProfileOpen(false)}
                                    />

                                    <div className="absolute right-0 top-full z-50 mt-2 w-56 rounded-xl border border-slate-700 bg-[#111C30] p-2 shadow-xl">
                                        <div className="border-b border-slate-700 px-3 py-2">
                                            <p className="truncate text-sm font-medium text-white">
                                                {username}
                                            </p>
                                            <p className="truncate text-xs text-slate-400">
                                                {role}
                                            </p>
                                        </div>

                                        <button
                                            onClick={handleLogout}
                                            className="mt-2 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-rose-300 hover:bg-rose-500/10"
                                        >
                                            <LogOut size={16} />
                                            Log out
                                        </button>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </header>

                <div className="mx-auto max-w-[1600px] space-y-6 p-4 sm:p-6 lg:p-8">
                    <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                        <div>
                            <div className="flex items-center gap-2">
                                <span className="h-2 w-2 rounded-full bg-blue-400" />
                                <p className="text-xs font-medium uppercase tracking-[0.18em] text-blue-400">
                                    Finance intelligence
                                </p>
                            </div>
                            <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
                                Dashboard Overview
                            </h1>
                            <p className="mt-2 text-sm text-slate-400">
                                Monitor invoice liquidity, buyer risk and
                                discount opportunities.
                            </p>
                        </div>

                        <div className="flex items-center gap-3">
                            <span
                                className={`rounded-lg border px-3 py-2 text-xs ${error
                                        ? "border-rose-500/20 bg-rose-500/[0.06] text-rose-300"
                                        : "border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-300"
                                    }`}
                            >
                                {error ? "Connection issue" : "Live API"}
                            </span>

                            <NavLink
                                to="/discounts"
                                className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-500"
                            >
                                <BadgePercent size={16} />
                                View discounts
                            </NavLink>
                        </div>
                    </section>

                    {error && (
                        <section
                            role="alert"
                            className="rounded-xl border border-rose-500/30 bg-rose-500/[0.06] p-4"
                        >
                            <p className="text-sm font-medium text-rose-300">
                                Dashboard data could not be loaded.
                            </p>
                            <p className="mt-1 break-words text-sm text-slate-300">
                                {error}
                            </p>
                            <button
                                onClick={() => void loadDashboard()}
                                className="mt-3 rounded-lg bg-rose-500/15 px-3 py-2 text-sm text-rose-200 hover:bg-rose-500/25"
                            >
                                Retry
                            </button>
                        </section>
                    )}

                    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                        {kpis.map((kpi, index) => {
                            const Icon = kpi.icon;

                            return (
                                <div
                                    key={kpi.label}
                                    className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 transition hover:border-blue-500/30"
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <p className="text-sm text-slate-400">
                                                {kpi.label}
                                            </p>
                                            <p className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
                                                {loading ? "…" : kpi.value}
                                            </p>
                                        </div>
                                        <div
                                            className={`flex h-11 w-11 items-center justify-center rounded-xl ${kpi.bg} ${kpi.color}`}
                                        >
                                            <Icon size={21} />
                                        </div>
                                    </div>

                                    <div className="mt-5 flex items-center gap-2 border-t border-slate-800 pt-4">
                                        {index === 1 ? (
                                            <ArrowDownRight
                                                size={15}
                                                className="text-amber-400"
                                            />
                                        ) : (
                                            <ArrowUpRight
                                                size={15}
                                                className="text-blue-400"
                                            />
                                        )}
                                        <span className="text-xs text-slate-400">
                                            {loading ? "Loading…" : kpi.change}
                                        </span>
                                    </div>
                                </div>
                            );
                        })}
                    </section>

                    <section className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                        <div className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 sm:p-6 xl:col-span-2">
                            <div className="flex flex-wrap items-start justify-between gap-4">
                                <div>
                                    <h3 className="font-semibold">
                                        Liquidity Overview
                                    </h3>
                                    <p className="mt-1 text-xs text-slate-500">
                                        Illustrative weekly trend
                                    </p>
                                </div>

                                <select
                                    value={period}
                                    onChange={(event) =>
                                        setPeriod(event.target.value)
                                    }
                                    className="rounded-lg border border-slate-700 bg-[#0B1120] px-3 py-2 text-xs text-slate-300 outline-none focus:border-blue-500"
                                    aria-label="Chart time period"
                                >
                                    <option>7 days</option>
                                    <option>30 days</option>
                                    <option>90 days</option>
                                </select>
                            </div>

                            <div className="mt-5 flex items-end gap-3">
                                <p className="text-3xl font-bold">
                                    {loading
                                        ? "…"
                                        : formatINR(
                                            summary?.eligible_invoice_value ?? 0
                                        )}
                                </p>
                                <span className="mb-1 rounded-md bg-blue-500/10 px-2 py-1 text-xs text-blue-300">
                                    Eligible value
                                </span>
                            </div>

                            <LiquidityChart />
                            <p className="mt-2 text-xs text-slate-500">
                                Selected period: {period}
                            </p>
                        </div>

                        <div className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 sm:p-6">
                            <div>
                                <h3 className="font-semibold">Buyer Risk Tiers</h3>
                                <p className="mt-1 text-xs text-slate-500">
                                    Based on buyer records from the API
                                </p>
                            </div>

                            <div className="mt-7 flex justify-center">
                                <div
                                    className="relative flex h-44 w-44 items-center justify-center rounded-full"
                                    style={{
                                        background:
                                            totalBuyers > 0
                                                ? `conic-gradient(#60A5FA 0% ${summary?.buyer_tiers.A
                                                    ?.percentage ?? 0
                                                }%, #A78BFA ${summary?.buyer_tiers.A
                                                    ?.percentage ?? 0
                                                }% ${(summary?.buyer_tiers.A
                                                    ?.percentage ?? 0) +
                                                (summary?.buyer_tiers.B
                                                    ?.percentage ?? 0)
                                                }%, #FBBF24 ${(summary?.buyer_tiers.A
                                                    ?.percentage ?? 0) +
                                                (summary?.buyer_tiers.B
                                                    ?.percentage ?? 0)
                                                }% 100%)`
                                                : "#1E293B",
                                    }}
                                >
                                    <div className="flex h-32 w-32 flex-col items-center justify-center rounded-full bg-[#111C30]">
                                        <span className="text-3xl font-bold">
                                            {loading ? "…" : totalBuyers}
                                        </span>
                                        <span className="mt-1 text-xs text-slate-400">
                                            Total buyers
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-7 space-y-4">
                                {(["A", "B", "C"] as const).map((tier) => {
                                    const item = summary?.buyer_tiers[tier];
                                    const count = item?.count ?? 0;
                                    const percentage = item?.percentage ?? 0;

                                    return (
                                        <div key={tier}>
                                            <div className="mb-2 flex items-center justify-between gap-2">
                                                <div className="flex items-center gap-2">
                                                    <span
                                                        className={`h-2.5 w-2.5 rounded-full ${tierColors[tier]}`}
                                                    />
                                                    <span className="text-sm">
                                                        Tier {tier}
                                                    </span>
                                                </div>
                                                <span className="text-xs text-slate-400">
                                                    {loading
                                                        ? "…"
                                                        : `${count} · ${percentage}%`}
                                                </span>
                                            </div>
                                            <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                                                <div
                                                    className={`h-full rounded-full ${tierColors[tier]}`}
                                                    style={{
                                                        width: `${Math.min(
                                                            percentage,
                                                            100
                                                        )}%`,
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </section>

                    {/* Buyer Score Preview */}
                    <section className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 sm:p-6">
                        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                            <div>
                                <h3 className="font-semibold">
                                    Buyer Score Preview
                                </h3>
                                <p className="mt-1 text-xs text-slate-400">
                                    Preview buyer risk scores for a selected
                                    historical date. This action does not save
                                    scores to the database.
                                </p>
                            </div>

                            <span className="w-fit rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-300">
                                Read-only
                            </span>
                        </div>

                        <form
                            className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_190px_auto]"
                            onSubmit={(event) => {
                                event.preventDefault();
                                void handleBuyerScorePreview();
                            }}
                        >
                            <div>
                                <label
                                    htmlFor="buyer-score-id"
                                    className="mb-2 block text-xs font-medium text-slate-300"
                                >
                                    Buyer ID
                                </label>
                                <input
                                    id="buyer-score-id"
                                    value={buyerId}
                                    onChange={(event) =>
                                        setBuyerId(event.target.value)
                                    }
                                    placeholder="Enter buyer ID"
                                    className="w-full rounded-xl border border-slate-700 bg-[#0B1120] px-3 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-blue-500"
                                />
                            </div>

                            <div>
                                <label
                                    htmlFor="buyer-score-date"
                                    className="mb-2 block text-xs font-medium text-slate-300"
                                >
                                    Calculate as of
                                </label>
                                <input
                                    id="buyer-score-date"
                                    type="date"
                                    value={scoreDate}
                                    onChange={(event) =>
                                        setScoreDate(event.target.value)
                                    }
                                    className="w-full rounded-xl border border-slate-700 bg-[#0B1120] px-3 py-3 text-sm text-white outline-none focus:border-blue-500"
                                />
                            </div>

                            <div className="flex items-end">
                                <button
                                    type="submit"
                                    disabled={scoreLoading}
                                    className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                                >
                                    {scoreLoading
                                        ? "Calculating…"
                                        : "Preview score"}
                                </button>
                            </div>
                        </form>

                        {scoreError && (
                            <div
                                role="alert"
                                className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/[0.06] p-3 text-sm text-rose-300"
                            >
                                {scoreError}
                            </div>
                        )}

                        {buyerScore && (
                            <div className="mt-6">
                                <div className="flex flex-col justify-between gap-3 rounded-xl border border-slate-700 bg-[#0D1729] p-4 sm:flex-row sm:items-center">
                                    <div>
                                        <p className="text-xs text-slate-400">
                                            Buyer
                                        </p>
                                        <p className="mt-1 break-all font-semibold text-white">
                                            {buyerScore.buyer_id}
                                        </p>
                                        <p className="mt-1 text-xs text-slate-500">
                                            As of {formatDate(buyerScore.as_of_date)}
                                        </p>
                                    </div>

                                    <div className="flex items-center gap-3">
                                        <div className="text-right">
                                            <p className="text-xs text-slate-400">
                                                Overall score
                                            </p>
                                            <p className="mt-1 text-3xl font-bold text-white">
                                                {buyerScore.overall_score == null
                                                    ? "—"
                                                    : buyerScore.overall_score.toFixed(2)}
                                            </p>
                                        </div>

                                        <span
                                            className={`rounded-xl px-3 py-2 text-sm font-semibold ${buyerScore.tier === "A"
                                                    ? "bg-blue-500/10 text-blue-300"
                                                    : buyerScore.tier === "B"
                                                        ? "bg-violet-500/10 text-violet-300"
                                                        : buyerScore.tier === "C"
                                                            ? "bg-amber-500/10 text-amber-300"
                                                            : "bg-slate-700 text-slate-300"
                                                }`}
                                        >
                                            {buyerScore.tier
                                                ? `Tier ${buyerScore.tier}`
                                                : "No tier"}
                                        </span>
                                    </div>
                                </div>

                                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                                    {[
                                        {
                                            label: "Reliability",
                                            value: buyerScore.reliability_score,
                                            description: "Payment behaviour",
                                            color: "text-blue-300",
                                        },
                                        {
                                            label: "Financial health",
                                            value: buyerScore.financial_score,
                                            description: "Credit limit and exposure",
                                            color: "text-violet-300",
                                        },
                                        {
                                            label: "Liquidity health",
                                            value: buyerScore.liquidity_score,
                                            description: "Overdue exposure",
                                            color: "text-emerald-300",
                                        },
                                    ].map((item) => (
                                        <div
                                            key={item.label}
                                            className="rounded-xl border border-slate-800 bg-[#0D1729] p-4"
                                        >
                                            <p className="text-sm text-slate-300">
                                                {item.label}
                                            </p>
                                            <p
                                                className={`mt-3 text-2xl font-bold ${item.color}`}
                                            >
                                                {item.value == null
                                                    ? "—"
                                                    : item.value.toFixed(2)}
                                            </p>
                                            <p className="mt-1 text-xs text-slate-500">
                                                {item.description}
                                            </p>
                                        </div>
                                    ))}
                                </div>

                                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                                    {[
                                        {
                                            label: "Resolved invoices",
                                            value: String(
                                                buyerScore.resolved_invoice_count
                                            ),
                                        },
                                        {
                                            label: "Open exposure",
                                            value: formatINR(
                                                buyerScore.open_exposure
                                            ),
                                        },
                                        {
                                            label: "Overdue exposure",
                                            value: formatINR(
                                                buyerScore.overdue_open_exposure
                                            ),
                                        },
                                        {
                                            label: "Credit limit",
                                            value: formatINR(
                                                buyerScore.credit_limit
                                            ),
                                        },
                                    ].map((item) => (
                                        <div
                                            key={item.label}
                                            className="rounded-xl border border-slate-800 p-3"
                                        >
                                            <p className="text-xs text-slate-500">
                                                {item.label}
                                            </p>
                                            <p className="mt-2 break-words text-sm font-semibold text-slate-200">
                                                {item.value}
                                            </p>
                                        </div>
                                    ))}
                                </div>

                                <div className="mt-4 rounded-xl border border-slate-800 bg-[#0D1729] p-4">
                                    <p className="text-sm font-medium text-slate-200">
                                        Score status
                                    </p>
                                    <p className="mt-2 text-sm text-slate-400">
                                        {buyerScore.status === "calculated"
                                            ? "Score calculated using the available settled and open invoice records."
                                            : buyerScore.status === "provisional"
                                                ? "Provisional Tier B: fewer than five resolved invoices are available."
                                                : "Scoring is blocked pending a valid credit-limit decision."}
                                    </p>
                                    <p className="mt-2 text-xs text-slate-500">
                                        Tier basis: {buyerScore.tier_basis}
                                        {" · "}Late rate:{" "}
                                        {(buyerScore.late_rate * 100).toFixed(2)}%
                                        {" · "}Average days late:{" "}
                                        {buyerScore.avg_days_late.toFixed(2)}
                                        {" · "}Last five late rate:{" "}
                                        {(
                                            buyerScore.late_rate_last_5_settled *
                                            100
                                        ).toFixed(2)}%
                                    </p>
                                </div>
                            </div>
                        )}
                    </section>

                    {/* Recent Invoices */}
                    <section className="overflow-hidden rounded-2xl border border-slate-800 bg-[#111C30]">
                        <div className="flex flex-col justify-between gap-3 border-b border-slate-800 p-5 sm:flex-row sm:items-center sm:px-6">
                            <div>
                                <h3 className="font-semibold">Recent Invoices</h3>
                                <p className="mt-1 text-xs text-slate-500">
                                    Invoice records returned by the backend
                                </p>
                            </div>

                            <NavLink
                                to="/invoices"
                                className="inline-flex items-center gap-2 self-start rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-300 hover:border-blue-500/50 hover:text-blue-300 sm:self-auto"
                            >
                                View all invoices <ArrowUpRight size={14} />
                            </NavLink>
                        </div>

                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[760px] text-left">
                                <thead className="bg-[#0D1729]">
                                    <tr className="text-[11px] uppercase tracking-wider text-slate-500">
                                        {[
                                            "Invoice ID",
                                            "Buyer ID",
                                            "Amount",
                                            "Due date",
                                            "Tier",
                                            "Status",
                                        ].map((heading) => (
                                            <th
                                                key={heading}
                                                className="px-6 py-4 font-medium"
                                            >
                                                {heading}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>

                                <tbody className="divide-y divide-slate-800/80">
                                    {loading ? (
                                        <tr>
                                            <td
                                                colSpan={6}
                                                className="px-6 py-8 text-center text-sm text-slate-400"
                                            >
                                                Loading invoices…
                                            </td>
                                        </tr>
                                    ) : filteredInvoices.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={6}
                                                className="px-6 py-10 text-center"
                                            >
                                                <FileText
                                                    size={28}
                                                    className="mx-auto mb-3 text-slate-600"
                                                />
                                                <p className="text-sm font-medium text-slate-300">
                                                    {search.trim()
                                                        ? "No matching invoices found."
                                                        : "No invoices found."}
                                                </p>
                                                <p className="mt-1 text-xs text-slate-500">
                                                    {search.trim()
                                                        ? "Try a different search term."
                                                        : "The database currently has no invoice records."}
                                                </p>
                                            </td>
                                        </tr>
                                    ) : (
                                        filteredInvoices.map((invoice) => (
                                            <tr
                                                key={invoice.invoice_id}
                                                className="transition hover:bg-blue-500/[0.035]"
                                            >
                                                <td className="px-6 py-4 text-sm font-medium text-blue-300">
                                                    {invoice.invoice_id}
                                                </td>
                                                <td className="px-6 py-4 text-sm text-slate-200">
                                                    {invoice.buyer_id}
                                                </td>
                                                <td className="px-6 py-4 text-sm font-medium">
                                                    {formatINR(invoice.invoice_amount)}
                                                </td>
                                                <td className="px-6 py-4 text-sm text-slate-400">
                                                    {formatDate(invoice.due_date)}
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span
                                                        className={`inline-flex rounded-md px-2.5 py-1 text-xs font-medium ${invoice.tier
                                                                ? `${tierColors[
                                                                invoice.tier
                                                                ] ?? "bg-slate-500"
                                                                } ${tierTextColors[
                                                                invoice.tier
                                                                ] ?? "text-slate-300"
                                                                }`
                                                                : "bg-slate-700 text-slate-300"
                                                            }`}
                                                    >
                                                        {invoice.tier
                                                            ? `Tier ${invoice.tier}`
                                                            : "—"}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span
                                                        className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs ${getStatusStyle(
                                                            invoice.eligibility_status
                                                        )}`}
                                                    >
                                                        {invoice.eligibility_status ===
                                                            "Eligible" ? (
                                                            <CheckCircle2 size={12} />
                                                        ) : invoice.eligibility_status ===
                                                            "Disputed" ? (
                                                            <ShieldAlert size={12} />
                                                        ) : (
                                                            <Clock3 size={12} />
                                                        )}
                                                        {invoice.eligibility_status}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>

                        <div className="flex flex-col gap-2 border-t border-slate-800 px-5 py-4 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                            <span>
                                {loading
                                    ? "Loading records…"
                                    : `${filteredInvoices.length} of ${invoices.length} API records shown`}
                            </span>
                            <span className="flex items-center gap-1.5">
                                <span
                                    className={`h-1.5 w-1.5 rounded-full ${error ? "bg-rose-400" : "bg-emerald-400"
                                        }`}
                                />
                                {error ? "API connection issue" : "Dashboard API"}
                            </span>
                        </div>
                    </section>

                    <footer className="flex flex-col gap-2 pb-4 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                        <p>
                            AI-Driven Dynamic Discounting &amp; Supply Chain
                            Liquidity Engine
                        </p>
                        <p>Live KPIs and invoices · Illustrative chart</p>
                    </footer>
                </div>
            </main>
        </div>
    );
}