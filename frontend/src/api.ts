
const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface LoginResponse {
    access_token: string;
    token_type: string;
}

export interface UserProfile {
    id?: number;
    username: string;
    email?: string | null;
    role: string;
    company_id?: number | null;
}

export interface DashboardSummary {
    eligible_invoice_value: string;
    eligible_invoice_count: number;
    historical_late_rate: number;
    weekly_discount_budget: string;
    total_buyers: number;
    buyer_tiers: Record<
        string,
        {
            count: number;
            percentage: number;
        }
    >;
    currency: string;
}

export interface DashboardInvoice {
    invoice_id: number;
    buyer_id: string;
    invoice_amount: string;
    formatted_amount: string;
    invoice_date: string;
    due_date: string;
    days_until_due: number;
    tier: string | null;
    invoice_status: string;
    disputed: boolean;
    eligibility_status: string;
}

export class ApiError extends Error {
    status: number;
    detail?: string;

    constructor(status: number, message: string, detail?: string) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.detail = detail;
    }
}

export function logout(): void {
    const hadAuth = Boolean(
        localStorage.getItem("access_token") ||
        localStorage.getItem("username") ||
        localStorage.getItem("role")
    );

    localStorage.removeItem("access_token");
    localStorage.removeItem("username");
    localStorage.removeItem("role");
    localStorage.removeItem("token");
    localStorage.removeItem("user_profile");

    if (hadAuth) {
        window.dispatchEvent(new CustomEvent("auth:logout"));
    }
}

export function handleUnauthorized(): void {
    if (!localStorage.getItem("access_token")) {
        return;
    }

    logout();
}

async function getErrorMessage(
    response: Response,
    fallback: string
): Promise<string> {
    const error = await response.json().catch(() => null);
    return error?.detail || fallback;
}

export async function authFetch(
    url: string,
    token: string,
    init?: RequestInit
): Promise<Response> {
    const headers = new Headers(init?.headers);

    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(url, {
        ...init,
        headers,
    });

    if (response.status === 401) {
        handleUnauthorized();

        const detail = await getErrorMessage(
            response,
            "Session expired. Please log in again."
        );

        throw new ApiError(401, detail, detail);
    }

    return response;
}

