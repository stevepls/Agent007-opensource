"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Zap } from "lucide-react";

/**
 * Dashboard Sign-In Page
 *
 * Shows a branded sign-in page with a "Sign in with Google" button.
 * When clicked, initiates the OAuth flow through the Orchestrator.
 * Displays error messages from failed auth attempts.
 */
function LoginContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  const handleSignIn = () => {
    window.location.href = "/api/auth/start";
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      {/* Login Card */}
      <div className="w-full max-w-md">
        <div className="relative overflow-hidden rounded-2xl border border-border bg-card/50 backdrop-blur-xl shadow-2xl">
          {/* Top gradient accent */}
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-violet-500 via-purple-500 to-fuchsia-500" />

          <div className="px-8 py-12 text-center">
            {/* Logo */}
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow-lg shadow-violet-500/25">
              <Zap className="h-8 w-8 text-white" />
            </div>

            {/* Title */}
            <h1 className="mb-2 text-2xl font-bold tracking-tight gradient-text">
              Agent007
            </h1>
            <p className="mb-8 text-sm text-muted-foreground">
              Command Center
            </p>

            {/* Error message */}
            {error && (
              <div className="mb-6 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                {error}
              </div>
            )}

            {/* Sign in button */}
            <button
              onClick={handleSignIn}
              className="group flex w-full items-center justify-center gap-3 rounded-xl bg-white px-6 py-3.5 text-base font-semibold text-gray-800 shadow-md transition-all hover:bg-gray-50 hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0"
            >
              {/* Google icon */}
              <svg className="h-5 w-5 flex-shrink-0" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Sign in with Google
            </button>

            {/* Footer */}
            <p className="mt-8 text-xs text-muted-foreground/50">
              Authorized users only
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}
