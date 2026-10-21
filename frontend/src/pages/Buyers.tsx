
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, getBuyers, type BuyerItem } from "../api";

const PAGE_SIZE = 20;

export default function Buyers() {
    const navigate = useNavigate();

    const [buyers, setBuyers] = useState<BuyerItem[]>([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);

    useEffect(() => {
        let cancelled = false;

        async function loadBuyers() {
            setLoading(true);
            setError("");

            try {
                const token = localStorage.getItem("access_token");

                if (!token) {
                    if (!cancelled) setLoading(false);
                    return;
                }

                const result = await getBuyers(token, page, PAGE_SIZE);

                if (!cancelled) {
                    setBuyers(result.items);
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
                            : "Something went wrong."
                    );
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        loadBuyers();

        return () => {
            cancelled = true;
        };
    }, [page]);

    const filteredBuyers = useMemo(() => {
        const query = search.trim().toLowerCase();

        return buyers.filter((buyer) =>
            buyer.buyer_id.toLowerCase().includes(query)
        );
    }, [buyers, search]);

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    return (
        <main className="min-h-screen bg-slate-950 p-6 text-slate-100 md:p-10">
            <div className="mx-auto max-w-7xl">
                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-400">
                    Finance Intelligence
                </p>

                <h1 className="mt-3 text-3xl font-bold">Buyers</h1>

                <p className="mt-2 text-slate-400">
                    View buyer records and review their risk-score previews.
                </p>

                <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                        <div>
                            <h2 className="text-xl font-semibold">
                                Buyer Directory
                            </h2>

                            <p className="mt-1 text-sm text-slate-400">
                                {loading
                                    ? "Loading buyers..."
                                    : `Showing ${total === 0
                                        ? 0
                                        : (page - 1) * PAGE_SIZE + 1
                                    }–${Math.min(
                                        page * PAGE_SIZE,
                                        total
                                    )} of ${total} buyers`}
                            </p>
                        </div>

                        <input
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search buyer ID on this page..."
                            className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none focus:border-blue-500"
                        />
                    </div>

                    {loading && (
                        <p className="py-10 text-center text-slate-400">
                            Loading buyer records...
                        </p>
                    )}

                    {error && (
                        <div className="mt-5 rounded-lg border border-red-800 bg-red-950/30 p-4 text-red-300">
                            {error}
                        </div>
                    )}

                    {!loading && !error && (
                        <>
                            <div className="mt-6 overflow-x-auto">
                                <table className="w-full min-w-[600px] text-left text-sm">
                                    <thead className="border-b border-slate-700 text-slate-400">
                                        <tr>
                                            <th className="px-4 py-4">Buyer ID</th>
                                            <th className="px-4 py-4">Stored Tier</th>
                                            <th className="px-4 py-4">Credit Limit</th>
                                            <th className="px-4 py-4">Action</th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {filteredBuyers.map((buyer) => (
                                            <tr
                                                key={buyer.buyer_id}
                                                className="border-b border-slate-800 hover:bg-slate-800/50"
                                            >
                                                <td className="px-4 py-4 font-medium text-blue-300">
                                                    {buyer.buyer_id}
                                                </td>

                                                <td className="px-4 py-4">
                                                    {buyer.tier || "Not assigned"}
                                                </td>

                                                <td className="px-4 py-4">
                                                    {buyer.credit_limit == null
                                                        ? "—"
                                                        : `₹${Number(
                                                            buyer.credit_limit
                                                        ).toLocaleString("en-IN")}`}
                                                </td>

                                                <td className="px-4 py-4">
                                                    <button
                                                        onClick={() =>
                                                            navigate(
                                                                `/buyers/${encodeURIComponent(
                                                                    buyer.buyer_id
                                                                )}`
                                                            )
                                                        }
                                                        className="rounded-lg border border-blue-700 px-3 py-2 text-blue-300 hover:bg-blue-950"
                                                    >
                                                        View Score
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}

                                        {filteredBuyers.length === 0 && (
                                            <tr>
                                                <td
                                                    colSpan={4}
                                                    className="px-4 py-10 text-center text-slate-400"
                                                >
                                                    No buyers found on this page.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>

                            <div className="mt-6 flex flex-col items-center justify-between gap-3 border-t border-slate-800 pt-5 sm:flex-row">
                                <p className="text-sm text-slate-400">
                                    Page {page} of {totalPages}
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
                                                Math.min(
                                                    totalPages,
                                                    current + 1
                                                )
                                            )
                                        }
                                        disabled={
                                            page >= totalPages || loading
                                        }
                                        className="rounded-lg border border-blue-700 px-4 py-2 text-sm text-blue-300 hover:bg-blue-950 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                        Next
                                    </button>
                                </div>
                            </div>
                        </>
                    )}

                    <button
                        onClick={() => navigate("/")}
                        className="mt-6 rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
                    >
                        Back to Dashboard
                    </button>
                </div>
            </div>
        </main>
    );
}
