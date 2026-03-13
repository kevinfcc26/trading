# Phase 12 — Professional Multi-Timeframe Trading Engine

**Status: DONE**
**Date: 2026-03-10**

---

## Objetivo

Convertir el sistema de un ponderado simple (TA×0.25 + ML×0.35 + AI×0.40) a un motor de trading profesional que actúa como un trader institucional real:

- Análisis top-down multi-timeframe (D1 → H4 → H1)
- Detección de soporte/resistencia por swing highs/lows
- Prompt estructurado como trader profesional (confluencias, R:R, estructura de mercado)
- Agregador por confluencia (no por promedio ponderado)
- Persistencia real de señales en la DB

---

## Arquitectura implementada

### Pipeline por vela

```
TradingWorker._iteration(symbol, H1)
  │
  ├─ MultiTimeframeAnalyzer.analyze(symbol, H1)
  │   ├─ broker.get_candles(D1, 200) → EMA20/50 → TimeframeAnalysis
  │   ├─ broker.get_candles(H4, 200) → EMA20/50 → TimeframeAnalysis
  │   └─ broker.get_candles(H1, 200) → EMA20/50 → TimeframeAnalysis
  │   → MultiTimeframeContext(dominant_bias, trend_alignment)
  │
  ├─ SRDetector.detect(h4_candles, current_price)
  │   ├─ Swing highs/lows (ventana de 5 barras)
  │   ├─ Clustering de niveles (tolerancia 0.1%)
  │   ├─ Score por toques + recencia
  │   └─ Niveles psicológicos (00/50 pips)
  │   → SRContext(nearest_support, nearest_resistance, rr_viable)
  │
  ├─ TAStrategy.generate(h1_candles, mtf_context=ctx)
  │   └─ Penaliza ×0.5 señales contra el sesgo D1
  │
  ├─ MLStrategy.generate(h1_candles)
  │
  ├─ AI.generate(candles, ta, ml, mtf_context, sr_context)
  │   └─ ProfessionalPromptBuilder → 7 secciones estructuradas
  │      (MTF, S/R, velas, TA, ML, sesión, framework de decisión)
  │
  ├─ SignalAggregator.aggregate_professional(ta, ml, ai, mtf, sr)
  │   Rules (prioridad):
  │   1. R:R no viable → HOLD
  │   2. AI dice HOLD con conf≥0.60 → HOLD
  │   3. Confluencia < 3/5 → HOLD
  │   4. Confianza final = ai_conf × (0.6 + 0.4 × alignment)
  │
  ├─ SQLSignalRepository.save(aggregated) → DB
  │
  └─ RiskPipeline.evaluate() → Order si aprobado
```

---

## Archivos nuevos

| Archivo | Descripción |
|---|---|
| `src/strategy/domain/value_objects.py` | `TimeframeAnalysis`, `MultiTimeframeContext`, `SupportResistanceLevel`, `SRContext` |
| `src/strategy/domain/sr_detector.py` | `SRDetector` — swing detection + clustering (pure domain, sin pandas) |
| `src/strategy/infrastructure/multi_timeframe_analyzer.py` | `MultiTimeframeAnalyzer` — fetcha D1/H4/H1 vía broker |
| `src/strategy/infrastructure/professional_prompt_builder.py` | `ProfessionalPromptBuilder` — brief de 7 secciones para el LLM |
| `alembic/versions/0003_signal_mtf_sr_context.py` | Agrega columnas `mtf_context` y `sr_context` JSONB a `signals` |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `src/strategy/domain/services.py` | `+aggregate_professional()` (el `aggregate()` original no cambia) |
| `src/strategy/infrastructure/ta_strategy.py` | Filtro de sesgo MTF — penaliza señales contra D1 |
| `src/strategy/infrastructure/claude_strategy.py` | Usa `ProfessionalPromptBuilder`, parsea campos extendidos |
| `src/strategy/infrastructure/ollama_strategy.py` | Ídem Claude — contexto MTF+SR, prompt profesional |
| `src/strategy/infrastructure/signal_repository.py` | Persiste `mtf_context` y `sr_context` en DB |
| `src/infrastructure/persistence/models.py` | +columnas `mtf_context`, `sr_context` JSONB en `SignalModel` |
| `src/entrypoints/workers/trading_worker.py` | Pipeline completo MTF+SR+persistencia |
| `src/entrypoints/cli/container.py` | Wires `MultiTimeframeAnalyzer` y `SRDetector` |
| `config/settings.py` | +`mtf_enabled`, `sr_*`, `use_professional_aggregator`, `signal_persistence_enabled` |

---

## Settings relevantes (`.env`)

```env
MTF_ENABLED=true
USE_PROFESSIONAL_AGGREGATOR=true
SIGNAL_PERSISTENCE_ENABLED=true
SR_MIN_RR_RATIO=2.0
SR_SWING_WINDOW=5
SR_MAX_LEVELS=8
CONFLUENCE_MIN_SCORE=3.0
```

---

## Lógica del Prompt Profesional (7 secciones)

1. **Multi-Timeframe Structure** — D1/H4/H1 tendencia, fuerza, alineación %
2. **Key S/R Levels** — Resistencias y soportes con fuerza, toques, distancia en pips
3. **Recent Candles** — Últimas 5 velas OHLCV
4. **Technical Analysis Signal** — RSI, EMAs, MACD, Bollinger
5. **ML Signal** — Dirección XGBoost + probabilidades
6. **Session & Timing** — Sesión actual (Londres/NY overlap = mejor)
7. **Decision Framework** — 5 checks obligatorios: bias, nivel, R:R, confluencia, convicción

---

## Agregador Profesional — Reglas

| Regla | Condición | Resultado |
|---|---|---|
| 1 | `sr_context.rr_viable == False` | HOLD forzado |
| 2 | AI dice HOLD con conf ≥ 0.60 | HOLD |
| 3 | Confluencia < 3.0/5.0 | HOLD |
| 4 | Confluencia ≥ 3.0 | Dirección AI, conf = ai_conf × (0.6 + 0.4 × alignment) |

**Puntos de confluencia:**
- D1 alineado con AI → +1.0
- H4 alineado con AI → +1.0
- TA alineado con AI → +0.5
- ML alineado con AI → +0.5
- Precio en nivel S/R → +1.0

---

## Tests

- 96 tests unitarios pasan (sin regresiones)
- 3 fallos pre-existentes en `tests/unit/domain/` (legacy, no tocar)
