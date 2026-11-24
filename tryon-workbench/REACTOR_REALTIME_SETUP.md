# Reactor Xmax Relay (`reactor/xmax-x2-1` & `xmax/x2`) Setup Guide

This workbench supports **Reactor (`https://www.reactor.inc`)** as an optional third realtime video try-on engine alongside **Decart Lucy VTON 3.6** and **Xmax Official**. By default all three engines are **disabled (`enabled=False`)** so `$0` upstream cost is incurred until explicitly enabled by an administrator.

## 1. Supported Models & Official Pricing

Verified against `https://api.reactor.inc/pricing` and `@reactor-team/js-sdk@3.5.0`:

| Model ID | Version | Default | Credit Rate | USD Rate | Notes |
| --- | --- | --- | --- | --- | --- |
| `reactor/xmax-x2-1` | Xmax X2.1 | Yes | `17 credits/s` | `$0.0017/s` (`~$0.102/min`) | Swaps reference image mid-stream without restarting; **does not support `set_keep_backlog`**. |
| `xmax/x2` | Xmax X2.0 | Optional | `17 credits/s` | `$0.0017/s` (`~$0.102/min`) | Supports `set_keep_backlog: { keep_backlog: false }`; restarts stream when garment reference changes. |

- Exchange rate: `10,000 credits = $1.00 USD`.
- Conservative USD budget cap defaults to `11 cents/min` (ceiling over `$0.102/min`).

## 2. Security & Cost-Control Architecture

1. **Zero Secret Exposure**: The permanent Reactor `rk_...` API key is stored encrypted (`FERNET_SECRET_KEY`) in Admin PostgreSQL (`ai_api_providers` / `ai_feature_configs`) or env `REACTOR_REALTIME_API_KEY`, and never sent to browsers.
2. **Account Credit Floor (`min_account_credits`)**: Before minting a token (`POST /api/realtime-tryon/reactor/sessions/{id}/token`), the backend calls `GET /me` and `GET /accounts/{id}/credits` and rejects new sessions with `402` if account credits are below `min_account_credits` (default `1000`).
3. **One-Shot Scoped JWT (`POST /tokens`)**: Each session mints an ephemeral JWT constrained to `max_sessions: 1`, `models.match: [chosen_model]`, and `max_session_duration_seconds = min(120, requested_seconds + 30)`.
4. **Budget Reservation & Reconciliation**:
   - Browser daily cap (default `50` cents), site daily cap (`200` cents), site monthly cap (`1000` cents), max active (`1`), and starts/min (`3`) are enforced atomically in SQL before any token is minted.
   - Browser disconnect ALWAYS invokes `reactor.disconnect(false)` (`recoverable = false`) so Reactor tears down the remote session immediately.
   - Server stop (`POST /api/realtime-tryon/sessions/{id}/stop`) and admin stop (`POST /api/admin/realtime-tryon/sessions/{id}/stop`) issue `DELETE /sessions/{provider_session_id}`, settle `billed_seconds` / `provider_credits`, and release unused budget hold.

## 3. Environment Variables (Fallback if Admin DB Not Configured)

- `REACTOR_REALTIME_ENABLED=false`
- `REACTOR_REALTIME_ORIGIN=https://tryon.example.com`
- `REACTOR_REALTIME_BASE_URL=https://api.reactor.inc`
- `REACTOR_REALTIME_MODEL=reactor/xmax-x2-1`
- `REACTOR_REALTIME_ALLOWED_MODELS=reactor/xmax-x2-1,xmax/x2`
- `REACTOR_REALTIME_CREDITS_PER_SECOND=17`
- `REACTOR_REALTIME_CENTS_PER_MINUTE=11`
- `REACTOR_REALTIME_MIN_ACCOUNT_CREDITS=1000`

## 4. Admin Controls & Zero-Cost Official Data Sync

In **AI Model Settings -> Live Try-On -> Reactor Relay (X2.1 / X2.0)**:
- Click **Fetch official data (`获取官方数据`)** to call `POST /api/ai-config/realtime/reactor/fetch-official` (`GET /pricing`, plus optional `GET /me`, `/credits`, `/quotas` if an API key is provided or saved). This pre-fills defaults without mutating DB or creating paid sessions.
- Click **Check balance & connectivity (zero cost)** to verify `rk_...` key validity at `$0`.
- Monitor live balance, active concurrency, session ledger, upstream usage sync (`sync-usage`), credit/second manual reconciliation, and emergency kill switch under `/realtime-tryon?provider=reactor`.