export async function login(
    username: string,
    password: string
): Promise<LoginResponse> {
    const formData = new URLSearchParams();

    formData.append("username", username);
    formData.append("password", password);

    const response = await fetch(`${API_BASE_URL}/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData,
    });

    if (!response.ok) {
        const errorMsg = await getErrorMessage(response, "Login failed");
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export async function getCurrentUser(
    token: string
): Promise<UserProfile> {
    const response = await authFetch(`${API_BASE_URL}/users/me`, token);

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to fetch current user"
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export async function getDashboardSummary(
    token: string
): Promise<DashboardSummary> {
    const response = await authFetch(
        `${API_BASE_URL}/dashboard/summary`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to load dashboard summary."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export async function getDashboardInvoices(
    token: string,
    limit = 10
): Promise<DashboardInvoice[]> {
    const response = await authFetch(
        `${API_BASE_URL}/dashboard/invoices?limit=${limit}`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to load invoices."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export interface BuyerScore {
    buyer_id: string;
    resolved_invoice_count: number;
    late_rate: number;
    avg_days_late: number;
    late_rate_last_5_settled: number;
    open_exposure: number;
    overdue_open_exposure: number;
    credit_limit: number;
    as_of_date: string;
    reliability_score: number | null;
    financial_score: number | null;
    liquidity_score: number | null;
    overall_score: number | null;
    tier: "A" | "B" | "C" | null;
    tier_basis: "scored" | "cold_start" | "scoring_blocked";
    status:
    | "calculated"
    | "provisional"
    | "credit_limit_decision_required";
}

export async function getBuyerScore(
    token: string,
    buyerId: string,
    asOfDate?: string
): Promise<BuyerScore> {
    const params = asOfDate
        ? `?as_of_date=${encodeURIComponent(asOfDate)}`
        : "";

    const response = await authFetch(
        `${API_BASE_URL}/buyers/${encodeURIComponent(buyerId)}/score${params}`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to load buyer score."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export async function calculateAndPersistBuyerScore(
    token: string,
    buyerId: string,
    asOfDate?: string
): Promise<BuyerScore> {
    const params = asOfDate
        ? `?as_of_date=${encodeURIComponent(asOfDate)}`
        : "";

    const response = await authFetch(
        `${API_BASE_URL}/buyers/${encodeURIComponent(buyerId)}/score${params}`,
        token,
        {
            method: "POST",
        }
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to calculate and persist buyer score."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export interface BuyerItem {
    buyer_id: string;
    tier?: string | null;
    credit_limit?: number | string | null;
    primary_supplier_id?: string;
    behavioural_segment?: string | null;
    blacklisted?: boolean;
}

export interface BuyersPage {
    items: BuyerItem[];
    total: number;
    page: number;
    page_size: number;
}

export async function getBuyers(
    token: string,
    page = 1,
    pageSize = 20
): Promise<BuyersPage> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    });

    const response = await authFetch(
        `${API_BASE_URL}/buyers?${params.toString()}`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            response.status === 404
                ? "Buyers list API abhi backend mein available nahi hai."
                : `Buyers load nahi hue (${response.status}).`
        );

        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    const data = await response.json();

    if (!Array.isArray(data) && Array.isArray(data.items)) {
        return {
            items: data.items,
            total: Number(data.total ?? data.items.length),
            page: Number(data.page ?? page),
            page_size: Number(data.page_size ?? pageSize),
        };
    }

    if (Array.isArray(data)) {
        return {
            items: data,
            total: data.length,
            page: 1,
            page_size: data.length || pageSize,
        };
    }

    throw new Error("Backend se buyers list ka format unexpected hai.");
}

export interface Invoice {
    invoice_id: number;
    buyer_id: string;
    supplier_id: string;
    invoice_date: string;
    due_date: string;
    payment_terms_days: number;
    invoice_amount: number | string;
    currency: string;
    disputed: boolean;
    invoice_status: string;
    settled_date: string | null;
    days_late: number | null;
    is_late: boolean | null;
    days_until_due: number | null;
    overdue_days: number;
    created_at: string | null;
    updated_at: string | null;
}

export interface InvoiceMetric {
    count: number;
    total_amount: number | string;
}

export interface InvoiceSummary {
    open: InvoiceMetric;
    overdue: InvoiceMetric;
    settled: InvoiceMetric;
    disputed: InvoiceMetric;
    open_count: number;
    open_total: number | string;
    overdue_count: number;
    overdue_total: number | string;
    settled_count: number;
    settled_total: number | string;
    disputed_count: number;
    disputed_total: number | string;
}

export interface InvoiceBuyer {
    buyer_id: string;
    country_code: string | null;
    tier: string | null;
    credit_limit: number | string | null;
    blacklisted: boolean | null;
}

export interface InvoicePayment {
    payment_id: number;
    invoice_id: number;
    payment_date: string;
    payment_amount: number | string;
    payment_method: string | null;
    reference_number: string | null;
    status: string;
    discount_applied: number | string;
    created_at: string | null;
}

export interface InvoiceDetail extends Invoice {
    buyer: InvoiceBuyer | null;
    payments: InvoicePayment[];
}

export interface InvoicesPage {
    items: Invoice[];
    total: number;
    page: number;
    page_size: number;
}

export interface InvoiceFilters {
    buyer_id?: string;
    supplier_id?: string;
    invoice_status?: "open" | "settled";
    is_late?: boolean;
    disputed?: boolean;
    invoice_date_from?: string;
    invoice_date_to?: string;
    due_date_from?: string;
    due_date_to?: string;
    min_amount?: number;
    max_amount?: number;
    sort_by?: "invoice_date" | "due_date" | "invoice_amount";
    order?: "asc" | "desc";
}

export async function getInvoicesSummary(
    token: string
): Promise<InvoiceSummary> {
    const response = await authFetch(
        `${API_BASE_URL}/invoices/summary`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to load invoice summary."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export async function getInvoices(
    token: string,
    page = 1,
    pageSize = 20,
    filters: InvoiceFilters = {}
): Promise<InvoicesPage> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    });

    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
            params.set(key, String(value));
        }
    });

    const response = await authFetch(
        `${API_BASE_URL}/invoices?${params.toString()}`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to load invoices."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export async function getInvoiceDetail(
    token: string,
    invoiceId: number
): Promise<InvoiceDetail> {
    const response = await authFetch(
        `${API_BASE_URL}/invoices/${encodeURIComponent(invoiceId)}`,
        token
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to load invoice details."
        );
        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

// --- Late Payment Prediction API ---
export interface LatePaymentPredictionRequest {
    invoice_id: number;
    invoice_amount: number; // INR amount (backend will convert if >1000)
    invoice_month: number; // 1-12 derived from invoice_date
    invoice_dow: number; // 0=Mon … 6=Sun derived from invoice_date
    has_history: 0 | 1; // 1 if buyer historical features are available
    outstanding_amount_at_invoice: number; // source scale (₹000) – unknown set to 0
    outstanding_count_at_invoice: number; // unknown set to 0
    buyer_hist_late_rate?: number | null;
    buyer_hist_avg_delay_days?: number | null;
    buyer_hist_delay_std?: number | null;
    buyer_hist_max_delay?: number | null;
    country_code?: string | null;
    paperless_bill?: string | null;
}

export interface LatePaymentPredictionResponse {
    late_probability: number; // 0‑1
    predicted_label: number; // 0=on‑time, 1=late
}

export async function predictInvoiceLatePayment(
    token: string,
    invoiceId: number,
    payload: LatePaymentPredictionRequest,
): Promise<LatePaymentPredictionResponse> {
    const url = `${API_BASE_URL}/invoices/${invoiceId}/predict`;
    const response = await authFetch(url, token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const errMsg = await getErrorMessage(response, "Prediction request failed");
        throw new ApiError(response.status, errMsg, errMsg);
    }
    return response.json();
}

export interface AutoLatePaymentPredictionResponse {
    late_probability: number;
    predicted_label: number;
    threshold: number;
    model_name: string;
    model_version: string;
    features_used: Record<string, number | string | null>;
    calibrated: boolean;
    scored_at: string;
}

export async function predictInvoiceLatePaymentAuto(
    token: string,
    invoiceId: number,
): Promise<AutoLatePaymentPredictionResponse> {
    const url = `${API_BASE_URL}/invoices/${encodeURIComponent(invoiceId)}/predict/auto`;

    const response = await authFetch(url, token, {
        method: "POST",
    });

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to predict late-payment risk for this invoice.",
        );

        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}

export interface RagCitation {
    index: number;
    document_name: string;
    document_type: string;
    version: string;
    chunk_index: number;
}

export interface RagSourceChunk {
    document_name: string;
    document_type: string;
    version: string;
    chunk_index: number;
    chunk_text: string;
    distance: number;
}

export interface RagAnswerResponse {
    answer: string;
    citations: RagCitation[];
    source_chunks: RagSourceChunk[];
}

export async function askRagQuestion(
    token: string,
    query: string,
    limit = 5,
): Promise<RagAnswerResponse> {
    const response = await authFetch(
        `${API_BASE_URL}/rag/answer`,
        token,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                query,
                limit,
            }),
        },
    );

    if (!response.ok) {
        const errorMsg = await getErrorMessage(
            response,
            "Unable to generate a policy explanation.",
        );

        throw new ApiError(response.status, errorMsg, errorMsg);
    }

    return response.json();
}
