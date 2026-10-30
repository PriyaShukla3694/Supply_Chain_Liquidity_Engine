
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
    getInvoicesSummary,
    getInvoices,
    predictInvoiceLatePaymentAuto,
    askRagQuestion,
    type InvoiceSummary,
    type Invoice,
    type AutoLatePaymentPredictionResponse,
    type RagAnswerResponse,
    type RagSourceChunk,
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

    // ML prediction state
    const [prediction, setPrediction] =
        useState<AutoLatePaymentPredictionResponse | null>(null);
    const [predictedInvoiceId, setPredictedInvoiceId] =
        useState<number | null>(null);
    const [predictingInvoiceId, setPredictingInvoiceId] =
        useState<number | null>(null);
    const [predictionError, setPredictionError] = useState("");

    // RAG assistant state
    const [ragQuestion, setRagQuestion] = useState("");
    const [ragResult, setRagResult] =
        useState<RagAnswerResponse | null>(null);
    const [ragLoading, setRagLoading] = useState(false);
    const [ragError, setRagError] = useState("");

    const pageSize = 10;
    const token = localStorage.getItem("access_token") || "";

    // Load invoice summary
    useEffect(() => {
        let cancelled = false;

        async function loadSummary() {
            try {
                const data = await getInvoicesSummary(token);

                if (!cancelled) {
                    setSummary(data);
                }
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

    // Load invoice register
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
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        loadInvoices();

        return () => {
            cancelled = true;
        };
    }, [token, page, status]);

    // Run ML payment-risk prediction
    async function handlePredict(invoiceId: number) {
        if (!token) {
            setPredictionError("Please log in to predict invoice risk.");
            setPrediction(null);
            setPredictedInvoiceId(null);
            return;
        }

        setPredictingInvoiceId(invoiceId);
        setPredictionError("");
        setPrediction(null);
        setPredictedInvoiceId(null);

        try {
            const result = await predictInvoiceLatePaymentAuto(
                token,
                invoiceId
            );

            setPrediction(result);
            setPredictedInvoiceId(invoiceId);
        } catch (err) {
            setPredictionError(
                err instanceof ApiError
                    ? err.message
                    : "Unable to predict payment risk."
            );
        } finally {
            setPredictingInvoiceId(null);
        }
    }

    // Ask a question using the RAG backend
    async function handleAskRag(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        const question = ragQuestion.trim();

        if (!question) {
            setRagError("Please enter a question.");
            return;
        }

        if (!token) {
            setRagError("Please log in to ask policy questions.");
            setRagResult(null);
            return;
        }

        setRagLoading(true);
        setRagError("");
        setRagResult(null);

        try {
            const result = await askRagQuestion(token, question);
            setRagResult(result);
        } catch (err) {
            setRagError(
                err instanceof ApiError
                    ? err.message
                    : "Unable to generate an answer. Please try again."
            );
        } finally {
            setRagLoading(false);
        }
    }

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
                                setPrediction(null);
                                setPredictedInvoiceId(null);
                                setPredictionError("");
                            }}
                            className="rounded-lg border border-slate-700 bg-[#0D1729] px-4 py-2.5 text-sm text-slate-200 outline-none transition-colors focus:border-blue-500"
                            aria-label="Filter invoices by status"
                        >
                            <option value="">All statuses</option>
                            <option value="open">Open</option>
                            <option value="settled">Settled</option>
                        </select>
                    </div>

                    {error && (
                        <div
                            role="alert"
                            className="mt-5 rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300"
                        >
                            {error}
                        </div>
                    )}

                    {/* Invoice table */}
                    <div className="mt-6 overflow-x-auto rounded-xl border border-slate-800">
                        <table className="w-full min-w-[1000px] text-left text-sm">
                            <thead className="border-b border-slate-800 bg-[#0D1729] text-slate-400">
                                <tr>
                                    <th className="px-4 py-4 font-medium">Invoice</th>
                                    <th className="px-4 py-4 font-medium">Buyer</th>
                                    <th className="px-4 py-4 font-medium">Amount</th>
                                    <th className="px-4 py-4 font-medium">Due Date</th>
                                    <th className="px-4 py-4 font-medium">Due Status</th>
                                    <th className="px-4 py-4 font-medium">Invoice Status</th>
                                    <th className="px-4 py-4 font-medium">Dispute</th>
                                    <th className="px-4 py-4 font-medium">ML Prediction</th>
                                </tr>
                            </thead>

                            <tbody className="divide-y divide-slate-800">
                                {loading ? (
                                    <tr>
                                        <td
                                            colSpan={8}
                                            className="px-4 py-12 text-center text-slate-400"
                                        >
                                            Loading invoices…
                                        </td>
                                    </tr>
                                ) : invoices.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={8}
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

                                            <td className="px-4 py-4">
                                                <button
                                                    type="button"
                                                    onClick={() =>
                                                        handlePredict(invoice.invoice_id)
                                                    }
                                                    disabled={predictingInvoiceId !== null}
                                                    className="whitespace-nowrap rounded-lg border border-blue-700 bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                                                >
                                                    {predictingInvoiceId === invoice.invoice_id
                                                        ? "Predicting…"
                                                        : "Predict Risk"}
                                                </button>
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
                            Page{" "}
                            <span className="font-medium text-slate-200">{page}</span>
                            {" "}of{" "}
                            <span className="font-medium text-slate-200">{totalPages}</span>
                        </p>

                        <div className="flex gap-3">
                            <button
                                type="button"
                                disabled={page <= 1 || loading}
                                onClick={() => setPage((current) => current - 1)}
                                className="rounded-lg border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Previous
                            </button>

                            <button
                                type="button"
                                disabled={page >= totalPages || loading}
                                onClick={() => setPage((current) => current + 1)}
                                className="rounded-lg border border-blue-700 bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                </section>

                {/* RAG AI Policy Assistant */}
                <section className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 md:p-6">
                    <div>
                        <p className="text-sm font-semibold uppercase tracking-wider text-blue-400">
                            Retrieval-Augmented Generation
                        </p>

                        <h2 className="mt-2 text-xl font-semibold text-slate-100">
                            AI Policy Assistant
                        </h2>

                        <p className="mt-2 text-sm leading-6 text-slate-400">
                            Ask questions about your organization's policies and
                            indexed documents. Review the cited sources before
                            making business decisions.
                        </p>
                    </div>

                    <form onSubmit={handleAskRag} className="mt-5 space-y-3">
                        <label
                            htmlFor="rag-question"
                            className="block text-sm font-medium text-slate-300"
                        >
                            Your question
                        </label>

                        <textarea
                            id="rag-question"
                            value={ragQuestion}
                            onChange={(event) => setRagQuestion(event.target.value)}
                            placeholder="For example: What are the discount eligibility rules?"
                            rows={3}
                            maxLength={2000}
                            disabled={ragLoading}
                            className="w-full resize-y rounded-xl border border-slate-700 bg-[#0D1729] px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-blue-500 disabled:opacity-50"
                        />

                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <p className="text-xs text-slate-500">
                                Answers depend on the documents available to your organization.
                            </p>

                            <button
                                type="submit"
                                disabled={ragLoading || !ragQuestion.trim()}
                                className="rounded-lg border border-blue-700 bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {ragLoading ? "Generating answer…" : "Ask AI"}
                            </button>
                        </div>
                    </form>

                    {ragError && (
                        <div
                            role="alert"
                            className="mt-5 rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300"
                        >
                            {ragError}
                        </div>
                    )}

                    {ragLoading && (
                        <p role="status" className="mt-5 text-sm text-blue-300">
                            Searching relevant documents and preparing an answer…
                        </p>
                    )}

                    {ragResult && (
                        <div className="mt-6 space-y-5">
                            {/* Generated answer */}
                            <article className="rounded-xl border border-slate-800 bg-[#0D1729] p-5">
                                <h3 className="font-semibold text-slate-100">
                                    Answer
                                </h3>

                                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-300">
                                    {ragResult.answer}
                                </p>
                            </article>

                            {/* Citations */}
                            <div>
                                <h3 className="font-semibold text-slate-100">
                                    Sources and citations
                                </h3>

                                {ragResult.citations.length === 0 ? (
                                    <p className="mt-3 rounded-lg border border-amber-800 bg-amber-950/20 p-4 text-sm text-amber-300">
                                        No citations were returned. Verify this answer
                                        against the original documents before relying on it.
                                    </p>
                                ) : (
                                    <ul className="mt-3 space-y-2">
                                        {ragResult.citations.map((citation) => (
                                            <li
                                                key={`${citation.index}-${citation.document_name}-${citation.chunk_index}`}
                                                className="rounded-lg border border-slate-800 p-4"
                                            >
                                                <p className="text-sm font-medium text-blue-300">
                                                    [{citation.index}] {citation.document_name}
                                                </p>

                                                <p className="mt-1 text-xs text-slate-400">
                                                    Type: {citation.document_type}
                                                    {" · "}
                                                    Version: {citation.version}
                                                    {" · "}
                                                    Chunk: {citation.chunk_index}
                                                </p>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>

                            {/* Retrieved source excerpts */}
                            {ragResult.source_chunks.length > 0 && (
                                <details className="rounded-xl border border-slate-800 p-4">
                                    <summary className="cursor-pointer text-sm font-medium text-slate-300">
                                        View retrieved source excerpts (
                                        {ragResult.source_chunks.length})
                                    </summary>

                                    <div className="mt-4 space-y-3">
                                        {ragResult.source_chunks.map(
                                            (source: RagSourceChunk, index) => (
                                                <article
                                                    key={`${source.document_name}-${source.chunk_index}-${index}`}
                                                    className="rounded-lg border border-slate-800 bg-[#0D1729] p-4"
                                                >
                                                    <p className="text-sm font-medium text-slate-200">
                                                        {source.document_name}
                                                    </p>

                                                    <p className="mt-1 text-xs text-slate-400">
                                                        {source.document_type}
                                                        {" · "}
                                                        Version: {source.version}
                                                        {" · "}
                                                        Chunk: {source.chunk_index}
                                                    </p>

                                                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                                                        {source.chunk_text}
                                                    </p>
                                                </article>
                                            )
                                        )}
                                    </div>
                                </details>
                            )}
                        </div>
                    )}
                </section>

                {/* ML prediction results */}
                <section className="rounded-2xl border border-slate-800 bg-[#111C30] p-5 md:p-6">
                    <h2 className="text-xl font-semibold text-slate-100">
                        ML Payment Predictions
                    </h2>

                    <p className="mt-2 text-sm text-slate-400">
                        Select an invoice and click Predict Risk to run the trained
                        payment-risk model.
                    </p>

                    {predictionError && (
                        <div
                            role="alert"
                            className="mt-5 rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300"
                        >
                            {predictionError}
                        </div>
                    )}

                    {predictingInvoiceId !== null && (
                        <p className="mt-5 text-sm text-blue-300">
                            Calculating prediction for invoice #{predictingInvoiceId}…
                        </p>
                    )}

                    {prediction && predictedInvoiceId !== null && (
                        <div className="mt-6 space-y-5">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <div>
                                    <p className="text-sm text-slate-400">
                                        Invoice ID
                                    </p>
                                    <p className="mt-1 text-lg font-semibold text-slate-100">
                                        #{predictedInvoiceId}
                                    </p>
                                </div>

                                <span
                                    className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${prediction.predicted_label === 1
                                            ? "border-red-800 bg-red-950/40 text-red-300"
                                            : "border-emerald-800 bg-emerald-950/40 text-emerald-300"
                                        }`}
                                >
                                    {prediction.predicted_label === 1
                                        ? "Higher late-payment risk"
                                        : "Lower late-payment risk"}
                                </span>
                            </div>

                            <div className="rounded-xl border border-slate-800 bg-[#0D1729] p-5">
                                <div className="flex items-end justify-between gap-3">
                                    <div>
                                        <p className="text-sm text-slate-400">
                                            Estimated late-payment probability
                                        </p>

                                        <p className="mt-2 text-4xl font-bold text-slate-100">
                                            {(prediction.late_probability * 100).toFixed(2)}%
                                        </p>
                                    </div>

                                    <p className="text-sm text-slate-400">
                                        Threshold: {(prediction.threshold * 100).toFixed(0)}%
                                    </p>
                                </div>

                                <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
                                    <div
                                        className={`h-full rounded-full ${prediction.predicted_label === 1
                                                ? "bg-red-500"
                                                : "bg-emerald-500"
                                            }`}
                                        style={{
                                            width: `${Math.max(
                                                0,
                                                Math.min(
                                                    100,
                                                    prediction.late_probability * 100
                                                )
                                            )}%`,
                                        }}
                                    />
                                </div>
                            </div>

                            <div className="grid gap-4 sm:grid-cols-2">
                                <div className="rounded-xl border border-slate-800 p-4">
                                    <p className="text-sm text-slate-400">Model</p>

                                    <p className="mt-2 font-medium text-slate-100">
                                        {prediction.model_name}
                                    </p>

                                    <p className="mt-1 text-sm text-slate-400">
                                        Version {prediction.model_version}
                                    </p>
                                </div>

                                <div className="rounded-xl border border-slate-800 p-4">
                                    <p className="text-sm text-slate-400">
                                        Probability calibration
                                    </p>

                                    <p className="mt-2 font-medium text-slate-100">
                                        {prediction.calibrated
                                            ? "Calibrated"
                                            : "Not calibrated"}
                                    </p>

                                    <p className="mt-1 text-xs text-slate-400">
                                        Probability is an estimate, not a guarantee.
                                    </p>
                                </div>
                            </div>

                            <p className="text-xs text-slate-500">
                                Scored at:{" "}
                                {new Date(prediction.scored_at).toLocaleString()}
                            </p>

                            <details className="rounded-xl border border-slate-800 p-4">
                                <summary className="cursor-pointer text-sm font-medium text-slate-300">
                                    View features used by the model
                                </summary>

                                <div className="mt-4 overflow-x-auto">
                                    <table className="w-full text-left text-sm">
                                        <thead className="text-slate-400">
                                            <tr>
                                                <th className="px-3 py-2 font-medium">
                                                    Feature
                                                </th>
                                                <th className="px-3 py-2 font-medium">
                                                    Value
                                                </th>
                                            </tr>
                                        </thead>

                                        <tbody className="divide-y divide-slate-800">
                                            {Object.entries(prediction.features_used).map(
                                                ([feature, value]) => (
                                                    <tr key={feature}>
                                                        <td className="px-3 py-2 text-slate-300">
                                                            {feature}
                                                        </td>

                                                        <td className="px-3 py-2 text-slate-100">
                                                            {value === null
                                                                ? "N/A"
                                                                : String(value)}
                                                        </td>
                                                    </tr>
                                                )
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </details>
                        </div>
                    )}

                    {!prediction &&
                        !predictionError &&
                        predictingInvoiceId === null && (
                            <div className="mt-5 rounded-xl border border-dashed border-slate-700 p-6 text-center">
                                <p className="text-sm text-slate-400">
                                    No prediction yet. Click{" "}
                                    <span className="font-semibold text-blue-300">
                                        Predict Risk
                                    </span>{" "}
                                    beside an invoice to view its result.
                                </p>
                            </div>
                        )}
                </section>
            </div>
        </main>
    );
}
