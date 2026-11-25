import { NextRequest, NextResponse } from "next/server";

const GENIE_AI_URL = (
  process.env.GENIE_AI_URL ||
  process.env.NEXT_PUBLIC_GENIE_AI_URL ||
  "http://102.209.46.116:8001"
).replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  try {
    const incomingForm = await request.formData();
    const file = incomingForm.get("file");
    if (!file || !(file instanceof Blob)) {
      return NextResponse.json({ error: "Missing 'file' image upload" }, { status: 400 });
    }

    const upstreamForm = new FormData();
    const filename = file instanceof File && file.name ? file.name : "scan.jpg";
    upstreamForm.append("file", file, filename);

    const compareVisual = request.nextUrl.searchParams.get("compare_visual") ?? "true";
    const autoDiscover = request.nextUrl.searchParams.get("auto_discover") ?? "true";
    const target = `${GENIE_AI_URL}/v1/verify/image?compare_visual=${encodeURIComponent(
      compareVisual,
    )}&auto_discover=${encodeURIComponent(autoDiscover)}`;

    const upstream = await fetch(target, {
      method: "POST",
      body: upstreamForm,
      cache: "no-store",
    });

    const text = await upstream.text();
    try {
      const json = JSON.parse(text);
      return NextResponse.json(json, { status: upstream.status });
    } catch {
      return NextResponse.json(
        { error: "Invalid JSON from GENIE AI backend", detail: text.slice(0, 300) },
        { status: upstream.status || 502 },
      );
    }
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to reach GENIE AI verification backend", detail: String(err) },
      { status: 502 },
    );
  }
}
