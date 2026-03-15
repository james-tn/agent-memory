# Azure Deployment

The repo ships an `azd` + Bicep deployment path for:

- Azure OpenAI
- Azure Cosmos DB
- Azure AI Search
- Azure Database for PostgreSQL Flexible Server
- Container Apps demo hosting

## Quick Start

```bash
azd auth login
azd provision
```

If you also want the demo app deployed:

```bash
azd up
```

## PostgreSQL Regioning

PostgreSQL deployment is choice-based:

- default: same region as `AZURE_LOCATION`
- optional override: set `POSTGRES_LOCATION`

Example:

```bash
azd env set AZURE_LOCATION eastus
azd env set POSTGRES_LOCATION westus3
azd provision
```

Do not treat the override as required. Use it only when your subscription or offer cannot provision PostgreSQL in the main region.

## Post-Provision Setup

The `azd` flow runs setup scripts for:

1. Cosmos vector setup
2. Azure AI Search index setup
3. PostgreSQL schema and `vector` extension setup

See [infra/README.md on GitHub](https://github.com/james-tn/agent-memory/blob/main/infra/README.md) for the infra-focused guide.
