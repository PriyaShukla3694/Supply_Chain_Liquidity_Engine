
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getBuyerScore, type BuyerScore } from "../api";

export default function BuyerDetails() {
    const { buyerId } = useParams<{ buyerId: string }>();
    const navigate = useNavigate();

    const [asOfDate, setAsOfDate] = useState("2015-04-15");
    const [score, setScore] = useState<BuyerScore | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const loadScore = useCallback(async (date: string) => {
        const token = localStorage.getItem("access_token");

        if (!token || !buyerId) {
            navigate("/login", { replace: true });
            return;
        }

        setLoading(true);
        setError("");

        try {
            const result = await getBuyerScore(token, buyerId, date);
            setScore(result);
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Unable to load buyer score."
            );
            setScore(null);
        } finally {
            setLoading(false);
        }
    }, [buyerId, navigate]);

    useEffect(() => {
        if (!buyerId) return;
        const timer = setTimeout(() => {
            void loadScore("2015-04-15");
        }, 0);
        return () => clearTimeout(timer);
    }, [buyerId, loadScore]);

    const metrics = [
        { label: "Reliability Score", value: score?.reliability_score },
        { label: "Financial Health", value: score?.financial_score },
        { label: "Liquidity Health", value: score?.liquidity_score },
        { label: "Overall Score", value: score?.overall_score },
    ];

    return (
        <main className="min-h-screen bg-slate-950 p-6 text-slate-100 md:p-10">
            <div className="mx-auto max-w-6xl">
                <button
                    onClick={() => navigate("/buyers")}
                    className="mb-6 rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
                >
                    ← Back to Buyers
                </button>

                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-400">
                    Finance Intelligence
                </p>

                <h1 className="mt-3 text-3xl font-bold">Buyer Score Details</h1>
                <p className="mt-2 text-slate-400">
                    Buyer ID: <span className="text-blue-300">{buyerId}</span>
                </p>

                <section className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6">
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                        <div>
                            <label
                                htmlFor="as-of-date"
                                className="mb-2 block text-sm text-slate-400"
                            >
                                Calculate score as of
                            </label>
                            <input
                                id="as-of-date"
                                type="date"
                                value={asOfDate}
                                onChange={(event) => setAsOfDate(event.target.value)}
                                className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-3"
                            />
                        </div>

                        <button
                            onClick={() => void loadScore(asOfDate)}
                            disabled={loading || !asOfDate}
                            className="rounded-lg bg-blue-600 px-5 py-3 font-medium hover:bg-blue-500 disabled:opacity-50"
                        >
                            {loading ? "Calculating..." : "Calculate Score"}
                        </button>
                    </div>

                    {loading && (
                        <p className="mt-6 text-slate-400">Loading score preview...</p>
                    )}

                    {error && (
                        <p className="mt-6 rounded-lg border border-red-800 bg-red-950/30 p-4 text-red-300">
                            {error}
                        </p>
                    )}

                    {!loading && score && (
                        <>
                            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                                {metrics.map((metric) => (
                                    <div
                                        key={metric.label}
                                        className="rounded-xl border border-slate-800 bg-slate-950 p-5"
                                    >
                                        <p className="text-sm text-slate-400">{metric.label}</p>
                                        <p className="mt-3 text-3xl font-bold">
                                            {metric.value == null
                                                ? "—"
                                                : `${metric.value.toFixed(2)}`}
                                        </p>
                                        <p className="mt-1 text-xs text-slate-500">Out of 100</p>
                                    </div>
                                ))}
                            </div>

                            <div className="mt-6 grid gap-4 sm:grid-cols-2">
                                <div className="rounded-xl border border-slate-800 p-5">
                                    <p className="text-sm text-slate-400">Risk Tier</p>
                                    <p className="mt-2 text-2xl font-bold">
                                        {score.tier ?? "Not assigned"}
                                    </p>
                                    <p className="mt-2 text-sm text-slate-400">
                                        Basis: {score.tier_basis.replaceAll("_", " ")}
                                    </p>
                                    <p className="mt-1 text-sm text-slate-400">
                                        Status: {score.status.replaceAll("_", " ")}
                                    </p>
                                </div>

                                <div className="rounded-xl border border-slate-800 p-5">
                                    <p className="text-sm text-slate-400">Payment History</p>
                                    <p className="mt-2">
                                        Resolved invoices:{" "}
                                        <strong>{score.resolved_invoice_count}</strong>
                                    </p>
                                    <p className="mt-2">
                                        Late rate:{" "}
                                        <strong>{(score.late_rate * 100).toFixed(2)}%</strong>
                                    </p>
                                    <p className="mt-2">
                                        Average days late:{" "}
                                        <strong>{score.avg_days_late.toFixed(2)}</strong>
                                    </p>
                                    <p className="mt-2">
                                        Last 5 settled late rate:{" "}
                                        <strong>
                                            {(score.late_rate_last_5_settled * 100).toFixed(2)}%
                                        </strong>
                                    </p>
                                </div>

                                <div className="rounded-xl border border-slate-800 p-5">
                                    <p className="text-sm text-slate-400">Exposure</p>
                                    <p className="mt-2">
                                        Open exposure:{" "}
                                        <strong>
                                            ₹{score.open_exposure.toLocaleString("en-IN")}
                                        </strong>
                                    </p>
                                    <p className="mt-2">
                                        Overdue exposure:{" "}
                                        <strong>
                                            ₹{score.overdue_open_exposure.toLocaleString("en-IN")}
                                        </strong>
                                    </p>
                                    <p className="mt-2">
                                        Credit limit:{" "}
                                        <strong>
                                            ₹{score.credit_limit.toLocaleString("en-IN")}
                                        </strong>
                                    </p>
                                </div>

                                <div className="rounded-xl border border-slate-800 p-5">
                                    <p className="text-sm text-slate-400">Preview Information</p>
                                    <p className="mt-2">
                                        As of: <strong>{score.as_of_date}</strong>
                                    </p>
                                    <p className="mt-2 text-sm text-amber-300">
                                        Read-only preview. This calculation does not save scores to
                                        the database.
                                    </p>
                                </div>
                            </div>
                        </>
                    )}
                </section>
            </div>
        </main>
    );
}
