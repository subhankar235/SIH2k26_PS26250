"""A compact temporal graph network with recurrent node memory and event scoring."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from ml.temporal_graph.dataset import TemporalData


@dataclass(frozen=True)
class TGNOutput:
    """Event fault logits and temporal link logits produced by the TGN."""

    node_logits: Tensor
    link_logits: Tensor


class TGNModel(nn.Module):
    """Temporal memory network with recurrent message, embedding and classifiers."""

    def __init__(
        self,
        num_sources: int,
        num_entities: int,
        num_attributes: int,
        *,
        hidden_dim: int = 64,
        value_buckets: int = 65_536,
        dropout: float = 0.1,
    ) -> None:
        """Create learned feature embeddings and a GRU-updated entity memory."""
        super().__init__()
        if min(num_sources, num_entities, num_attributes, hidden_dim, value_buckets) < 1:
            raise ValueError("embedding cardinalities and hidden_dim must be positive")
        if not 0 <= dropout < 1:
            raise ValueError("dropout must be in [0, 1)")
        self.hidden_dim = hidden_dim
        self.num_entities = num_entities
        self.value_buckets = value_buckets
        embedding_dim = max(8, hidden_dim // 4)
        self.source_embedding = nn.Embedding(num_sources, embedding_dim)
        self.attribute_embedding = nn.Embedding(num_attributes, embedding_dim)
        self.value_embedding = nn.Embedding(value_buckets, embedding_dim)
        self.time_projection = nn.Sequential(nn.Linear(1, embedding_dim), nn.Tanh())
        self.message = nn.Sequential(
            nn.Linear(embedding_dim * 4 + hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )
        self.memory_update = nn.GRUCell(hidden_dim, hidden_dim)
        self.embedding = nn.Sequential(
            nn.Linear(hidden_dim * 2 + embedding_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.node_classifier = nn.Linear(hidden_dim, 2)
        self.link_classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2 + embedding_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self._memory_state: dict[int, Tensor] = {}

    def reset_memory(self) -> None:
        """Clear recurrent node state at the start of an independent sequence."""
        self._memory_state = {}

    def forward(
        self,
        data: TemporalData,
        *,
        reset_memory: bool = False,
        detach_memory: bool = True,
    ) -> TGNOutput:
        """Process chronological events and update entity memory at each event.

        ``detach_memory`` provides truncated back-propagation between event chunks;
        memory still carries forward numerically across calls unless reset explicitly.
        """
        count = len(data)
        if count == 0:
            raise ValueError("TGN requires at least one temporal event")
        if data.num_entities > self.num_entities:
            raise ValueError("data entity vocabulary exceeds this model's memory table")
        if reset_memory:
            self.reset_memory()
        device = self.source_embedding.weight.device
        source_ids = data.source_ids.to(device)
        entity_ids = data.entity_ids.to(device)
        attribute_ids = data.attribute_ids.to(device)
        value_ids = torch.remainder(data.value_hashes.to(device), self.value_buckets)
        time_deltas = data.time_deltas.to(device).unsqueeze(-1)
        zeros = self.source_embedding.weight.new_zeros(self.hidden_dim)
        node_logits: list[Tensor] = []
        link_logits: list[Tensor] = []
        next_memory: dict[int, Tensor] = dict(self._memory_state)

        for index in range(count):
            source = self.source_embedding(source_ids[index])
            attribute = self.attribute_embedding(attribute_ids[index])
            value = self.value_embedding(value_ids[index])
            time = self.time_projection(time_deltas[index])
            entity_id = int(entity_ids[index].item())
            prior_memory = next_memory.get(entity_id, zeros)
            message = self.message(
                torch.cat((source, attribute, value, time, prior_memory), dim=-1)
            )
            updated_memory = self.memory_update(message.unsqueeze(0), prior_memory.unsqueeze(0))[0]
            next_memory[entity_id] = updated_memory
            event_embedding = self.embedding(
                torch.cat((prior_memory, updated_memory, attribute, time), dim=-1)
            )
            node_logits.append(self.node_classifier(event_embedding))
            link_logits.append(
                self.link_classifier(
                    torch.cat((source, prior_memory, updated_memory, attribute, time), dim=-1)
                ).squeeze(-1)
            )

        self._memory_state = (
            {node: state.detach() for node, state in next_memory.items()}
            if detach_memory
            else next_memory
        )
        return TGNOutput(torch.stack(node_logits), torch.stack(link_logits))


def model_for_data(data: TemporalData, **kwargs: object) -> TGNModel:
    """Construct a TGN whose embedding tables match one temporal split."""
    return TGNModel(
        data.num_sources,
        data.num_entities,
        data.num_attributes,
        **kwargs,  # type: ignore[arg-type]
    )
