"""Порты ядра агента (hexagonal ports).

Ядро объявляет здесь абстракции в доменном словаре; driving-адаптеры (ACP,
потенциально A2A) и driven-адаптеры реализуют их снаружи. Цель `import-linter` —
ноль рёбер `agent.core -> protocol` (см. ADR-005, ADR-003).

Каркас Фазы 0: порты наполняются по мере фаз change `acp-independent-agent-core`:
- Фаза 1: `SessionView`
- Фаза 2: `ContentCodec`
- Фаза 3: `ToolGateway`, `UpdateSink`
- Фаза 4: `AgentRunner`, `ChildSessionFactory`, `LLMPort`
"""

from __future__ import annotations
