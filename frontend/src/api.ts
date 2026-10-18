
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

async function getErrorMessage(
    response: Response,
    fallback: string
): Promise<string> {
    const error = await response.json().catch(() => null);
    return error?.detail || fallback;
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
        throw new Error(
            await getErrorMessage(response, "Login failed")
        );
    }

    return response.json();
}

export async function getCurrentUser(
    token: string
): Promise<UserProfile> {
    const response = await fetch(`${API_BASE_URL}/users/me`, {
        headers: {
            Authorization: `Bearer ${token}`,
        },
    });

    if (!response.ok) {
        throw new Error(
            await getErrorMessage(
                response,
                "Unable to fetch current user"
            )
        );
    }

    return response.json();
}

export async function getDashboardSummary(
    token: string
): Promise<DashboardSummary> {
    const response = await fetch(`${API_BASE_URL}/dashboard/summary`, {
        headers: {
            Authorization: `Bearer ${token}`,
        },
    });

    if (!response.ok) {
        throw new Error(
            await getErrorMessage(
                response,
                response.status === 401
                    ? "Session expired. Please log in again."
                    : "Unable to load dashboard summary."
            )
        );
    }

    return response.json();
}

export async function getDashboardInvoices(
    token: string,
    limit = 10
): Promise<DashboardInvoice[]> {
    const response = await fetch(
        `${API_BASE_URL}/dashboard/invoices?limit=${limit}`,
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        }
    );

    if (!response.ok) {
        throw new Error(
            await getErrorMessage(
                response,
                response.status === 401
                    ? "Session expired. Please log in again."
                    : "Unable to load invoices."
            )
        );
    }

    return response.json();
}

export function logout(): void {
    localStorage.removeItem("access_token");
    localStorage.removeItem("username");
    localStorage.removeItem("role");
    localStorage.removeItem("token");
    localStorage.removeItem("user_profile");
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

    const response = await fetch(
        `${API_BASE_URL}/buyers/${encodeURIComponent(buyerId)}/score${params}`,
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        }
    );

    if (!response.ok) {
        throw new Error(
            await getErrorMessage(
                response,
                response.status === 401
                    ? "Session expired. Please log in again."
                    : "Unable to load buyer score."
            )
        );
    }

    return response.json();
}
