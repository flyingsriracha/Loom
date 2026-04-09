"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PortalConfig } from "@/lib/loom-api";

type ConnectionState = {
  status: "idle" | "connecting" | "connected" | "error";
  message?: string;
};

type Props = {
  config: PortalConfig;
  onChange: (next: PortalConfig) => void;
  onConnect: () => void;
  onUseSample: (query: string) => void;
  connectionState: ConnectionState;
};

const guidedQueries = [
  "What are XCP timing constraints?",
  "Where did we leave off on this objective?",
  "Fix the AUTOSAR Ethernet configuration workflow",
];

export function PortalConfigCard({ config, onChange, onConnect, onUseSample, connectionState }: Props) {
  const update = (key: keyof PortalConfig, value: string) =>
    onChange({
      ...config,
      [key]: value,
    });

  return (
    <Card className="border-zinc-200 bg-white/90 shadow-sm">
      <CardHeader>
        <CardTitle>First-Run Wizard</CardTitle>
        <CardDescription>
          Enter the same Loom context that your IDE agent uses, verify the connection, then run a guided example.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <Input value={config.baseUrl} onChange={(event) => update("baseUrl", event.target.value)} placeholder="http://localhost:8080" />
          <Input value={config.apiKey} onChange={(event) => update("apiKey", event.target.value)} placeholder="X-API-Key (optional in local dev)" />
          <Input value={config.engineerId} onChange={(event) => update("engineerId", event.target.value)} placeholder="engineer_id" />
          <Input value={config.sessionId} onChange={(event) => update("sessionId", event.target.value)} placeholder="session_id" />
          <Input value={config.objectiveId} onChange={(event) => update("objectiveId", event.target.value)} placeholder="objective_id" />
          <Input value={config.projectId} onChange={(event) => update("projectId", event.target.value)} placeholder="project_id" />
        </div>
        <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-600">
          <p className="font-medium text-zinc-900">How to think about the IDs</p>
          <p>`project_id` = what you are building. `objective_id` = the goal inside that project. `session_id` = this conversation run.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onConnect} disabled={connectionState.status === "connecting"}>
            {connectionState.status === "connecting" ? "Connecting..." : "Apply connection"}
          </Button>
          <span className="text-sm text-zinc-600">
            {connectionState.status === "connected"
              ? connectionState.message ?? "Connected to Loom successfully."
              : connectionState.status === "error"
                ? connectionState.message ?? "Connection failed."
                : "Connect first to load the dashboard and traces."}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {guidedQueries.map((query) => (
            <Button key={query} variant="outline" onClick={() => onUseSample(query)}>
              Run guided example
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
