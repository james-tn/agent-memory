# Infrastructure

This folder contains the `azd` + Bicep deployment for Agent Memory.

## What Gets Deployed

- Azure OpenAI
- Azure Cosmos DB
- Azure AI Search
- Azure Database for PostgreSQL Flexible Server
- Azure Container Apps demo resources
- Optional secure networking for Cosmos connectivity

## Deployment Model

PostgreSQL regioning is choice-based:

- Default: PostgreSQL deploys in the same region as `AZURE_LOCATION`
- Optional override: set `POSTGRES_LOCATION` to deploy PostgreSQL in a different supported region

The code does not hardcode a separate PostgreSQL fallback region. If your subscription or offer cannot provision PostgreSQL in the main region, choose an alternate supported region explicitly.

## Prerequisites

- Azure Developer CLI (`azd`)
- Azure CLI (`az`)
- PowerShell 7+ or POSIX shell
- Python 3.12 for local test and setup scripts
- Logged-in Azure credentials for the target tenant/subscription

Login example:

```bash
azd auth login --tenant-id <tenant-id>
az login --tenant <tenant-id>
```

## Quick Start

```bash
azd provision
```

This will:

1. run preprovision hooks
2. provision Azure resources
3. run postprovision setup for Cosmos, Azure AI Search, and PostgreSQL

If you also want the demo container deployed:

```bash
azd up
```

## Same-Region vs Split-Region PostgreSQL

### Default same-region deployment

```bash
azd env set AZURE_LOCATION eastus
azd provision
```

With no `POSTGRES_LOCATION` set, PostgreSQL uses `AZURE_LOCATION`.

### Optional split-region PostgreSQL deployment

```bash
azd env set AZURE_LOCATION eastus
azd env set POSTGRES_LOCATION westus3
azd provision
```

Use this only when you need it, such as offer-restricted subscriptions where Flexible Server cannot be created in the main deployment region.

## Troubleshooting PostgreSQL Region Restrictions

Exact symptom:

- `azd provision` fails while creating `Microsoft.DBforPostgreSQL/flexibleServers`
- the error indicates the server cannot be provisioned in the selected region for the current subscription or offer

Remediation:

```bash
azd env set POSTGRES_LOCATION <supported-region>
azd provision
```

`POSTGRES_SERVER_NAME_SUFFIX` is also available as an escape hatch if a failed deployment leaves behind a soft-deleted or collision-prone server name:

```bash
azd env set POSTGRES_SERVER_NAME_SUFFIX retry1
```

That suffix is for recovery only, not a normal required setting.

## Environment Inputs

Set these with `azd env set <NAME> <VALUE>`.

### Core

| Variable | Description |
| --- | --- |
| `AZURE_ENV_NAME` | Environment name |
| `AZURE_LOCATION` | Main Azure deployment region |
| `SECURE_COSMOS` | Whether to use the secure Cosmos networking path |

### PostgreSQL

| Variable | Description |
| --- | --- |
| `POSTGRES_ADMIN_LOGIN` | PostgreSQL admin login |
| `POSTGRES_ADMIN_PASSWORD` | PostgreSQL admin password |
| `POSTGRES_LOCATION` | Optional PostgreSQL region override |
| `POSTGRES_SERVER_NAME_SUFFIX` | Optional suffix for collision recovery |
| `LOCAL_DEVELOPER_PUBLIC_IP` | Auto-populated for local firewall access |

### Optional auth/demo settings

| Variable | Description |
| --- | --- |
| `ENABLE_AUTH` | Enable auth gate / demo auth integration |
| `AUTH_CLIENT_ID` | Auth app client ID |
| `AUTH_TENANT_ID` | Auth tenant override |
| `AUTH_CLIENT_SECRET` | Auth client secret |

## `azd` Outputs You Can Reuse Locally

These values are written into the local `azd` environment and consumed by the runtime and live tests:

| Output | Purpose |
| --- | --- |
| `AZURE_AI_SEARCH_ENDPOINT` | Azure AI Search endpoint |
| `AZURE_AI_SEARCH_API_KEY` | Azure AI Search admin/query key |
| `AZURE_AI_SEARCH_INDEX_PREFIX` | Stable index prefix |
| `POSTGRES_HOST` | PostgreSQL server hostname |
| `POSTGRES_DATABASE` | PostgreSQL database name |
| `POSTGRES_ADMIN_LOGIN` | PostgreSQL admin login |
| `POSTGRES_CONNECTION_STRING` | SSL-enabled connection string |

## Hooks and Setup Scripts

### Preprovision

`infra/scripts/preprovision.ps1` and `infra/scripts/preprovision.sh`:

- resolve the local developer object ID for Cosmos RBAC
- ensure PostgreSQL admin credentials exist
- detect the developer public IP for local PostgreSQL firewall access
- preserve `POSTGRES_LOCATION` only if the operator explicitly set it

### Postprovision

`infra/scripts/postprovision.ps1` and `infra/scripts/postprovision.sh` run, in order:

1. Cosmos vector setup
2. Azure AI Search index setup
3. PostgreSQL schema and `vector` extension setup

Supporting scripts:

- `infra/scripts/setup-cosmos-vectors.ps1`
- `infra/scripts/setup-cosmos-vectors.sh`
- `infra/scripts/setup-search-indexes.ps1`
- `infra/scripts/setup-search-indexes.sh`
- `infra/scripts/setup-postgres-schema.ps1`
- `infra/scripts/setup-postgres-schema.sh`

Each script is intended to be idempotent and safe to re-run after provisioning updates.

## Local Runtime Flow

You can export the `azd` environment into local development after provisioning:

```bash
azd env get-values > .env.azd
```

In this repo, local `.env` remains the primary source for Azure OpenAI endpoint/key pairs, while the `azd` environment is the source of truth for infra-managed backend settings such as Azure AI Search and PostgreSQL outputs.

## Live Validation

After provisioning, the live smoke suite can be run with:

```bash
pytest -m live -q tests/test_live_azure_backends.py
```

The current live suite validates:

- direct `AgentMemory` with Azure AI Search
- direct `AgentMemory` with PostgreSQL
- FastAPI + `MemoryServiceClient` with Azure AI Search
- FastAPI + `MemoryServiceClient` with PostgreSQL

## Relevant Files

```text
infra/
  main.bicep
  main.bicepparam
  modules/
    azure-search.bicep
    postgresql.bicep
  scripts/
    preprovision.*
    postprovision.*
    setup-cosmos-vectors.*
    setup-search-indexes.*
    setup-postgres-schema.*
```
