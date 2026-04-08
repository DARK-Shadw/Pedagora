import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({
            request,
          });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // IMPORTANT: Do NOT run code between createServerClient and
  // supabase.auth.getUser(). A simple mistake could make it very
  // hard to debug issues with users being randomly logged out.

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;

  // Public routes that don't need auth
  const isPublicRoute =
    pathname === "/" ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname === "/favicon.ico";

  const isAuthRoute = pathname === "/login" || pathname === "/signup" || pathname === "/callback";

  const isProtectedRoute =
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/courses") ||
    pathname.startsWith("/sessions") ||
    pathname.startsWith("/agents") ||
    pathname.startsWith("/insights") ||
    pathname.startsWith("/settings") ||
    pathname.startsWith("/onboarding") ||
    pathname.startsWith("/classroom");

  // Not logged in + trying to access protected route → redirect to login
  if (!user && isProtectedRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Logged in + on auth route → redirect based on onboarding status
  if (user && isAuthRoute) {
    // Fetch profile to check onboarding status
    const { data: profile } = await supabase
      .from("profiles")
      .select("onboarding_status")
      .eq("id", user.id)
      .single();

    const url = request.nextUrl.clone();
    if (profile?.onboarding_status === "completed") {
      url.pathname = "/dashboard";
    } else {
      url.pathname = "/onboarding/goal";
    }
    return NextResponse.redirect(url);
  }

  // Logged in + on app route + onboarding not completed → redirect to onboarding
  // Skip this check for classroom routes (students may join via shared link)
  if (user && isProtectedRoute && !pathname.startsWith("/onboarding") && !pathname.startsWith("/classroom")) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("onboarding_status")
      .eq("id", user.id)
      .single();

    if (profile && profile.onboarding_status !== "completed") {
      const url = request.nextUrl.clone();
      url.pathname = "/onboarding/goal";
      return NextResponse.redirect(url);
    }
  }

  return supabaseResponse;
}
