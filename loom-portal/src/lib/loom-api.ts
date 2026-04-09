export type PortalConfig = {
  baseUrl: string;
  apiKey: string;
  engineerId: string;
  sessionId: string;
  objectiveId: string;
  projectId: string;
};

export type TraceabilityResponse = {
  answer_summary: string;
  route: string;
  status: string;
  warnings: string[];
  citations: Array<Record<string, unknown>>;
  availability: Record<string, string>;
  knowledge_trace: Array<Record<string, unknown>>;
  memory_trace: Array<Record<string, unknown>>;
  code_trace: Array<Record<string, unknown>>;
  workflow_trace: Array<Record<string, unknown>>;
  deep_links: Array<{ name: string; label: string; url: string; kind: string }>;
};

export type DashboardOverview = {
  objective: {
    summary?: string;
    sections?: Record<string, string[]>;
    warnings?: string[];
    available?: boolean;
  };
  services: Record<string, unknown>;
  progress: {
    recent_event_count: number;
    knowledge_queries: number;
    memory_events: number;
    artifact_revisions: number;
    code_events: number;
    hitl_checkpoints: number;
  };
  recent_events: JourneyEvent[];
  change_impact?: Record<string, unknown>;
  deep_links: Array<{ name: string; label: string; url: string; kind: string }>;
};

export type JourneyEvent = {
  event_id: string;
  event_type: string;
  timestamp: string;
  title: string;
  summary: string;
  audit_id?: string;
  related_ids?: Record<string, string>;
};

export const DEFAULT_CONFIG: PortalConfig = {
  baseUrl: "http://localhost:8080",
  apiKey: "",
  engineerId: "eng-1",
  sessionId: "sess-1",
  objectiveId: "obj-1",
  projectId: "proj-1",
};

function buildHeaders(config: PortalConfig): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(config.apiKey ? { "X-API-Key": config.apiKey } : {}),
    ...(config.engineerId ? { "X-Engineer-Id": config.engineerId } : {}),
    ...(config.sessionId ? { "X-Session-Id": config.sessionId } : {}),
    ...(config.objectiveId ? { "X-Objective-Id": config.objectiveId } : {}),
    ...(config.projectId ? { "X-Project-Id": config.projectId } : {}),
  };
}

async function apiRequest<T>(
  config: PortalConfig,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${config.baseUrl}${path}`, {
    ...init,
    headers: {
      ...buildHeaders(config),
      ...(init?.headers ?? {}),
    },
  });
  const data = await response.json();
  if (!response.ok) {
    const message =
      data?.error?.message ||
      data?.detail ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }
  return data as T;
}

export function fetchTraceExplain(
  config: PortalConfig,
  payload: { query: string; includeChangeImpact: boolean },
) {
  return apiRequest<TraceabilityResponse>(config, "/api/v1/trace/explain", {
    method: "POST",
    body: JSON.stringify({
      query: payload.query,
      include_change_impact: payload.includeChangeImpact,
    }),
  });
}

export function fetchDashboardOverview(config: PortalConfig) {
  return apiRequest<DashboardOverview>(config, "/api/v1/dashboard/overview");
}

export function fetchDashboardJourney(config: PortalConfig) {
  return apiRequest<{ events: JourneyEvent[]; counts: Record<string, number> }>(
    config,
    "/api/v1/dashboard/journey?limit=25",
  );
}

export function fetchIntegrationLinks(
  config: PortalConfig,
  params: { query?: string; nodeId?: string; auditId?: string },
) {
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.nodeId) search.set("node_id", params.nodeId);
  if (params.auditId) search.set("audit_id", params.auditId);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<{ links: Array<{ name: string; label: string; url: string; kind: string }> }>(
    config,
    `/api/v1/integrations/links${suffix}`,
  );
}
