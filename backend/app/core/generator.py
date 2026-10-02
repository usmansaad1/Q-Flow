"""
Random venue generator for scaling experiments.

Each instance has `num_groups` zones, each holding one crowd group, and every zone
has direct routes to exactly two different exits. With paths_per_group = 2 that
gives exactly 2 * num_groups qubits, so problem size is controlled precisely.

Exit capacities are set below the load the nearest exit plan would put on them,
so instances are congested by design (otherwise the optimum is trivial and every
method looks perfect). Instances are fully determined by the seed.
"""
from __future__ import annotations

import random

from app.core.venue import Venue


def generate_venue(num_groups: int, seed: int, num_exits: int | None = None,
                   tightness: float = 0.85) -> Venue:
    """
    tightness: exit capacity as a fraction of a perfectly even share of the crowd.
               Below 1 means even the best plan is close to full, so routing matters.
    """
    if num_groups < 1:
        raise ValueError("num_groups must be at least 1.")
    rng = random.Random(seed)
    num_exits = num_exits or max(2, min(4, (num_groups + 1) // 2 + 1))

    v = Venue(f"Synthetic {2 * num_groups}q #{seed}",
              description=f"Generated: {num_groups} groups, {num_exits} exits, seed {seed}.")
    exits = [f"Exit {chr(65 + e)}" for e in range(num_exits)]
    sizes = [rng.randint(80, 200) for _ in range(num_groups)]
    total = sum(sizes)
    # Generous enough that a balanced plan exists, tight enough that naive plans overload.
    even_share = total / num_exits
    for e, name in enumerate(exits):
        cap = int(round(even_share * (1 / tightness) * rng.uniform(0.9, 1.1), -1))
        v.add_location(name, "exit", capacity=cap, x=760, y=60 + e * (380 / max(num_exits - 1, 1)))

    # A popular exit most zones are close to creates the congestion to resolve.
    popular = rng.randrange(num_exits)
    for g in range(num_groups):
        zone = f"Zone {g + 1}"
        v.add_location(zone, "zone", x=120 + (g % 4) * 140, y=60 + (g // 4) * 140)
        near = popular if rng.random() < 0.7 else rng.randrange(num_exits)
        far = rng.choice([e for e in range(num_exits) if e != near])
        near_len = rng.randint(10, 25)
        v.add_route(zone, exits[near], capacity=rng.randint(150, 300), length=near_len)
        v.add_route(zone, exits[far], capacity=rng.randint(150, 300), length=near_len + rng.randint(5, 20))
        v.add_group(f"Group {g + 1}", zone, sizes[g])
    return v
