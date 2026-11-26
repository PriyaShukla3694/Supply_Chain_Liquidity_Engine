
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
    ArrowLeft,
    RefreshCw,
    AlertCircle,
    CheckCircle2,
    Clock,
    Wallet,
    BadgePercent,
    Check,
    X,
} from "lucide-react";
import {
    getDiscountRecommendations,
    createDiscountOffer,
    approveDiscountOffer,
    rejectDiscountOffer,
    type DiscountRecommendationsResponse,
} from "../api";

const cardStyle: React.CSSProperties = {
    background: "#111827",
    border: "1px solid #263244",
    borderRadius: "12px",
    padding: "20px",
};

const formatINR = (value: string | number) =>
    new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
    }).format(Number(value) || 0);

const formatPercent = (value: string | number) =>
    `${(Number(value) * 100).toFixed(1)}%`;

export default function Discounts() {
    const [data, setData] =
        useState<DiscountRecommendationsResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
    const [actionMessage, setActionMessage] = useState("");
    const [actionError, setActionError] = useState("");

    // Keep a created offer ID if approval/rejection needs to be retried.
    const [createdOfferIds, setCreatedOfferIds] = useState<
        Record<number, string>
    >({});

    const loadRecommendations = useCallback(async () => {
        const token = localStorage.getItem("access_token");

        if (!token) {
            setError("Your session has expired. Please log in again.");
            setLoading(false);
            return;
        }

        setLoading(true);
        setError("");

        try {
            const result = await getDiscountRecommendations(token);
            setData(result);
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "Unable to load discount recommendations."
            );
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadRecommendations();
    }, [loadRecommendations]);

    const handleOfferAction = async (
        invoiceId: number,
        buyerId: string,
        action: "approve" | "reject"
    ) => {
        const token = localStorage.getItem("access_token");

        if (!token) {
            setActionError("Your session has expired. Please log in again.");
            return;
        }

        setActionLoadingId(invoiceId);
        setActionMessage("");
        setActionError("");

        try {
            // Reuse the offer ID if offer creation already succeeded.
            let offerId = createdOfferIds[invoiceId];

            if (!offerId) {
                const createdOffer = await createDiscountOffer(token, {
                    invoice_id: invoiceId,
                    buyer_id: buyerId,
                });

                offerId = createdOffer.offer_id;

                setCreatedOfferIds((previous) => ({
                    ...previous,
                    [invoiceId]: offerId,
                }));
            }

            if (action === "approve") {
                await approveDiscountOffer(token, offerId);
                setActionMessage(
                    `Discount offer for Invoice #${invoiceId} approved successfully.`
                );
            } else {
                await rejectDiscountOffer(token, offerId);
                setActionMessage(
                    `Discount offer for Invoice #${invoiceId} rejected successfully.`
                );
            }

            setCreatedOfferIds((previous) => {
                const updated = { ...previous };
                delete updated[invoiceId];
                return updated;
            });

            await loadRecommendations();
        } catch (err) {
            setActionError(
                err instanceof Error
                    ? err.message
                    : `Unable to ${action} the discount offer.`
            );
        } finally {
            setActionLoadingId(null);
        }
    };

    const summaryCards = data
        ? [
            {
                label: "Eligible Invoice Value",
                value: formatINR(data.eligible_invoice_value),
                icon: Wallet,
            },
            {
                label: "Weekly Budget",
                value: formatINR(data.weekly_budget),
                icon: BadgePercent,
            },
            {
                label: "Existing Allocation",
                value: formatINR(data.existing_allocation),
                icon: Clock,
            },
            {
                label: "New Recommendations",
                value: formatINR(data.new_recommendation_total),
                icon: CheckCircle2,
            },
            {
                label: "Remaining Budget",
                value: formatINR(data.remaining_budget),
                icon: Wallet,
            },
        ]
        : [];

    return (
        <div
            style={{
                minHeight: "100vh",
                background: "#0b1120",
                color: "#e5e7eb",
                padding: "32px",
                fontFamily: "Inter, sans-serif",
            }}
        >
            <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: "16px",
                        marginBottom: "28px",
                    }}
                >
                    <div>
                        <Link
                            to="/"
                            style={{
                                color: "#94a3b8",
                                textDecoration: "none",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "8px",
                                marginBottom: "18px",
                            }}
                        >
                            <ArrowLeft size={16} />
                            Back to Dashboard
                        </Link>

                        <h1
                            style={{
                                fontSize: "28px",
                                fontWeight: 700,
                                margin: 0,
                            }}
                        >
                            Discount Optimizer
                        </h1>
                        <p style={{ color: "#94a3b8", marginTop: "8px" }}>
                            AI-driven early payment discount recommendations
                        </p>
                    </div>

                    <button
                        onClick={() => void loadRecommendations()}
                        disabled={loading || actionLoadingId !== null}
                        style={{
                            background: "#2563eb",
                            color: "white",
                            border: 0,
                            borderRadius: "8px",
                            padding: "11px 18px",
                            display: "flex",
                            alignItems: "center",
                            gap: "8px",
                            cursor: loading ? "not-allowed" : "pointer",
                            opacity: loading ? 0.6 : 1,
                        }}
                    >
                        <RefreshCw size={16} />
                        Refresh
                    </button>
                </div>

                {actionMessage && (
                    <div
                        role="status"
                        style={{
                            ...cardStyle,
                            marginBottom: "18px",
                            borderColor: "#166534",
                            color: "#86efac",
                        }}
                    >
                        <CheckCircle2
                            size={18}
                            style={{
                                display: "inline",
                                verticalAlign: "middle",
                                marginRight: "8px",
                            }}
                        />
                        {actionMessage}
                    </div>
                )}

                {actionError && (
                    <div
                        role="alert"
                        style={{
                            ...cardStyle,
                            marginBottom: "18px",
                            borderColor: "#7f1d1d",
                            color: "#fca5a5",
                        }}
                    >
                        <AlertCircle
                            size={18}
                            style={{
                                display: "inline",
                                verticalAlign: "middle",
                                marginRight: "8px",
                            }}
                        />
                        {actionError}
                    </div>
                )}

                {loading && (
                    <div style={cardStyle}>
                        Loading discount recommendations...
                    </div>
                )}

                {!loading && error && (
                    <div
                        style={{
                            ...cardStyle,
                            borderColor: "#7f1d1d",
                            color: "#fca5a5",
                        }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "10px",
                            }}
                        >
                            <AlertCircle size={20} />
                            <strong>Could not load recommendations</strong>
                        </div>
                        <p>{error}</p>
                        <button
                            onClick={() => void loadRecommendations()}
                            style={{
                                background: "#7f1d1d",
                                color: "white",
                                border: 0,
                                borderRadius: "6px",
                                padding: "9px 14px",
                                cursor: "pointer",
                            }}
                        >
                            Try Again
                        </button>
                    </div>
                )}

                {!loading && !error && data && (
                    <>
                        <div
                            style={{
                                ...cardStyle,
                                marginBottom: "22px",
                                display: "flex",
                                justifyContent: "space-between",
                                flexWrap: "wrap",
                                gap: "12px",
                            }}
                        >
                            <div>
                                <div style={{ color: "#94a3b8", fontSize: "13px" }}>
                                    Business Date
                                </div>
                                <strong>{data.business_date}</strong>
                                <p style={{ color: "#94a3b8", margin: "8px 0 0" }}>
                                    Budget period: {data.week_start} to {data.week_end}
                                </p>
                            </div>

                            <div
                                style={{
                                    color: data.is_urgent ? "#fbbf24" : "#86efac",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "8px",
                                    fontWeight: 600,
                                }}
                            >
                                {data.is_urgent ? (
                                    <AlertCircle size={20} />
                                ) : (
                                    <CheckCircle2 size={20} />
                                )}
                                {data.is_urgent
                                    ? "Urgent Liquidity Status"
                                    : "Normal Liquidity Status"}
                            </div>
                        </div>

                        <div
                            style={{
                                display: "grid",
                                gridTemplateColumns:
                                    "repeat(auto-fit, minmax(210px, 1fr))",
                                gap: "16px",
                                marginBottom: "30px",
                            }}
                        >
                            {summaryCards.map((card) => {
                                const Icon = card.icon;
                                return (
                                    <div key={card.label} style={cardStyle}>
                                        <div
                                            style={{
                                                display: "flex",
                                                justifyContent: "space-between",
                                                color: "#94a3b8",
                                                fontSize: "13px",
                                            }}
                                        >
                                            {card.label}
                                            <Icon size={18} />
                                        </div>
                                        <div
                                            style={{
                                                fontSize: "21px",
                                                fontWeight: 700,
                                                marginTop: "14px",
                                            }}
                                        >
                                            {card.value}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <section style={{ marginBottom: "32px" }}>
                            <h2 style={{ fontSize: "20px", marginBottom: "16px" }}>
                                Recommended Discounts
                            </h2>

                            <div
                                style={{
                                    ...cardStyle,
                                    overflowX: "auto",
                                    padding: "0",
                                }}
                            >
                                <table
                                    style={{
                                        width: "100%",
                                        borderCollapse: "collapse",
                                        minWidth: "1200px",
                                        textAlign: "left",
                                    }}
                                >
                                    <thead>
                                        <tr style={{ color: "#94a3b8", background: "#172033" }}>
                                            {[
                                                "Invoice ID",
                                                "Buyer ID",
                                                "Invoice Amount",
                                                "Due In",
                                                "Tier",
                                                "Discount Rate",
                                                "Discount Amount",
                                                "Net Payable",
                                                "Approval",
                                                "Actions",
                                            ].map((heading) => (
                                                <th
                                                    key={heading}
                                                    style={{
                                                        padding: "15px",
                                                        fontSize: "12px",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {heading}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {data.recommendations.map((item) => {
                                            const isProcessing =
                                                actionLoadingId === item.invoice_id;

                                            return (
                                                <tr
                                                    key={item.invoice_id}
                                                    style={{
                                                        borderTop: "1px solid #263244",
                                                    }}
                                                >
                                                    <td style={{ padding: "15px" }}>
                                                        #{item.invoice_id}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {item.buyer_id}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {formatINR(item.invoice_amount)}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {item.days_until_due} days
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {item.buyer_tier}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {formatPercent(item.offered_rate_pct)}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {formatINR(item.discount_amount)}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {formatINR(item.net_payable_if_accepted)}
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        <span
                                                            style={{
                                                                color: item.requires_approval
                                                                    ? "#fbbf24"
                                                                    : "#86efac",
                                                                fontWeight: 600,
                                                            }}
                                                        >
                                                            {item.requires_approval
                                                                ? "Required"
                                                                : "Not required"}
                                                        </span>
                                                    </td>

                                                    <td style={{ padding: "15px" }}>
                                                        {item.requires_approval ? (
                                                            <div
                                                                style={{
                                                                    display: "flex",
                                                                    gap: "8px",
                                                                }}
                                                            >
                                                                <button
                                                                    onClick={() =>
                                                                        void handleOfferAction(
                                                                            item.invoice_id,
                                                                            item.buyer_id,
                                                                            "approve"
                                                                        )
                                                                    }
                                                                    disabled={
                                                                        actionLoadingId !== null
                                                                    }
                                                                    style={{
                                                                        background: "#166534",
                                                                        color: "white",
                                                                        border: 0,
                                                                        borderRadius: "6px",
                                                                        padding: "8px 12px",
                                                                        display: "inline-flex",
                                                                        alignItems: "center",
                                                                        gap: "5px",
                                                                        cursor: actionLoadingId !== null
                                                                            ? "not-allowed"
                                                                            : "pointer",
                                                                        opacity: actionLoadingId !== null
                                                                            ? 0.6
                                                                            : 1,
                                                                    }}
                                                                >
                                                                    <Check size={15} />
                                                                    {isProcessing
                                                                        ? "Processing..."
                                                                        : "Approve"}
                                                                </button>

                                                                <button
                                                                    onClick={() =>
                                                                        void handleOfferAction(
                                                                            item.invoice_id,
                                                                            item.buyer_id,
                                                                            "reject"
                                                                        )
                                                                    }
                                                                    disabled={
                                                                        actionLoadingId !== null
                                                                    }
                                                                    style={{
                                                                        background: "#991b1b",
                                                                        color: "white",
                                                                        border: 0,
                                                                        borderRadius: "6px",
                                                                        padding: "8px 12px",
                                                                        display: "inline-flex",
                                                                        alignItems: "center",
                                                                        gap: "5px",
                                                                        cursor: actionLoadingId !== null
                                                                            ? "not-allowed"
                                                                            : "pointer",
                                                                        opacity: actionLoadingId !== null
                                                                            ? 0.6
                                                                            : 1,
                                                                    }}
                                                                >
                                                                    <X size={15} />
                                                                    {isProcessing
                                                                        ? "Processing..."
                                                                        : "Reject"}
                                                                </button>
                                                            </div>
                                                        ) : (
                                                            <span
                                                                style={{
                                                                    color: "#64748b",
                                                                    fontSize: "12px",
                                                                }}
                                                            >
                                                                No action required
                                                            </span>
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>

                                {data.recommendations.length === 0 && (
                                    <p
                                        style={{
                                            padding: "24px",
                                            color: "#94a3b8",
                                            textAlign: "center",
                                        }}
                                    >
                                        No eligible discount recommendations found.
                                    </p>
                                )}
                            </div>
                        </section>

                        <section>
                            <h2 style={{ fontSize: "20px", marginBottom: "16px" }}>
                                Excluded Invoices
                            </h2>

                            <div style={cardStyle}>
                                {data.excluded_invoices.length === 0 ? (
                                    <p style={{ color: "#94a3b8" }}>
                                        No excluded invoices.
                                    </p>
                                ) : (
                                    <div style={{ display: "grid", gap: "14px" }}>
                                        {data.excluded_invoices.map((item) => (
                                            <div
                                                key={item.invoice_id}
                                                style={{
                                                    borderBottom: "1px solid #263244",
                                                    paddingBottom: "12px",
                                                }}
                                            >
                                                <strong>
                                                    Invoice #{item.invoice_id}
                                                </strong>

                                                <span
                                                    style={{
                                                        color: "#94a3b8",
                                                        marginLeft: "12px",
                                                    }}
                                                >
                                                    Buyer: {item.buyer_id}
                                                </span>

                                                <ul
                                                    style={{
                                                        color: "#fca5a5",
                                                        marginBottom: 0,
                                                    }}
                                                >
                                                    {item.reasons.map((reason, index) => (
                                                        <li key={index}>{reason}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </section>

                        <p
                            style={{
                                color: "#64748b",
                                fontSize: "12px",
                                marginTop: "24px",
                            }}
                        >
                            These are recommendations only. Offers requiring approval
                            must be approved or rejected by an authorized user.
                        </p>
                    </>
                )}
            </div>
        </div>
    );
}
