"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

/**
 * Room code resolver — converts a share link into a teaching session.
 * Flow: resolve room code → create session → redirect to classroom.
 */
export default function JoinClassroomPage() {
  const params = useParams();
  const router = useRouter();
  const roomCode = params.roomCode as string;
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Resolving classroom link...");

  useEffect(() => {
    if (!roomCode) return;

    async function join() {
      try {
        // Step 1: Resolve room code → goal_id + lesson_id
        setStatus("Looking up classroom...");
        const resolveRes = await fetch(`${BACKEND_URL}/teacher/share/${roomCode}`);
        if (!resolveRes.ok) {
          setError("This classroom link is invalid or has expired.");
          return;
        }
        const { goal_id, lesson_id } = await resolveRes.json();

        // Step 2: Get auth token
        setStatus("Authenticating...");
        const supabase = createClient();
        const { data: authData } = await supabase.auth.getSession();
        const token = authData.session?.access_token;
        if (!token) {
          // Redirect to login with return URL
          router.push(`/login?redirect=/classroom/join/${roomCode}`);
          return;
        }

        // Step 3: Create teaching session
        setStatus("Setting up your lesson...");
        const sessionRes = await fetch(`${BACKEND_URL}/teacher/sessions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ goal_id, lesson_id }),
        });

        if (!sessionRes.ok) {
          const err = await sessionRes.json();
          setError(err.detail || "Failed to create session.");
          return;
        }

        const { session_id } = await sessionRes.json();

        // Step 4: Redirect to classroom
        router.replace(`/classroom/v2/${session_id}`);
      } catch (e) {
        console.error("[Join] Error:", e);
        setError("Something went wrong. Please try again.");
      }
    }

    join();
  }, [roomCode, router]);

  if (error) {
    return (
      <div className="fixed inset-0 bg-[#0d1117] flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md mx-4">
          <span className="material-symbols-rounded text-red-400 text-[48px]">error</span>
          <p className="text-white text-lg">{error}</p>
          <button
            onClick={() => router.push("/dashboard")}
            className="px-5 py-2.5 bg-white/10 hover:bg-white/15 text-white rounded-xl text-sm"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-[#0d1117] flex items-center justify-center">
      <div className="text-center space-y-4">
        <span className="material-symbols-rounded text-[#0d968b] text-[48px] animate-spin">
          progress_activity
        </span>
        <p className="text-white/60 text-sm">{status}</p>
      </div>
    </div>
  );
}
