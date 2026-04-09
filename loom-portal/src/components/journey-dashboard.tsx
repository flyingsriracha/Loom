"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, BookOpen, BrainCircuit, GitBranchPlus, History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchDashboardJourney, fetchDashboardOverview, PortalConfig } from "@/lib/loom-api";

type Props = {
  config: PortalConfig | null;
};

const icons = {
  knowledge_query: BookOpen,
  memory_recall: BrainCircuit,
  memory_retain: BrainCircuit,
  memory_reflect: BrainCircuit,
  code_impact: GitBranchPlus,
  artifact_revision: History,
  hitl_checkpoint: Activity,
} as const;

export function JourneyDashboard({ config }: Props) {
  const overview = useQuery({
    queryKey: ["overview", config?.baseUrl, config?.projectId, config?.objectiveId, config?.sessionId, config?.engineerId],
    queryFn: () => fetchDashboardOverview(config as PortalConfig),
    enabled: Boolean(config),
  });
  const journey = useQuery({
    queryKey: ["journey", config?.baseUrl, config?.projectId, config?.objectiveId, config?.sessionId, config?.engineerId],
    queryFn: () => fetchDashboardJourney(config as PortalConfig),
    enabled: Boolean(config),
  });

  return (
    <div className="space-y-4">
      <Card className="border-zinc-200 bg-white/90 shadow-sm">
        <CardHeader>
          <CardTitle>Development Journey</CardTitle>
          <CardDescription>
            A plain-language overview of what Loom has done for this objective so far.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          {!config
            ? <div className="col-span-full rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-4 text-sm text-zinc-600">Apply a connection above to load the live dashboard.</div>
            : overview.isLoading
              ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-24 w-full" />)
              : [
                  ["Knowledge queries", overview.data?.progress.knowledge_queries ?? 0],
                  ["Memory events", overview.data?.progress.memory_events ?? 0],
                  ["Artifact revisions", overview.data?.progress.artifact_revisions ?? 0],
                  ["Code events", overview.data?.progress.code_events ?? 0],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                    <p className="text-sm text-zinc-500">{label}</p>
                    <p className="mt-2 text-3xl font-semibold text-zinc-950">{value}</p>
                  </div>
                ))}
        </CardContent>
      </Card>

      <Card className="border-zinc-200 bg-white/90 shadow-sm">
        <CardHeader>
          <CardTitle>Current Objective Snapshot</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-zinc-700">
          {!config ? <p className="text-zinc-500">No active connection yet.</p> : null}
          {overview.isLoading ? <Skeleton className="h-24 w-full" /> : null}
          {overview.data?.objective.summary ? <p>{overview.data.objective.summary}</p> : null}
          {Object.entries(overview.data?.objective.sections ?? {}).map(([section, items]) => (
            <div key={section} className="rounded-lg border border-zinc-200 p-3">
              <p className="font-medium text-zinc-900">{section}</p>
              <ul className="mt-2 space-y-1 text-zinc-600">
                {items.slice(0, 3).map((item) => (
                  <li key={item}>- {item}</li>
                ))}
              </ul>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="border-zinc-200 bg-white/90 shadow-sm">
        <CardHeader>
          <CardTitle>Recent Timeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!config ? <p className="text-sm text-zinc-500">Connect to Loom to view recent events.</p> : null}
          {journey.isLoading ? <Skeleton className="h-48 w-full" /> : null}
          {(journey.data?.events ?? []).map((event) => {
            const Icon = icons[event.event_type as keyof typeof icons] ?? Activity;
            return (
              <div key={event.event_id} className="rounded-xl border border-zinc-200 p-4">
                <div className="flex items-center gap-2">
                  <Icon className="size-4 text-zinc-500" />
                  <p className="font-medium text-zinc-900">{event.title}</p>
                  <Badge variant="outline">{event.event_type}</Badge>
                </div>
                <p className="mt-2 text-sm text-zinc-600">{event.summary}</p>
                <p className="mt-2 text-xs text-zinc-400">{event.timestamp}</p>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
