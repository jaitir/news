import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL
  ?? process.env.INTERNAL_API_BASE_URL
  ?? "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const backendResponse = await fetch(`${API_BASE}/event-registry/narratives`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const responseText = await backendResponse.text();
    return new Response(
      responseText || JSON.stringify({ detail: "Backend proxy error" }),
      {
        status: backendResponse.status,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
        },
      },
    );
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : "Не удалось выполнить проксированный AI narratives request.";
    return NextResponse.json(
      {
        detail: "Не удалось выполнить AI-аналитику через backend API. " + message,
      },
      { status: 502 },
    );
  }
}
