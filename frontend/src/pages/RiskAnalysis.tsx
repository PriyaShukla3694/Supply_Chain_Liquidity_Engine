
import { useEffect, useMemo, useState } from "react";
import {
    ApiError,
    getInvoices,
    predictInvoiceLatePaymentAuto,
    type Invoice,
    type AutoLatePaymentPredictionResponse,
} from "../api";

const PAGE_SIZE = 20;
const STORAGE_KEY = "risk_analysis_predictions_v1";

type RiskLevel = "High" | "Medium" | "Low";

function loadSavedPredictions(): Record<
    number,
    AutoLatePaymentPredictionResponse
> {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);

        if (!saved) return {};

        const parsed = JSON.parse(saved);

        return parsed && typeof parsed === "object" && !Array.isArray(parsed)
            ? parsed
            : {};
    } catch {
        return {};
    }
}

function getRiskLevel(probability: number): RiskLevel {
    if (probability >= 0.6) return "High";
    if (probability >= 0.3) return "Medium";
    return "Low";
}

function formatAmount(amount: number | string): string {
    return `Γé╣${Number(amount).toLocaleString("en-IN", {
        maximumFractionDigits: 2,
    })}`;
}

export default function RiskAnalysis() {
    const [invoices, setInvoices] = useState<Invoice[]>([]);

    const [predictions, setPredictions] = useState<
        Record<number, AutoLatePaymentPredictionResponse>
    >(loadSavedPredictions);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [predictingId, setPredictingId] = useState<number | null>(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [refreshKey, setRefreshKey] = useState(0);

    // Save predictions whenever they change.
    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(predictions));
        } catch (err) {
            console.error("Unable to save risk predictions:", err);
        }
    }, [predictions]);

    // Load invoices for the selected page.
    useEffect(() => {
        let cancelled = false;

        async function loadInvoices() {
            setLoading(true);
            setError("");

            try {
                const token = localStorage.getItem("access_token");

                if (!token) {
                    if (!cancelled) {
                        setError("Please log in to view invoice risk.");
                    }
                    return;
                }

                const result = await getInvoices(token, page, PAGE_SIZE);

                if (!cancelled) {
                    setInvoices(result.items);
                    setTotal(result.total);
                }
            } catch (err) {
                if (!cancelled) {
                    if (err instanceof ApiError && err.status === 401) {
                        return;
                    }

                    setError(
                        err instanceof Error
                            ? err.message
                            : "Unable to load invoices."
                    );
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        loadInvoices();

        return () => {
            cancelled = true;
        };
    }, [page, refreshKey]);

    async function predictRisk(invoiceId: number) {
        const token = localStorage.getItem("access_token");

        if (!token) {
            setError("Please log in to calculate invoice risk.");
            return;
        }

        setPredictingId(invoiceId);
        setError("");

        try {
            const result = await predictInvoiceLatePaymentAuto(
                token,
                invoiceId
            );

            setPredictions((previous) => ({
                ...previous,
                [invoiceId]: result,
            }));
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "Prediction failed."
            );
        } finally {
            setPredictingId(null);
        }
    }

    function refreshInvoices() {
        setRefreshKey((current) => current + 1);
    }

    const analysed = Object.values(predictions);

    const highRisk = analysed.filter(
        (prediction) =>
            getRiskLevel(prediction.late_probability) === "High"
    ).length;

    const mediumRisk = analysed.filter(
        (prediction) =>
            getRiskLevel(prediction.late_probability) === "Medium"
    ).length;

    const lowRisk = analysed.filter(
        (prediction) =>
            getRiskLevel(prediction.late_probability) === "Low"
    ).length;

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const riskDistribution = useMemo(
        () => [
            {
                label: "High",
                value: highRisk,
                color: "text-red-300",
                bg: "bg-red-500/10",
            },
            {
                label: "Medium",
                value: mediumRisk,
                color: "text-yellow-300",
                bg: "bg-yellow-500/10",
            },
            {
                label: "Low",
                value: lowRisk,
                color: "text-green-300",
                bg: "bg-green-500/10",
            },
        ],
        [highRisk, mediumRisk, lowRisk]
    );

    return (
        <main className="min-h-screen bg-slate-950 p-6 text-slate-100 md:p-10">
            <div className="mx-auto max-w-7xl">

                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-400">
                    Finance Intelligence
                </p>

                <h1 className="mt-3 text-3xl font-bold">
                    Risk Analysis
                </h1>

                <p className="mt-2 text-slate-400">
                    Analyse invoice late-payment risk using the existing prediction model.
                </p>

                {/* Summary Cards */}
                <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                    {[
                        {
                            label: "Total Invoices",
                            value: total,
                            color: "text-blue-300",
                        },
                        {
                            label: "Analysed",
                            value: analysed.length,
                            color: "text-purple-300",
                        },
                        {
                            label: "High Risk",
                            value: highRisk,
                            color: "text-red-300",
                        },
                        {
                            label: "Medium Risk",
                            value: mediumRisk,
                            color: "text-yellow-300",
                        },
                        {
                            label: "Low Risk",
                            value: lowRisk,
                            color: "text-green-300",
                        },
                    ].map((card) => (
                        <div
                            key={card.label}
                            className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
                        >
                            <p className="text-sm text-slate-400">
                                {card.label}
                            </p>

                            <p className={`mt-2 text-3xl font-bold ${card.color}`}>
                                {card.value}
                            </p>
                        </div>
                    ))}
                </div>

                {/* Invoice Risk Overview */}
                <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-5">

                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                        <div>
                            <h2 className="text-xl font-semibold">
                                Invoice Risk Overview
                            </h2>

                            <p className="mt-1 text-sm text-slate-400">
                                Select an invoice to calculate its late-payment probability.
                            </p>
                        </div>

                        <button
                            onClick={refreshInvoices}
                            disabled={loading}
                            className="rounded-lg border border-blue-700 px-4 py-3 text-sm text-blue-300 hover:bg-blue-950 disabled:opacity-50"
                        >
                            Refresh Invoices
                        </button>
                    </div>

                    {error && (
                        <div className="mt-5 rounded-lg border border-red-800 bg-red-950/30 p-4 text-red-300">
                            {error}
                        </div>
                    )}

                    {loading && (
                        <p className="py-10 text-center text-slate-400">
                            Loading invoice records...
                        </p>
                    )}

                    {!loading && !error && invoices.length === 0 && (
                        <p className="py-10 text-center text-slate-400">
                            No invoices found.
                        </p>
                    )}

                    {!loading && invoices.length > 0 && (
                        <>
                            <div className="mt-6 overflow-x-auto">
                                <table className="w-full min-w-[850px] text-left text-sm">
                                    <thead className="border-b border-slate-700 text-slate-400">
                                        <tr>
                                            <th className="px-4 py-4">Invoice ID</th>
                                            <th className="px-4 py-4">Buyer</th>
                                            <th className="px-4 py-4">Amount</th>
                                            <th className="px-4 py-4">Status</th>
                                            <th className="px-4 py-4">Late Probability</th>
                                            <th className="px-4 py-4">Risk Level</th>
                                            <th className="px-4 py-4">Action</th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {invoices.map((invoice) => {
                                            const prediction =
                                                predictions[invoice.invoice_id];

                                            const probability =
                                                prediction?.late_probability;

                                            const risk =
                                                probability === undefined
                                                    ? null
                                                    : getRiskLevel(probability);

                                            return (
                                                <tr
                                                    key={invoice.invoice_id}
                                                    className="border-b border-slate-800 hover:bg-slate-800/50"
                                                >
                                                    <td className="px-4 py-4 font-medium text-blue-300">
                                                        {invoice.invoice_id}
                                                    </td>

                                                    <td className="px-4 py-4">
                                                        {invoice.buyer_id}
                                                    </td>

                                                    <td className="px-4 py-4">
                                                        {formatAmount(invoice.invoice_amount)}
                                                    </td>

                                                    <td className="px-4 py-4 capitalize">
                                                        {invoice.invoice_status}
                                                    </td>

                                                    <td className="px-4 py-4">
                                                        {probability === undefined
                                                            ? "Not analysed"
                                                            : `${(probability * 100).toFixed(1)}%`}
                                                    </td>

                                                    <td className="px-4 py-4">
                                                        {risk && (
                                                            <span
                                                                className={`rounded-full px-3 py-1 text-xs font-semibold ${risk === "High"
                                                                        ? "bg-red-500/20 text-red-300"
                                                                        : risk === "Medium"
                                                                            ? "bg-yellow-500/20 text-yellow-300"
                                                                            : "bg-green-500/20 text-green-300"
                                                                    }`}
                                                            >
                                                                {risk}
                                                            </span>
                                                        )}
                                                        {!risk && (
                                                            <span className="text-slate-500">
                                                                ΓÇö
                                                            </span>
                                                        )}
                                                    </td>

                                                    <td className="px-4 py-4">
                                                        <button
                                                            onClick={() =>
                                                                predictRisk(invoice.invoice_id)
                                                            }
                                                            disabled={predictingId !== null}
                                                            className="rounded-lg border border-blue-700 px-3 py-2 text-blue-300 hover:bg-blue-950 disabled:cursor-not-allowed disabled:opacity-40"
                                                        >
                                                            {predictingId === invoice.invoice_id
                                                                ? "Analysing..."
                                                                : prediction
                                                                    ? "Recalculate"
                                                                    : "Predict Risk"}
                                                        </button>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            {/* Pagination */}
                            <div className="mt-6 flex flex-col items-center justify-between gap-3 border-t border-slate-800 pt-5 sm:flex-row">
                                <p className="text-sm text-slate-400">
                                    Page {page} of {totalPages} ┬╖ {total} invoices
                                </p>

                                <div className="flex gap-3">
                                    <button
                                        onClick={() =>
                                            setPage((current) =>
                                                Math.max(1, current - 1)
                                            )
                                        }
                                        disabled={page <= 1 || loading}
                                        className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                        Previous
                                    </button>

                                    <button
                                        onClick={() =>
                                            setPage((current) =>
                                                Math.min(totalPages, current + 1)
                                            )
                                        }
                                        disabled={page >= totalPages || loading}
                                        className="rounded-lg border border-blue-700 px-4 py-2 text-sm text-blue-300 hover:bg-blue-950 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                        Next
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Risk Distribution */}
                <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <h2 className="text-xl font-semibold">
                        Risk Distribution
                    </h2>

                    <p className="mt-1 text-sm text-slate-400">
                        Distribution of predictions saved in this browser.
                    </p>

                    <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                        {riskDistribution.map((item) => (
                            <div
                                key={item.label}
                                className={`rounded-xl ${item.bg} p-5 text-center`}
                            >
                                <p className={`text-3xl font-bold ${item.color}`}>
                                    {item.value}
                                </p>

                                <p className="mt-1 text-sm text-slate-400">
                                    {item.label} Risk
                                </p>
                            </div>
                        ))}
                    </div>
                </div>

            </div>
        </main>
    );
}
