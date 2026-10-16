# WHAT THIS FILE IS FOR: describes the exact shape of every request the web app sends.
# Each class below is a form template: the server checks incoming data against it.
# Missing or out of range values are rejected with a clear error before any maths runs.
# Used by main.py and hardware_routes.py.
from typing import Literal, Optional

from pydantic import BaseModel, Field


# One place in the venue, such as a room or an exit.
# It may have a capacity (how many people fit) and a position on the map.
class LocationIn(BaseModel):
    id: str
    location_type: str
    capacity: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None


# One corridor or path between two places, with its capacity and length.
# By default people can walk it both ways.
class RouteIn(BaseModel):
    from_node: str
    to_node: str
    capacity: int
    length: float
    travel_time: Optional[float] = None
    bidirectional: bool = True
    id: Optional[str] = None


# A group of people waiting at one place, and how many of them there are.
class CrowdGroupIn(BaseModel):
    group_id: str
    location: str
    size: int


# A whole venue: its name, places, paths between them and the crowd groups inside.
class VenueIn(BaseModel):
    name: str = "Custom Venue"
    description: str = ""
    locations: list[LocationIn]
    routes: list[RouteIn]
    crowd_groups: list[CrowdGroupIn]


# How much the optimiser should care about each cost: distance, time, crowding and overflow.
# Overflow means more people on a path than it can hold. No weight may be negative.
class WeightsIn(BaseModel):
    distance: float = Field(1.0, ge=0)
    time: float = Field(0.0, ge=0)
    congestion: float = Field(1.0, ge=0)
    overflow: float = Field(2.0, ge=0)


# Settings for building the problem: the weights and how many route choices each group gets.
# Each group may get 1 to 6 route choices. The penalty factor must be above 1,
# so that breaking a rule always costs more than it could save.
class ProblemSettings(BaseModel):
    weights: WeightsIn = WeightsIn()
    paths_per_group: Optional[int] = Field(2, ge=1, le=6)
    penalty_factor: float = Field(1.5, gt=1.0)


# A request about a venue: either a drawn venue or the name of a preset, plus the settings.
class ProblemRequest(BaseModel):
    venue: Optional[VenueIn] = None
    preset_id: Optional[str] = None
    settings: ProblemSettings = ProblemSettings()


# The only solver names the app may ask for. The first three are classical methods,
# the rest are quantum: an ideal simulator, a noisy simulator and real IBM hardware.
SolverName = Literal[
    "naive", "classical_exact", "classical_cpsat",
    "qaoa_ideal", "qaoa_noisy", "ibm_hardware",
]


# Settings for quantum runs: circuit depth (reps) and number of repeated measurements (shots).
# Also the kind and strength of simulated noise, and a seed so results can be repeated exactly.
class QuantumSettings(BaseModel):
    reps: int = Field(2, ge=1, le=6)
    shots: int = Field(4096, ge=256, le=100_000)
    noise: Literal["depolarizing", "fake_backend"] = "depolarizing"
    noise_level: float = Field(1.0, ge=0, le=50)
    fake_backend: str = "FakeTorino"
    optimise_under_noise: bool = False
    seed: int = 7


# A request to solve a venue: everything in ProblemRequest, plus which solver to use.
class OptimizeRequest(ProblemRequest):
    solver: SolverName = "classical_exact"
    quantum: QuantumSettings = QuantumSettings()
    # False for display only calls (the Overview demo), so they never fill Run history.
    record: bool = True


# A request to start one of the four experiment types, optionally in quick mode.
class ExperimentRequest(BaseModel):
    kind: Literal["scaling", "noise", "depth", "versus"]
    quick: bool = False
    # Optional overrides of the experiment's settings, e.g. {"sizes": [4, 6], "instances": 2}
    config: dict = Field(default_factory=dict)


# A request to save or update a venue in the user's saved venues.
class VenueSaveRequest(BaseModel):
    venue: VenueIn
