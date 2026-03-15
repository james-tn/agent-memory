# HTTP API

The FastAPI service wraps `AgentMemory` behind a stable HTTP interface.

## Key Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | `GET` | service health |
| `/sessions/start` | `POST` | start or restore a session |
| `/sessions/context` | `GET` | get current prompt context |
| `/sessions/turn` | `POST` | store a user/assistant turn |
| `/sessions/end` | `POST` | end a session and trigger reflection |
| `/search` | `POST` | search persisted memory |
| `/users/{user_id}/insights` | `GET` | list insights |
| `/users/{user_id}/sessions` | `GET` | list recent sessions |

## Python Client

Use `MemoryServiceClient` when you do not want to work with raw HTTP payloads directly.

See [Usage > Server Mode](../usage/server-mode.md) for an example.
