import { getToken } from "@/lib/auth";
import type { ApiResponse } from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  idempotencyKey?: string;
  isFormData?: boolean;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.idempotencyKey) headers["x-idempotency-key"] = options.idempotencyKey;

  let payload: BodyInit | undefined;
  if (options.body !== undefined) {
    if (options.isFormData) {
      payload = options.body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(options.body);
    }
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: payload
  });

  const json = (await res.json().catch(() => null)) as ApiResponse<T> | null;
  if (!res.ok) {
    const message = (json as { detail?: string } | null)?.detail ?? `Request failed: ${res.status}`;
    throw new ApiError(res.status, message);
  }
  if (!json) {
    throw new ApiError(500, "Invalid empty response");
  }
  return json.data;
}

export async function apiBlob(path: string): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE_URL}${path}`, { headers });
  if (!res.ok) {
    throw new ApiError(res.status, `Blob request failed: ${res.status}`);
  }
  return res.blob();
}
