
import { useEffect, useState } from "react";
import {
    getInvoicesSummary,
    getInvoices,
    type InvoiceSummary,
    type Invoice,
    ApiError,
} from "../api";

function formatINR(value: number | string) {
    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
    }).format(Number(value));
}

export default function InvoiceIntelligence() {
    const [summary, setSummary] = useState<InvoiceSummary | null>(null);
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [status, setStatus] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const pageSize = 10;
    const token = localStorage.getItem("access_token") || "";

    useEffect(() => {
        let cancelled = false;

        async function loadSummary() {
            try {
                const data = await getInvoicesSummary(token);
                if (!cancelled) setSummary(data);
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof ApiError
                            ? err.message
                            : "Unable to load invoice summary."
                    );
                }
            }
        }

        loadSummary();

        return () => {
            cancelled = true;
        };
    }, [token]);

    useEffect(() => {
        let cancelled = false;

        async function loadInvoices() {
            setLoading(true);
            setError("");

            try {
                const filters = status
                    ? { invoice_status: status as "open" | "settled" }
                    : {};

                const data = await getInvoices(
                    token,
                    page,
                    pageSize,
                    filters
                );

                if (!cancelled) {
                    setInvoices(data.items);
                    setTotal(data.total);
                }
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof ApiError
                            ? err.message
                            : "Unable to load invoices."
                    );
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        loadInvoices();

        return () => {
            cancelled = true;
        };
    }, [token, page, status]);

    const cards = [
        {
            label: "Open",
            count: summary?.open.count,
            amount: summary?.open.total_amount,
        },
        {
            label: "Overdue",
            count: summary?.overdue.count,
            amount: summary?.overdue.total_amount,
        },
        {
            label: "Settled",
            count: summary?.settled.count,
            amount: summary?.settled.total_amount,
        },
        {
            label: "Disputed",
            count: summary?.disputed.count,
            amount: summary?.disputed.total_amount,
        },
    ];

    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    return (
        <main className="min-h-screen bg-[#0B1120] p-5 text-slate-100 md:p-8">
            <div className="mx-auto max-w-7xl space-y-6">

                {/* Page heading */}
                <header>
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-400">
                        Supply Chain Liquidity Engine
                    </p>

                    <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-100">
                        Invoice Intelligence
                    </h1>

                    <p className="mt-2 text-slate-400">
                        Monitor invoices, due dates, payment status and disputes.
                    </p>
                </header>

                {/* Summary cards */}
                <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    {cards.map((card) => (
                        <article
                            key={card.label}
                            className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 transition-colors hover:border-slate-700"
                        >
                            <p className="text-sm text-slate-400">
                                {card.label} invoices
                            </p>

                            <p className="mt-3 text-3xl font-bold text-slate-100">
                                {card.count ?? "—"}
                            </p>

                            <p className="mt-2 text-sm text-slate-400">
                                {card.amount !== undefined
                                    ? formatINR(card.amount)
                                    : "Loading amount…"}
                            </p>
                        </article>
                    ))}
                </section>

                {/* Invoice register */}
                <section className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 md:p-6">
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                        <div>
                            <h2 className="text-xl font-semibold text-slate-100">
                                Invoice Register
                            </h2>

                            <p className="mt-2 text-sm text-slate-400">
                                {total} invoices matching the selected filter
                            </p>
                        </div>

                        <select
                            value={status}
                            onChange={(event) => {
                                setStatus(event.target.value);
                                setPage(1);
                            }}
                            className="rounded-lg border border-slate-700 bg-[#0D1729] px-4 py-2.5 text-sm text-slate-200 outline-none transition-colors focus:border-blue-500"
                            aria-label="Filter invoices by status"
                        >
                            <option value="">All statuses</option>
                            <option value="open">Open</option>
                            <option value="settled">Settled</option>
                        </select>
                    </div>

                    {/* Error message */}
                    {error && (
                        <div className="mt-5 rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300">
                            {error}
                        </div>
                    )}

                    {/* Table */}
                    <div className="mt-6 overflow-x-auto rounded-xl border border-slate-800">
                        <table className="w-full min-w-[850px] text-left text-sm">
                            <thead className="border-b border-slate-800 bg-[#0D1729] text-slate-400">
                                <tr>
                                    <th className="px-4 py-4 font-medium">
                                        Invoice
                                    </th>
                                    <th className="px-4 py-4 font-medium">
                                        Buyer
                                    </th>
                                    <th className="px-4 py-4 font-medium">
                                        Amount
                                    </th>
                                    <th className="px-4 py-4 font-medium">
                                        Due Date
                                    </th>
                                    <th className="px-4 py-4 font-medium">
                                        Due Status
                                    </th>
                                    <th className="px-4 py-4 font-medium">
                                        Invoice Status
                                    </th>
                                    <th className="px-4 py-4 font-medium">
                                        Dispute
                                    </th>
                                </tr>
                            </thead>

                            <tbody className="divide-y divide-slate-800">
                                {loading ? (
                                    <tr>
                                        <td
                                            colSpan={7}
                                            className="px-4 py-12 text-center text-slate-400"
                                        >
                                            <span className="inline-flex items-center gap-2">
                                                <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
                                                Loading invoices…
                                            </span>
                                        </td>
                                    </tr>
                                ) : invoices.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={7}
                                            className="px-4 py-12 text-center text-slate-400"
                                        >
                                            No invoices found.
                                        </td>
                                    </tr>
                                ) : (
                                    invoices.map((invoice) => (
                                        <tr
                                            key={invoice.invoice_id}
                                            className="transition-colors hover:bg-slate-800/40"
                                        >
                                            <td className="px-4 py-4 font-medium text-blue-300">
                                                #{invoice.invoice_id}
                                            </td>

                                            <td className="px-4 py-4 text-slate-300">
                                                {invoice.buyer_id}
                                            </td>

                                            <td className="px-4 py-4 font-medium text-slate-100">
                                                {formatINR(invoice.invoice_amount)}
                                            </td>

                                            <td className="px-4 py-4 text-slate-300">
                                                {invoice.due_date}
                                            </td>

                                            <td className="px-4 py-4">
                                                {invoice.invoice_status === "settled" ? (
                                                    <span className="text-slate-400">
                                                        Settled
                                                    </span>
                                                ) : invoice.overdue_days > 0 ? (
                                                    <span className="font-medium text-red-400">
                                                        {invoice.overdue_days} days overdue
                                                    </span>
                                                ) : invoice.days_until_due === 0 ? (
                                                    <span className="font-medium text-amber-400">
                                                        Due today
                                                    </span>
                                                ) : (
                                                    <span className="text-emerald-400">
                                                        {invoice.days_until_due ?? "—"} days left
                                                    </span>
                                                )}
                                            </td>

                                            <td className="px-4 py-4">
                                                <span
                                                    className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${invoice.invoice_status === "settled"
                                                            ? "border-emerald-800 bg-emerald-950/40 text-emerald-300"
                                                            : "border-blue-800 bg-blue-950/40 text-blue-300"
                                                        }`}
                                                >
                                                    {invoice.invoice_status}
                                                </span>
                                            </td>

                                            <td className="px-4 py-4">
                                                {invoice.disputed ? (
                                                    <span className="inline-flex rounded-full border border-red-800 bg-red-950/40 px-2.5 py-1 text-xs font-medium text-red-300">
                                                        Yes
                                                    </span>
                                                ) : (
                                                    <span className="text-slate-400">
                                                        No
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    <div className="mt-6 flex flex-col items-center justify-between gap-4 border-t border-slate-800 pt-5 sm:flex-row">
                        <p className="text-sm text-slate-400">
                            Page <span className="font-medium text-slate-200">{page}</span>{" "}
                            of <span className="font-medium text-slate-200">{totalPages}</span>
                        </p>

                        <div className="flex gap-3">
                            <button
                                disabled={page <= 1 || loading}
                                onClick={() => setPage((current) => current - 1)}
                                className="rounded-lg border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Previous
                            </button>

                            <button
                                disabled={page >= totalPages || loading}
                                onClick={() => setPage((current) => current + 1)}
                                className="rounded-lg border border-blue-700 bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                </section>

                {/* ML predictions placeholder */}
                <section className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 md:p-6">
                    <div className="flex items-start gap-4">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-blue-800 bg-blue-950/50">
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="22"
                                height="22"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.8"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                className="text-blue-400"
                                aria-hidden="true"
                            >
                                <path d="M12 8V4H8" />
                                <rect width="16" height="12" x="4" y="8" rx="2" />
                                <path d="M2 14h2" />
                                <path d="M20 14h2" />
                                <path d="M15 13v2" />
                                <path d="M9 13v2" />
                            </svg>
                        </div>

                        <div>
                            <h2 className="font-semibold text-slate-100">
                                ML Payment Predictions
                            </h2>

                            <p className="mt-2 text-sm leading-6 text-slate-400">
                                Predictions will appear here after the payment-risk
                                model is trained and integrated with the backend.
                                No estimated probabilities are shown until real
                                model output is available.
                            </p>

                            <span className="mt-4 inline-flex rounded-full border border-amber-800 bg-amber-950/30 px-3 py-1 text-xs font-medium text-amber-300">
                                Awaiting model integration
                            </span>
                        </div>
                    </div>
                </section>

            </div>
        </main>
    );
}
