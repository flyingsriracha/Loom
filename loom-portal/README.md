# Loom Portal

A novice-first portal for the Loom runtime.

This app sits on top of the existing Loom orchestrator and knowledge services and focuses on three workflows:

- onboarding and first-run setup
- explain-this-answer traceability
- development journey visibility

## What it uses

- Next.js App Router
- shadcn/ui
- TanStack Query

## Local development

Start the Loom backend first, then run the portal:

```bash
cd ../loom
# start your existing Loom runtime / docker services here

cd ../loom-portal
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Default backend target

The portal defaults to `http://localhost:8080` for the orchestrator, but the onboarding form lets you override it.

The portal forwards the same headers your IDE agent uses:

- `X-API-Key`
- `X-Engineer-Id`
- `X-Session-Id`
- `X-Objective-Id`
- `X-Project-Id`

## Key backend endpoints

- `POST /api/v1/trace/explain`
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/journey`
- `GET /api/v1/integrations/links`

## Optional deep-link environment variables

Set these in the backend environment to improve the portal launchpad:

- `LOOM_SERVICE_PUBLIC_URL`
- `ORCHESTRATOR_PUBLIC_URL`
- `FALKORDB_UI_URL`
- `HINDSIGHT_UI_URL`
- `LANGGRAPH_UI_URL`
- `LANGSMITH_UI_URL`
- `CMM_UI_URL`

## Validation

```bash
npm run lint
npm run build
```
