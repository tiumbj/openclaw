# OpenClaw Decision JSON Schema (v1)

This document defines the JSON **decision** object returned by the OpenClaw/LLM layer back to the Python trading engine.

The goal is to standardize how the LLM communicates actionable trading intent (open/close/scale/hold) along with risk, sizing, and human-readable reasoning.

## Decision Object (JSONC)

```jsonc
{
  "version": 1,

  "symbol": "XAUUSD",

  "timeframes": {
    "signal_tf": "H1",                   // timeframe where the base signal comes from
    "execution_tf": "M15",               // timeframe used for actual order execution
    "context_tfs": ["M15", "H1", "H4"]   // timeframes used for broader context / filters
  },

  "timestamp": "2026-03-08T09:04:00Z",

  // High-level trading intent
  "action": "OPEN",          // OPEN | CLOSE | CLOSE_PARTIAL | HOLD | SCALE_IN | SCALE_OUT | REVERSE
  "direction": "LONG",       // LONG | SHORT | FLAT

  // Position sizing – focus on % equity risk
  "sizing": {
    "mode": "RISK_PCT",      // RISK_PCT | FIXED_LOT (RISK_PCT is the primary mode)
    "risk_pct": 1.0,         // % of account equity risked on this decision
    "fixed_lot": null,       // used only when mode = FIXED_LOT

    // caps for scaling in/out or reversing
    "max_add_lot": 0.10,     // maximum additional lots allowed to be added
    "max_reduce_lot": 0.10   // maximum lots allowed to be reduced in partial close / scale-out
  },

  // Risk limits related to price movement
  "risk": {
    "stop_loss_pips": 300,
    "take_profit_pips": 600,
    "min_rr": 1.5,
    "hard_block": false      // true = do not allow trade/opening/adding in this context
  },

  // Overall decision confidence from the LLM (0.0 - 1.0)
  "confidence": 0.82,

  // Explanation & debugging info (Thai + English mix is allowed for human readability)
  "meta": {
    "reason": "MTF alignment: H1 uptrend, M15 pullback complete, volatility moderate, daily DD < 1%",
    "notes": [
      "Reduce risk if upcoming high-impact news in < 4h",
      "Avoid new positions if XAUUSD total exposure > 5 lots"
    ],
    "debug": {
      "base_signal": "BUY",
      "filters_passed": ["mtf_trend_ok", "volatility_ok"],
      "filters_blocked": []
    }
  }
}
```

## Field Notes (Validation / Expectations)

- `version`
  - Integer schema version. Current version is `1`.
- `symbol`
  - MT5 symbol string (e.g., `XAUUSD`).
- `timeframes`
  - `signal_tf`: where the base signal originated.
  - `execution_tf`: where execution logic is applied (may differ from signal_tf).
  - `context_tfs`: list of timeframes used to justify the decision.
- `timestamp`
  - ISO-8601 timestamp in UTC (prefer `...Z`).
- `action` + `direction`
  - `action` describes what to do (open, close, scale, etc.).
  - `direction` describes directional intent (LONG/SHORT/FLAT).
- `sizing`
  - Primary mode is `RISK_PCT` to express intent in percent-of-equity risk.
  - `fixed_lot` is used only when `mode="FIXED_LOT"`.
  - `max_add_lot` and `max_reduce_lot` cap scaling actions to avoid runaway size changes.
- `risk`
  - Pips-based risk intent (SL/TP) and minimum RR requirement.
  - `hard_block=true` is a hard veto: no opening/adding should be allowed in this context.
- `confidence`
  - Float in `[0.0, 1.0]`. This is LLM self-estimated confidence.
- `meta`
  - `reason`: short explanation (human-readable).
  - `notes`: optional guidance list.
  - `debug`: free-form object for traceability (base_signal, filters, etc.).

## Action Semantics (How the trading engine should interpret actions)

This section describes **typical MT5 semantics** the trading engine can map to. The exact mapping is intentionally left to the engine implementation and risk layer.

- `OPEN`
  - Open a new position in the given `direction` (LONG/SHORT), if risk rules allow.
  - If `direction=FLAT`, treat as no-op or convert to `HOLD`.
- `CLOSE`
  - Close existing position(s) for this `symbol` (usually all exposure) regardless of direction.
- `CLOSE_PARTIAL`
  - Reduce exposure for this `symbol` by a partial amount (bounded by `sizing.max_reduce_lot`).
- `HOLD`
  - Do nothing. No open/close/scale action should be taken.
- `SCALE_IN`
  - Add to an existing position in the same `direction` (bounded by `sizing.max_add_lot`).
  - Should be blocked if `risk.hard_block=true`.
- `SCALE_OUT`
  - Reduce an existing position (bounded by `sizing.max_reduce_lot`).
  - Unlike CLOSE_PARTIAL, SCALE_OUT may be used more frequently as a management action.
- `REVERSE`
  - Close existing position(s) for `symbol` and open in the opposite direction.
  - Typically only allowed if risk layer approves and within sizing/risk constraints.

