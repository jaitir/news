import { spawn } from "node:child_process";
import path from "node:path";

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PYTHON_BIN = path.join(REPO_ROOT, ".venv", "bin", "python");
const SCRIPT_PATH = path.join(REPO_ROOT, "backend", "scripts", "event_registry_search.py");
const PYTHONPATH = path.join(REPO_ROOT, "backend");

type SearchPayload = {
  query: string;
  lookback_days: number;
  limit: number;
  sort_by: "relevance" | "date";
};

function runEventRegistrySearch(payload: SearchPayload): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, [SCRIPT_PATH], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH,
      },
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });

    child.on("error", (error) => {
      reject(error);
    });

    child.on("close", (code) => {
      if (code === 0) {
        resolve(stdout);
        return;
      }
      reject(new Error(stderr.trim() || `Python process exited with code ${code}.`));
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

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

    const responseText = await runEventRegistrySearch({
      query,
      lookback_days: payload.lookback_days ?? 30,
      limit: payload.limit ?? 25,
      sort_by: payload.sort_by ?? "relevance",
    });

    return new Response(responseText, {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      },
    });
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : "Не удалось запустить локальный Event Registry search.";

    return NextResponse.json(
      {
        detail:
          "Не удалось выполнить локальный поиск через Event Registry. " +
          "Проверь наличие `.venv`, пакета `eventregistry` и ключа `EVENT_REGISTRY_API_KEY`. " +
          message,
      },
      { status: 502 },
    );
  }
}
