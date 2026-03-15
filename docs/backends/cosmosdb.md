# Cosmos DB Backend

Cosmos DB is the Azure-native document backend for the project.

## Configuration

Use either:

```bash
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
```

or:

```bash
AZURE_COSMOS_CONNECTION_STRING=...
```

## Strengths

- Azure-native deployment story
- hybrid and vector search support
- works well with Azure identity and Cosmos RBAC

## When to Prefer It

- your memory model fits document storage naturally
- you want one Azure service for persistence and retrieval
- you already operate Cosmos DB
