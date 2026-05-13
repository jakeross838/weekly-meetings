import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  let body: { id?: string; title?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON" },
      { status: 400 }
    );
  }
  const id = body.id?.trim();
  const title = body.title?.trim();
  if (!id || !title) {
    return NextResponse.json(
      { ok: false, error: "Missing id or title" },
      { status: 400 }
    );
  }
  if (title.length > 600) {
    return NextResponse.json(
      { ok: false, error: "Title too long" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();
  const { error } = await supabase
    .from("todos")
    .update({ edited_title: title, edited_at: new Date().toISOString() })
    .eq("id", id);
  if (error) {
    return NextResponse.json(
      { ok: false, error: error.message },
      { status: 500 }
    );
  }
  return NextResponse.json({ ok: true });
}
