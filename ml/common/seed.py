"""Seed Python, NumPy, PyTorch, and CUDA random generators consistently."""

from __future__ import annotations

import random

import numpy as np
import torch


def set_all_seeds(seed: int) -> None:
    """Set global RNG seeds for Python, NumPy, CPU PyTorch, and available CUDA devices.

    NumPy's legacy global RNG accepts a 32-bit seed; PyTorch accepts an unsigned
    64-bit seed. Both are deterministically derived from the caller's non-negative
    integer seed.

    Raises:
        TypeError: If seed is not an integer or is a boolean.
        ValueError: If seed is negative.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed % (2**64))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed % (2**64))
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
