import type {
  EventRegistrySearchRequest,
  EventRegistrySearchResponse,
  EventRegistryNarrativesRequest,
  EventRegistryNarrativesResponse,
  ProviderStatus,
  SearchReport,
  SearchHistoryResponse,
  SearchPayload,
  SearchResponse,
  TranslationPreview,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";
const DIRECT_BACKEND_API_BASE =
  process.env.NEXT_PUBLIC_DIRECT_BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export type ExportFormat = "excel" | "docx";

const DEVICE_STORAGE_KEY = "media-intel-device-id";
const EXPORT_BASE = process.env.NEXT_PUBLIC_EXPORT_BASE_URL ?? API_BASE;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildDeviceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `device-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getDeviceId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const existing = window.localStorage.getItem(DEVICE_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created = buildDeviceId();
  window.localStorage.setItem(DEVICE_STORAGE_KEY, created);
  return created;
}

function withDeviceHeaders(init: RequestInit = {}): RequestInit {
  const deviceId = getDeviceId();
  const headers = new Headers(init.headers);
  if (deviceId) {
    headers.set("X-Device-Id", deviceId);
  }
  return {
    ...init,
    headers,
  };
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const fallback = "The request failed.";
    const text = await response.text().catch(() => "");
    if (!text) {
      throw new Error(fallback);
    }

    let message = text;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      message = payload.detail ?? text;
    } catch {}

    throw new ApiError(message || fallback, response.status);
  }

  return (await response.json()) as T;
}

export async function fetchProviderStatuses(): Promise<ProviderStatus[]> {
  const response = await fetch(`${API_BASE}/searches/providers/statuses`, withDeviceHeaders({
    cache: "no-store",
  }));
  return parseJson<ProviderStatus[]>(response);
}

export async function fetchHistory(): Promise<SearchHistoryResponse> {
  const response = await fetch(`${API_BASE}/searches?limit=20`, withDeviceHeaders({
    cache: "no-store",
  }));
  return parseJson<SearchHistoryResponse>(response);
}

export async function runSearch(payload: SearchPayload): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/searches`, withDeviceHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));
  return parseJson<SearchResponse>(response);
}

export async function fetchSnapshot(snapshotId: string): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/searches/${snapshotId}`, withDeviceHeaders({
    cache: "no-store",
  }));
  return parseJson<SearchResponse>(response);
}

export async function fetchReport(snapshotId: string): Promise<SearchReport> {
  const response = await fetch(`${API_BASE}/searches/${snapshotId}/report`, withDeviceHeaders({
    cache: "no-store",
  }));
  return parseJson<SearchReport>(response);
}

export function exportSnapshotUrl(snapshotId: string, format: ExportFormat = "excel"): string {
  const deviceId = getDeviceId();
  const params = new URLSearchParams();
  params.set("format", format);
  if (deviceId) {
    params.set("device_id", deviceId);
  }
  return `${EXPORT_BASE}/searches/${snapshotId}/export${params.size ? `?${params.toString()}` : ""}`;
}

export async function fetchTranslationPreview(
  text: string,
  source_language?: string | null,
): Promise<TranslationPreview> {
  const response = await fetch(`${API_BASE}/translations/preview`, {
    ...withDeviceHeaders({
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        source_language,
        target_language: "ru",
      }),
    }),
  });
  return parseJson<TranslationPreview>(response);
}

export async function searchEventRegistryNews(
  payload: EventRegistrySearchRequest,
): Promise<EventRegistrySearchResponse> {
  const response = await fetch("/api/v1/event-registry/search", withDeviceHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));
  return parseJson<EventRegistrySearchResponse>(response);
}

export async function analyzeEventRegistryNarratives(
  payload: EventRegistryNarrativesRequest,
): Promise<EventRegistryNarrativesResponse> {
  const narrativesEndpoint =
    typeof window !== "undefined" && API_BASE.startsWith("/")
      ? `${DIRECT_BACKEND_API_BASE}/event-registry/narratives`
      : `${API_BASE}/event-registry/narratives`;

  const response = await fetch(narrativesEndpoint, withDeviceHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));
  return parseJson<EventRegistryNarrativesResponse>(response);
}
