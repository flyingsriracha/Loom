"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { PortalConfigCard } from "@/components/portal-config-card";
import { TraceExplorer } from "@/components/trace-explorer";
import { JourneyDashboard } from "@/components/journey-dashboard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEFAULT_CONFIG, fetchDashboardOverview, PortalConfig } from "@/lib/loom-api";

export function LoomPortalShell() {
  const [draftConfig, setDraftConfig] = useState<PortalConfig>(DEFAULT_CONFIG);
  const [activeConfig, setActiveConfig] = useState<PortalConfig | null>(null);
  const [query, setQuery] = useState("What are XCP timing constraints?");
  const [autoRunToken, setAutoRunToken] = useState(0);
  const connectMutation = useMutation({
    mutationFn: async (nextConfig: PortalConfig) => fetchDashboardOverview(nextConfig),
    onSuccess: (_, variables) => {
      setActiveConfig(variables);
    },
  });

  const connectionState = connectMutation.isPending
    ? { status: "connecting" as const, message: "Verifying Loom connection..." }
    : connectMutation.isError
      ? { status: "error" as const, message: connectMutation.error.message }
      : activeConfig
        ? { status: "connected" as const, message: `Connected to ${activeConfig.baseUrl}` }
        : { status: "idle" as const, message: "Connect first to load the dashboard and traces." };

  const handleConnect = () => {
    connectMutation.mutate(draftConfig);
  };

  const handleGuidedExample = (nextQuery: string) => {
    setQuery(nextQuery);
    if (activeConfig) {
      setAutoRunToken((token) => token + 1);
      return;
    }
    connectMutation.mutate(draftConfig, {
      onSuccess: (_, variables) => {
        setActiveConfig(variables);
        setAutoRunToken((token) => token + 1);
      },
    });
  };

  return (
    <div className="min-h-screen bg-zinc-100 text-zinc-950">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10">
        <header className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="rounded-full px-3 py-1">Loom Portal</Badge>
            <Badge variant="outline" className="rounded-full px-3 py-1">Onboarding + Traceability + Journey</Badge>
          </div>
          <div className="space-y-2">
            <h1 className="text-4xl font-semibold tracking-tight">A novice-first control tower for the Loom runtime</h1>
            <p className="max-w-3xl text-base leading-7 text-zinc-600">
              This portal sits on top of the existing Loom orchestrator and knowledge services. It turns knowledge provenance,
              Hindsight memory traces, CMM impact analysis, and LangGraph workflow context into one place a new user can actually follow.
            </p>
          </div>
        </header>

        <div className="grid gap-6 xl:grid-cols-[1.05fr_1.35fr]">
          <div className="space-y-6">
            <PortalConfigCard
              config={draftConfig}
              onChange={setDraftConfig}
              onConnect={handleConnect}
              onUseSample={handleGuidedExample}
              connectionState={connectionState}
            />
            <Card className="border-zinc-200 bg-white/90 shadow-sm">
              <CardHeader>
                <CardTitle>Why this matters</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm leading-6 text-zinc-600">
                <p>New users should not need to understand MCP, prompt engineering, or the internal module split before they can trust a result.</p>
                <p>The portal keeps the advanced systems intact, but makes the outcome readable with plain-language panels, guided examples, and drill-down traces.</p>
              </CardContent>
            </Card>
          </div>

          <TraceExplorer config={activeConfig} initialQuery={query} onQueryChange={setQuery} autoRunToken={autoRunToken} />
        </div>

        <JourneyDashboard config={activeConfig} />
      </div>
    </div>
  );
}
