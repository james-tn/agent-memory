# Entra ID Authentication

The repo supports a config-driven auth setup for Azure-hosted scenarios.

## Basic Deployment Inputs

```bash
azd env set ENABLE_AUTH true
azd env set AUTH_CLIENT_ID <client-id>
azd env set AUTH_TENANT_ID <tenant-id>
azd env set AUTH_CLIENT_SECRET <client-secret>
```

## Flow

1. deploy with `azd up`
2. add the generated redirect URI to your Entra app registration
3. test sign-in against the deployed app

## When to Use This Guide

If you need the full step-by-step Entra setup details, see:

- [`docs/ENTRA_ID_AUTH_SETUP.md`](../ENTRA_ID_AUTH_SETUP.md)

That longer setup document stays in the repo as an operator reference, while this site page keeps the quick-start deployment flow short.
