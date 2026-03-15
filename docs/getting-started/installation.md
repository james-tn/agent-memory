# Installation

## Prerequisites

- Python 3.12+
- Azure OpenAI access
- `uv` recommended for dependency management

## Install the Project

Core + test tooling:

```bash
uv sync --extra dev
```

If you also want the docs toolchain:

```bash
uv sync --extra dev --extra docs
```

The repo pins:

- `agent-framework==1.0.0rc4`

Prerelease installs are enabled in project configuration.

## Build the Docs Locally

Once docs dependencies are installed:

```bash
mkdocs serve
```

Then open the local MkDocs URL shown in the terminal.
