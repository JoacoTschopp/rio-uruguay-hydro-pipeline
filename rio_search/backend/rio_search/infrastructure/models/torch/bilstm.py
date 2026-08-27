"""`BiLSTMAdapter` (Fase 3, docs/rio_search_plan.md §3.3): LSTM bidireccional sobre la ventana
`(N, lookback, n_features)` -> cabeza densa de `n_outputs` (uno por horizonte en
`multi_output`, uno solo en `per_horizon`, §3.3: "un adaptador que soporte `n_outputs=1` ya
soporta `per_horizon` gratis"). `BaseTorchAdapter` resuelve todo lo comun (tensores, bucle de
entrenamiento, checkpoint, serializacion); esta clase solo declara la arquitectura.
"""

from __future__ import annotations

import torch

from rio_search.domain.models.model_registry import register_model
from rio_search.infrastructure.models.torch.base_torch_adapter import BaseTorchAdapter


class _BiLSTMNetwork(torch.nn.Module):
    def __init__(
        self, n_features: int, hidden_size: int, num_layers: int, dropout: float, n_outputs: int
    ) -> None:
        super().__init__()
        self.lstm = torch.nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            # torch.nn.LSTM tira UserWarning si dropout>0 con num_layers==1 (no tiene efecto:
            # el dropout de LSTM se aplica *entre* capas apiladas).
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = torch.nn.Linear(hidden_size * 2, n_outputs)  # *2: bidireccional

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        last_step = out[:, -1, :]  # ultimo paso de la ventana (§3.3: "sobre la ventana pasada")
        return self.head(last_step)


@register_model("bilstm")
class BiLSTMAdapter(BaseTorchAdapter):
    """Implementa `application.ports.model_adapter.ModelAdapterPort` via `BaseTorchAdapter`.
    `model.params` del YAML (§4.1): `hidden_size`, `num_layers`, `dropout`."""

    name = "bilstm"

    def _build_network(self) -> torch.nn.Module:
        params = self._spec.params if self._spec is not None else {}
        return _BiLSTMNetwork(
            n_features=self._n_features,
            hidden_size=int(params.get("hidden_size", 64)),
            num_layers=int(params.get("num_layers", 2)),
            dropout=float(params.get("dropout", 0.0)),
            n_outputs=self._n_outputs,
        )
