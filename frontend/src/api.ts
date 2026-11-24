// Типы и обёртка над нашим FastAPI (/api/*)

export type RefItem = { id: number; name: string | null };

export type Offer = {
  id: number;
  name: string;
  state: string | null;
  country: string[] | null;
};

export type StreamOffer = { offer_id: number; name: string; share: number; state: string; pinned: boolean };

export type PublishOffers = {
  offers: { offer_id: number }[];
  base: { offer_id: number; share: number }[];
};

export type RemovedStreamOffer = { offer_id: number; name: string; share: number; state: string; removed_at: string };

export type StreamFilter = { name: string; mode?: string; payload?: unknown };

export type Stream = {
  id: number;
  name: string | null;
  type: string | null;
  stream_schema: string | null;
  position: number | null;
  state: string | null;
  action_type: string | null;
  action_payload: unknown;
  filters: StreamFilter[];
  offers: StreamOffer[];
  removed_offers: RemovedStreamOffer[];
  total_share: number;
  editable: boolean;
};

export type Campaign = {
  id: number;
  name: string;
  alias: string | null;
  state: string | null;
  domain: RefItem | null;
  group: RefItem | null;
  traffic_source: RefItem | null;
  keitaro_url: string;
  tracking_url: string | null;
  created_by_wrapper: boolean;
  geo: string[] | null;
};

export type CampaignDetails = Campaign & { streams: Stream[] };

export type Operation = {
  id: number;
  operation: string;
  campaign_id: number | null;
  stream_id: number | null;
  payload: Record<string, unknown> | null;
  success: boolean;
  error: string | null;
  created_at: string;
};

export type Meta = {
  keitaro_admin_url: string;
  google_url: string;
  domain: RefItem;
  group: RefItem;
  traffic_source: RefItem;
};

export type CampaignCreate = { name: string; geo: string[]; offer_id: number };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // ошибки валидации Pydantic: [{loc, msg, ...}]
    return detail
      .map((e) => String((e as { msg?: string }).msg ?? e).replace(/^Value error, /, ""))
      .join("; ");
  }
  return null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Сервер недоступен");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = formatDetail((data as { detail?: unknown } | null)?.detail);
    throw new ApiError(res.status, detail ?? `HTTP ${res.status}`);
  }
  return data as T;
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  countries: () => request<string[]>("/api/countries"),
  searchOffers: (q: string, signal?: AbortSignal) =>
    request<Offer[]>(`/api/offers?q=${encodeURIComponent(q)}&limit=20`, { signal }),
  refreshOffers: () => request<{ count: number }>("/api/offers/refresh", { method: "POST" }),

  listCampaigns: (offset = 0, limit = 50) =>
    request<Campaign[]>(`/api/campaigns?offset=${offset}&limit=${limit}`),
  getCampaign: (id: number) => request<CampaignDetails>(`/api/campaigns/${id}`),
  createCampaign: (body: CampaignCreate) =>
    request<CampaignDetails>("/api/campaigns", { method: "POST", body: JSON.stringify(body) }),
  deleteCampaign: (id: number) => request<void>(`/api/campaigns/${id}`, { method: "DELETE" }),
  operations: (id: number) => request<Operation[]>(`/api/campaigns/${id}/operations`),

  getStream: (streamId: number) => request<Stream>(`/api/streams/${streamId}`),
  publishOffers: (streamId: number, body: PublishOffers) =>
    request<Stream>(`/api/streams/${streamId}/offers`, { method: "PUT", body: JSON.stringify(body) }),
  pinOffer: (streamId: number, offerId: number) =>
    request<Stream>(`/api/streams/${streamId}/offers/${offerId}/pin`, { method: "PUT" }),
  unpinOffer: (streamId: number, offerId: number) =>
    request<Stream>(`/api/streams/${streamId}/offers/${offerId}/pin`, { method: "DELETE" }),
};
