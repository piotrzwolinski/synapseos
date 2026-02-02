"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Database, GitBranch, CheckCircle, XCircle } from "lucide-react";

interface GraphStats {
  nodes: number;
  relationships: number;
  connected: boolean;
}

export function GraphStats() {
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch("http://localhost:8000/graph/stats");
        if (!response.ok) {
          throw new Error("Failed to fetch graph stats");
        }
        const data = await response.json();
        setStats(data);
        setError(null);
      } catch (err) {
        setError("Unable to connect to database");
        setStats(null);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-xl flex items-center gap-2">
          <Database className="h-5 w-5" />
          Neo4j Graph Database
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="flex items-center gap-2 text-destructive">
            <XCircle className="h-4 w-4" />
            {error}
          </div>
        ) : stats ? (
          <div className="grid grid-cols-3 gap-4">
            <div className="flex items-center gap-2">
              {stats.connected ? (
                <CheckCircle className="h-4 w-4 text-green-500" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              <span className="text-sm">
                {stats.connected ? "Connected" : "Disconnected"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">{stats.nodes} nodes</span>
            </div>
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">{stats.relationships} relationships</span>
            </div>
          </div>
        ) : (
          <div className="text-muted-foreground">Loading...</div>
        )}
      </CardContent>
    </Card>
  );
}
