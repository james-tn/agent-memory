# Live Testing

The repo includes dedicated Azure-backed smoke tests.

## Non-Live Focused Suite

```bash
pytest -q tests -m 'not live'
```

## Live Azure Suite

```bash
pytest -m live -q tests/test_live_azure_backends.py
```

## What the Live Suite Covers

- direct `AgentMemory` with Azure AI Search
- direct `AgentMemory` with PostgreSQL
- FastAPI + `MemoryServiceClient` with Azure AI Search
- FastAPI + `MemoryServiceClient` with PostgreSQL

## Required Inputs

At minimum:

- Azure OpenAI endpoint and API key
- deployed backend settings from `.env`, process env, or `azd env`

The live test loader keeps Azure OpenAI endpoint/key pairs coherent from the local `.env` file while still consuming infra-managed backend settings from the `azd` environment.
