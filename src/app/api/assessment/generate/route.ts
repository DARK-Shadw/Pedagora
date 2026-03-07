import { NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { createClient } from "@/lib/supabase/server";

export async function POST(request: Request) {
  // Verify authentication
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { goal, prerequisites, educationLevel } = await request.json();

  if (!goal || typeof goal !== "string") {
    return NextResponse.json(
      { error: "Goal is required" },
      { status: 400 }
    );
  }

  const apiKey = process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "AI service not configured" },
      { status: 500 }
    );
  }

  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

  const prerequisitesList =
    prerequisites && Array.isArray(prerequisites) && prerequisites.length > 0
      ? prerequisites
          .map(
            (p: { skillName: string; confidenceLevel: string }) =>
              `- ${p.skillName} (self-rated: ${p.confidenceLevel})`
          )
          .join("\n")
      : "None provided";

  const prompt = `You are an education assessment expert. A student wants to learn: "${goal}"

Their education level: ${educationLevel || "not specified"}

Prerequisites they've listed:
${prerequisitesList}

Generate 5-8 skill assessment questions to gauge their actual readiness. Each question should check a foundational skill or concept they would need. Questions should be specific and actionable, not vague.

Rules:
- Questions should be answerable with a confidence level (None / Beginner / Intermediate / Advanced)
- Each question needs a brief "context" explaining why this skill matters for their goal
- Focus on prerequisites and foundational knowledge, not the target subject itself
- Order from most fundamental to more advanced
- Keep questions concise (1 sentence each)

Respond ONLY with valid JSON in this exact format, no markdown:
{
  "questions": [
    {
      "id": "q1",
      "question": "How comfortable are you with [specific skill]?",
      "context": "This matters because [reason related to their goal]."
    }
  ]
}`;

  try {
    const result = await model.generateContent(prompt);
    const text = result.response.text();

    // Parse the JSON response, handling potential markdown wrapping
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return NextResponse.json(
        { error: "Failed to parse AI response" },
        { status: 500 }
      );
    }

    const parsed = JSON.parse(jsonMatch[0]);

    if (!parsed.questions || !Array.isArray(parsed.questions)) {
      return NextResponse.json(
        { error: "Invalid AI response format" },
        { status: 500 }
      );
    }

    return NextResponse.json({ questions: parsed.questions });
  } catch (error) {
    console.error("Assessment generation error:", error);
    return NextResponse.json(
      { error: "Failed to generate assessment questions" },
      { status: 500 }
    );
  }
}
