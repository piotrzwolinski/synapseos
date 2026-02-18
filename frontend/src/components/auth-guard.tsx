"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { isAuthenticated, getToken, clearToken, setUserInfo } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    const checkAuth = async () => {
      // First check if we have a token
      if (!isAuthenticated()) {
        setChecking(false);
        router.push("/login");
        return;
      }

      // Verify the token with the backend
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);

        const response = await fetch(`${API_BASE_URL}/auth/verify`, {
          headers: {
            Authorization: `Bearer ${getToken()}`,
          },
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (response.ok) {
          const data = await response.json();
          if (data.username && data.role) {
            setUserInfo(data.username, data.role);
          }
          setAuthenticated(true);
        } else {
          // Token invalid or expired
          clearToken();
          router.push("/login");
        }
      } catch {
        // Backend not reachable or timeout - allow access if token exists (offline mode)
        setAuthenticated(true);
      } finally {
        setChecking(false);
      }
    };

    checkAuth();
  }, [router]);

  if (checking) {
    return (
      <div className="min-h-screen bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-green-700" />
          <p className="text-sm text-slate-500 dark:text-slate-400">Verifying authentication...</p>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return null;
  }

  return <>{children}</>;
}
