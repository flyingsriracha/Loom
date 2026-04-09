"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRightCircle, Link2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { fetchTraceExplain, PortalConfig, TraceabilityResponse } from "@/lib/loom-api";
import { useEffect, useState } from "react";

type Props = {
  config: PortalConfig | null;
  initialQuery: string;
  onQueryChange: (query: string) => void;
  autoRunToken: number;
};

export function TraceExplorer({ config, initialQuery, onQueryChange, autoRunToken }: Props) {
  const [includeChangeImpact, setIncludeChangeImpact] = useState(true);
  const queryClient = useQueryClient();
  const mutation = useMutation<TraceabilityResponse, Error, string>({
    mutationFn: (query) => {
      if (!config) {
        throw new Error("Connect to Loom before running a trace.");
      }
      return fetchTraceExplain(config, {
        query,
        includeChangeImpact,
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
        queryClient.invalidateQueries({ queryKey: ["journey"] }),
      ]);
    },
  });

  useEffect(() => {
    if (!config || autoRunToken === 0 || !initialQuery.trim()) {
      return;
    }
    mutation.mutate(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRunToken, config]);

  return (
    <Card className="border-zinc-200 bg-white/90 shadow-sm">
      <CardHeader>
        <CardTitle>Explain This Answer</CardTitle>
        <CardDescription>
          Ask Loom a real question and inspect the knowledge, memory, code, and workflow traces used to build the response.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Textarea value={initialQuery} onChange={(event) => onQueryChange(event.target.value)} className="min-h-28" />
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => mutation.mutate(initialQuery)} disabled={!config || !initialQuery.trim() || mutation.isPending}>
            <ArrowRightCircle className="size-4" />
            {mutation.isPending ? "Tracing..." : "Trace this answer"}
          </Button>
          <Button variant={includeChangeImpact ? "default" : "outline"} onClick={() => setIncludeChangeImpact((current) => !current)}>
            Include code impact
          </Button>
          {!config ? <span className="text-sm text-zinc-500">Connect to Loom first.</span> : null}
        </div>

        {mutation.error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <div className="flex items-center gap-2 font-medium"><AlertCircle className="size-4" /> Request failed</div>
            <p>{mutation.error.message}</p>
          </div>
        ) : null}

        {mutation.data ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge>{mutation.data.route}</Badge>
                <Badge variant="outline">{mutation.data.status}</Badge>
                {Object.entries(mutation.data.availability).map(([key, value]) => (
                  <Badge key={key} variant={value === "used" ? "default" : "secondary"}>
                    {key}: {value}
                  </Badge>
                ))}
              </div>
              <p className="text-sm leading-6 text-zinc-700">{mutation.data.answer_summary}</p>
            </div>

            <Tabs defaultValue="knowledge" className="w-full">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
                <TabsTrigger value="memory">Memory</TabsTrigger>
                <TabsTrigger value="code">Code</TabsTrigger>
                <TabsTrigger value="workflow">Workflow</TabsTrigger>
              </TabsList>
              <TabsContent value="knowledge" className="space-y-3">
                {mutation.data.knowledge_trace.length === 0 ? <p className="text-sm text-zinc-500">No knowledge evidence was returned for this answer.</p> : null}
                {mutation.data.knowledge_trace.map((item, index) => (
                  <div key={`${String(item.id ?? index)}`} className="rounded-lg border border-zinc-200 p-3 text-sm">
                    <p className="font-medium text-zinc-900">{String(item.summary ?? item.id ?? `Result ${index + 1}`)}</p>
                    <p className="text-zinc-500">Evidence items: {Array.isArray(item.evidence) ? item.evidence.length : 0}</p>
                  </div>
                ))}
              </TabsContent>
              <TabsContent value="memory" className="space-y-3">
                {mutation.data.memory_trace.length === 0 ? <p className="text-sm text-zinc-500">No AMS memory was pulled into this answer.</p> : null}
                {mutation.data.memory_trace.map((item, index) => (
                  <div key={`${String(item.kind)}-${index}`} className="rounded-lg border border-zinc-200 p-3 text-sm">
                    <p className="font-medium text-zinc-900">{String(item.kind)}</p>
                    <p className="text-zinc-600">{JSON.stringify(item)}</p>
                  </div>
                ))}
              </TabsContent>
              <TabsContent value="code" className="space-y-3">
                {mutation.data.code_trace.length === 0 ? <p className="text-sm text-zinc-500">No CMM or code-impact data contributed to this answer.</p> : null}
                {mutation.data.code_trace.map((item, index) => (
                  <div key={`${String(item.kind)}-${index}`} className="rounded-lg border border-zinc-200 p-3 text-sm">
                    <p className="font-medium text-zinc-900">{String(item.kind)}</p>
                    <p className="text-zinc-600">{JSON.stringify(item)}</p>
                  </div>
                ))}
              </TabsContent>
              <TabsContent value="workflow" className="space-y-3">
                {mutation.data.workflow_trace.length === 0 ? <p className="text-sm text-zinc-500">No workflow trace is available.</p> : null}
                {mutation.data.workflow_trace.map((item, index) => (
                  <div key={`${String(item.step)}-${index}`} className="rounded-lg border border-zinc-200 p-3 text-sm">
                    <p className="font-medium text-zinc-900">{String(item.step)}</p>
                    <p className="text-zinc-600">{JSON.stringify(item)}</p>
                  </div>
                ))}
              </TabsContent>
            </Tabs>

            <Separator />
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-zinc-900">
                <Link2 className="size-4" /> Native tool deep links
              </div>
              <div className="flex flex-wrap gap-2">
                {mutation.data.deep_links.map((link) => (
                  <a
                    key={link.name}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
