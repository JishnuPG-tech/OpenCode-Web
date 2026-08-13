# OmniRoute AI Gateway — Feature Specification & Integration Roadmap

This document outlines the detailed feature architecture of **OmniRoute** integrated within the `Jishnupg/Opencode-Cli` project, detailing the token compression pipeline, 290+ AI providers, CLI compatibility modes, and API endpoints.

---

## 1. Core Engine Subsystems

### A. Dual Token Compression Pipeline (RTK + Caveman)
OmniRoute features an inline token optimization engine that reduces prompt length by **15% to 95%** prior to forwarding requests to upstream LLM providers:

```
  [Client Prompt Payload]
             │
   [RTK (Recursive Token Killer)]  ──> Strips system prompt boilerplate, repeated context, & tool output noise
             │
   [Caveman Compression Engine]   ──> Compresses JSON schemas & system instructions into dense structural format
             │
  [Compressed API Request]       ──> Sent to Target Provider (e.g. Anthropic, OpenAI, DeepSeek, Kimi)
```

### B. Quota-Share Auto-Fallback Cascade
OmniRoute maintains real-time rate limit and quota tracking across 290+ providers and 500+ models.

```
                  [Client LLM Request]
                           │
                  [Provider Choice: Primary]
                           │
                 (Rate Limit 429 / 402?)
                /                       \
           (No: 200 OK)              (Yes: 429 Error)
                │                         │
     [Return Stream Response]    [Auto-Fallback Cascade]
                                          │
                                 [Select Next Key / Provider]
                                          │
                                 [Execute Request Seamlessly]
```

---

## 2. Supported AI Providers (290+ Integrations)

OmniRoute supports both direct API keys and OAuth single sign-on across top AI providers:

### Major Supported OAuth & API Providers:
- **Anthropic / Claude Code**: Claude 3.7 Sonnet, Claude 3.5 Haiku, Opus.
- **OpenAI**: GPT-4o, GPT-4o-mini, o1, o3-mini.
- **Google Antigravity & Gemini**: Gemini 2.5 Pro, Gemini 2.0 Flash, Flash-Lite.
- **Moonshot / Kimi Coding**: Kimi K1.5, Kimi CLI.
- **DeepSeek**: DeepSeek R1, DeepSeek V3.
- **Amazon Q / Bedrock**: Claude 3.5 Sonnet Bedrock endpoints.
- **GitHub Copilot / Copilot Enterprise**: Copilot Chat & Editor completions.
- **Cline / ClinePass**: Open-source coding agent integrations.
- **Cerebras & Groq**: Ultra-low latency Llama-3 70B inference.
- **Mistral, Cohere, Together, Replicate, Fireworks, OpenRouter**.

---

## 3. CLI Compatibility Layer (`CLI_COMPAT_*`)

To allow terminal coding assistants and IDE extensions to connect directly to OmniRoute without changing client code, OmniRoute emulates provider-specific CLI endpoints when environment flags are active:

| Compatibility Flag | Emulated Client Tool | Endpoint Behavior |
| :--- | :--- | :--- |
| `CLI_COMPAT_CLAUDE=1` | Anthropic Claude Code CLI | Translates `/v1/messages` requests |
| `CLI_COMPAT_ANTIGRAVITY=1` | Google Antigravity / Gemini CLI | Emulates Antigravity authentication & streaming |
| `CLI_COMPAT_CURSOR=1` | Cursor IDE | Translates Cursor autocomplete & chat headers |
| `CLI_COMPAT_GITHUB=1` | GitHub Copilot CLI / VSCode | Emulates Copilot token exchange |
| `CLI_COMPAT_KIMI_CODING=1` | Kimi Coding Assistant | Emulates Kimi OAuth handshake |
| `CLI_COMPAT_CODEX=1` | OpenAI Codex / Aider | Translates legacy code completion endpoints |

---

## 4. API Endpoints Reference

### OpenAI Compatible API (`/v1`)
- **Base URL**: `https://jishnupg-opencode-cli.hf.space/v1` or `/api/v1`
- **Endpoints**:
  - `POST /v1/chat/completions`: Streaming and non-streaming chat completions.
  - `GET /v1/models`: List all available and active models across connected providers.
  - `POST /v1/embeddings`: Vector embedding generation.

### Gemini Compatible API (`/v1beta`)
- **Base URL**: `https://jishnupg-opencode-cli.hf.space/v1beta` or `/api/v1beta`
- **Endpoints**:
  - `POST /v1beta/models/{model}:generateContent`: Gemini content generation.
  - `POST /v1beta/models/{model}:streamGenerateContent`: Gemini streaming content generation.

### Live Telemetry WebSocket (`/live-ws`)
- **Base URL**: `wss://jishnupg-opencode-cli.hf.space/live-ws`
- **Function**: Real-time token throughput metrics, active request visualization, and provider fallback telemetry.
