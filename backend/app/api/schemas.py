from typing import Literal, Optional

from pydantic import BaseModel, Field


class LocationIn(BaseModel):
    id: str
    location_type: str
    capacity: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None


class RouteIn(BaseModel):
    from_node: str
    to_node: str
    capacity: int
    length: float
    travel_time: Optional[float] = None
    bidirectional: bool = True
    id: Optional[str] = None


class CrowdGroupIn(BaseModel):
    group_id: str
    location: str
    size: int


class VenueIn(BaseModel):
    name: str = "Custom Venue"
    description: str = ""
    locations: list[LocationIn]
    routes: list[RouteIn]
    crowd_groups: list[CrowdGroupIn]


class WeightsIn(BaseModel):
    distance: float = Field(1.0, ge=0)
    time: float = Field(0.0, ge=0)
    congestion: float = Field(1.0, ge=0)
    overflow: float = Field(2.0, ge=0)


class ProblemSettings(BaseModel):
    weights: WeightsIn = WeightsIn()
    paths_per_group: Optional[int] = Field(2, ge=1, le=6)
    penalty_factor: float = Field(1.5, gt=1.0)


class ProblemRequest(BaseModel):
    venue: Optional[VenueIn] = None
    preset_id: Optional[str] = None
    settings: ProblemSettings = ProblemSettings()


SolverName = Literal[
    "naive", "classical_exact", "classical_cpsat",
    "qaoa_ideal", "qaoa_noisy", "ibm_hardware",
]


class QuantumSettings(BaseModel):
    reps: int = Field(2, ge=1, le=6)
    shots: int = Field(4096, ge=256, le=100_000)
    noise: Literal["depolarizing", "fake_backend"] = "depolarizing"
    noise_level: float = Field(1.0, ge=0, le=50)
    fake_backend: str = "FakeTorino"
    optimise_under_noise: bool = False
    seed: int = 7


class OptimizeRequest(ProblemRequest):
    solver: SolverName = "classical_exact"
    quantum: QuantumSettings = QuantumSettings()


class ExperimentRequest(BaseModel):
    kind: Literal["scaling", "noise", "depth", "versus"]
    quick: bool = False
    # Optional overrides of the experiment's settings, e.g. {"sizes": [4, 6], "instances": 2}
    config: dict = Field(default_factory=dict)
