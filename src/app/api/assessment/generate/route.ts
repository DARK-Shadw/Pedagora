import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function POST(request: Request) {
  // Try to get session for auth header, but don't block if unavailable
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const { goal, prerequisites, educationLevel } = await request.json();

  if (!goal || typeof goal !== "string") {
    return NextResponse.json(
      { error: "Goal is required" },
      { status: 400 }
    );
  }

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (session?.access_token) {
      headers["Authorization"] = `Bearer ${session.access_token}`;
    }

    const response = await fetch(`${BACKEND_URL}/agents/generate-assessment`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        goal_title: goal,
        education_level: educationLevel || "self_learner",
        prerequisites: prerequisites || [],
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error("Backend assessment error:", error);
      return NextResponse.json(
        { error: "Failed to generate assessment questions" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Assessment generation error:", error);
    return NextResponse.json(
      { error: "Failed to generate assessment questions" },
      { status: 500 }
    );
  }
}
