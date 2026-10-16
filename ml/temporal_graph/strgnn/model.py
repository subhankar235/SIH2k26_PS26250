"""Structural snapshot graph neural network for event anomaly classification."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from ml.temporal_graph.dataset import TemporalData


@dataclass(frozen=True)
class StrGNNOutput:
    """Fault logits for temporal graph edges and their corresponding record indexes."""

    event_indices: Tensor
    logits: Tensor


class StrGNNModel(nn.Module):
    """Snapshot graph network with bidirectional mean aggregation and edge classification."""

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
        """Create source/entity node embeddings and a message-passing edge classifier."""
        super().__init__()
        if min(num_sources, num_entities, num_attributes, hidden_dim, value_buckets) < 1:
            raise ValueError("embedding cardinalities and hidden_dim must be positive")
        if not 0 <= dropout < 1:
            raise ValueError("dropout must be in [0, 1)")
        self.num_sources = num_sources
        self.num_entities = num_entities
        self.hidden_dim = hidden_dim
        self.value_buckets = value_buckets
        embedding_dim = max(8, hidden_dim // 4)
        self.source_embedding = nn.Embedding(num_sources, hidden_dim)
        self.entity_embedding = nn.Embedding(num_entities, hidden_dim)
        self.attribute_embedding = nn.Embedding(num_attributes, embedding_dim)
        self.value_embedding = nn.Embedding(value_buckets, embedding_dim)
        self.time_projection = nn.Sequential(nn.Linear(1, embedding_dim), nn.Tanh())
        self.edge_message = nn.Sequential(
            nn.Linear(hidden_dim * 2 + embedding_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )
        self.source_convolution = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim), nn.ReLU(), nn.LayerNorm(hidden_dim)
        )
        self.entity_convolution = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim), nn.ReLU(), nn.LayerNorm(hidden_dim)
        )
        self.edge_classifier = nn.Sequential(
            nn.Linear(hidden_dim * 3 + embedding_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 2),
        )

    def forward(self, data: TemporalData) -> Tensor:
        """Classify every event after message passing over its UTC-day snapshot."""
        if len(data) == 0:
            raise ValueError("StrGNN requires at least one temporal event")
        if data.num_sources > self.num_sources or data.num_entities > self.num_entities:
            raise ValueError("data vocabulary exceeds this model's embedding tables")
        device = self.source_embedding.weight.device
        source_ids = data.source_ids.to(device)
        entity_ids = data.entity_ids.to(device)
        attribute_ids = data.attribute_ids.to(device)
        value_ids = torch.remainder(data.value_hashes.to(device), self.value_buckets)
        time_deltas = data.time_deltas.to(device).unsqueeze(-1)
        timestamps = data.timestamps.to(device)
        snapshot_ids = torch.div(timestamps, 86_400, rounding_mode="floor")
        logits = self.source_embedding.weight.new_zeros((len(data), 2))

        _, snapshot_counts = torch.unique_consecutive(snapshot_ids, return_counts=True)
        offset = 0
        for snapshot_count in snapshot_counts.tolist():
            indexes = torch.arange(offset, offset + snapshot_count, device=device)
            offset += snapshot_count
            source_idx = source_ids[indexes]
            entity_idx = entity_ids[indexes]
            source = self.source_embedding(source_idx)
            entity = self.entity_embedding(entity_idx)
            attribute = self.attribute_embedding(attribute_ids[indexes])
            value = self.value_embedding(value_ids[indexes])
            time = self.time_projection(time_deltas[indexes])
            messages = self.edge_message(
                torch.cat((source, entity, attribute, value, time), dim=-1)
            )

            source_sum = messages.new_zeros((self.num_sources, self.hidden_dim)).index_add(
                0, source_idx, messages
            )
            entity_sum = messages.new_zeros((self.num_entities, self.hidden_dim)).index_add(
                0, entity_idx, messages
            )
            source_degree = messages.new_zeros(self.num_sources).index_add(
                0, source_idx, messages.new_ones(len(indexes))
            ).clamp_min_(1).unsqueeze(-1)
            entity_degree = messages.new_zeros(self.num_entities).index_add(
                0, entity_idx, messages.new_ones(len(indexes))
            ).clamp_min_(1).unsqueeze(-1)
            source_updated = self.source_convolution(
                torch.cat(
                    (self.source_embedding.weight, source_sum / source_degree), dim=-1
                )
            )[source_idx]
            entity_updated = self.entity_convolution(
                torch.cat(
                    (self.entity_embedding.weight, entity_sum / entity_degree), dim=-1
                )
            )[entity_idx]
            logits[indexes] = self.edge_classifier(
                torch.cat(
                    (source_updated, entity_updated, messages, attribute, value, time), dim=-1
                )
            )
        return logits
