import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL
  ?? process.env.INTERNAL_API_BASE_URL
  ?? "http://127.0.0.1:8000/api/v1";

type SearchPayload = {
  query: string;
  lookback_days: number;
  limit: number;
  sort_by: "relevance" | "date";
};

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as Partial<SearchPayload>;
    const query = payload.query?.trim();

    if (!query || query.length < 3) {
      return NextResponse.json(
        { detail: "Query must be at least 3 characters long." },
        { status: 400 },
      );
    }

    const backendResponse = await fetch(`${API_BASE}/event-registry/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        lookback_days: payload.lookback_days ?? 30,
        limit: payload.limit ?? 25,
        sort_by: payload.sort_by ?? "relevance",
      } satisfies SearchPayload),
      cache: "no-store",
    });

    const responseText = await backendResponse.text();
    if (!backendResponse.ok) {
      return new Response(responseText || JSON.stringify({ detail: "Backend proxy error" }), {
        status: backendResponse.status,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
        },
      });
    }

    return new Response(responseText, {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      },
    });
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : "Не удалось выполнить проксированный Event Registry search.";

    return NextResponse.json(
      {
        detail: "Не удалось выполнить проксированный поиск через backend API. " + message,
      },
      { status: 502 },
    );
  }
}
