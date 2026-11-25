import { NextRequest, NextResponse } from "next/server";

const GENIE_AI_URL = (
  process.env.GENIE_AI_URL ||
  process.env.NEXT_PUBLIC_GENIE_AI_URL ||
  "http://102.209.46.116:8001"
).replace(/\/+$/, "");

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ scanId: string }> },
) {
  const { scanId } = await context.params;
  const target = `${GENIE_AI_URL}/v1/scans/${encodeURIComponent(scanId)}`;
  try {
    const upstream = await fetch(target, { cache: "no-store" });
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to reach GENIE AI scan detail backend", detail: String(err) },
      { status: 502 },
    );
  }
}
