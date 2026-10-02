"""
Preset venues. Sizes are chosen so that with 2 candidate paths per group the
qubit counts are 4, 6, 8 and 10, matching Experiment 1 in the proposal.
Coordinates are for the frontend canvas (roughly 0 to 800 by 0 to 500).
"""
from app.core.venue import Venue


def micro_hall() -> Venue:
    v = Venue("Micro Hall", description="Two groups, two exits. Small enough for real IBM hardware (4 qubits).")
    v.add_location("Hall", "hall", x=200, y=250)
    v.add_location("Lobby", "zone", x=400, y=250)
    v.add_location("Exit A", "exit", capacity=200, x=650, y=120)
    v.add_location("Exit B", "exit", capacity=200, x=650, y=380)
    v.add_route("Hall", "Exit A", capacity=150, length=20)
    v.add_route("Hall", "Lobby", capacity=250, length=10)
    v.add_route("Lobby", "Exit A", capacity=200, length=12)
    v.add_route("Lobby", "Exit B", capacity=200, length=18)
    v.add_group("Hall crowd", "Hall", 140)
    v.add_group("Lobby crowd", "Lobby", 120)
    return v


def small_event_hall() -> Venue:
    v = Venue("Small Event Hall", description="Four zones, two exits, three crowd groups (6 qubits).")
    v.add_location("Main Hall", "hall", x=180, y=170)
    v.add_location("Stage Area", "event", x=180, y=360)
    v.add_location("Foyer", "zone", x=420, y=80)
    v.add_location("Side Corridor", "corridor", x=420, y=330)
    v.add_location("Exit North", "exit", capacity=300, x=680, y=120)
    v.add_location("Exit South", "exit", capacity=300, x=680, y=400)
    v.add_route("Main Hall", "Exit North", capacity=200, length=20)
    v.add_route("Main Hall", "Side Corridor", capacity=250, length=12)
    v.add_route("Side Corridor", "Exit South", capacity=250, length=18)
    v.add_route("Stage Area", "Exit North", capacity=200, length=15)
    v.add_route("Stage Area", "Side Corridor", capacity=250, length=14)
    v.add_route("Foyer", "Exit North", capacity=150, length=10)
    v.add_route("Foyer", "Exit South", capacity=200, length=22)
    v.add_group("Main Hall crowd", "Main Hall", 180)
    v.add_group("Stage crowd", "Stage Area", 150)
    v.add_group("Foyer crowd", "Foyer", 120)
    return v


def concert_venue() -> Venue:
    v = Venue("Concert Venue", description="Four crowd sections competing for three gates (8 qubits).")
    v.add_location("Floor", "zone", x=400, y=260)
    v.add_location("Stand West", "seating", x=140, y=260)
    v.add_location("Stand East", "seating", x=660, y=260)
    v.add_location("Balcony", "seating", x=400, y=460)
    v.add_location("West Concourse", "corridor", x=230, y=110)
    v.add_location("East Concourse", "corridor", x=570, y=110)
    v.add_location("Gate 1", "exit", capacity=500, x=80, y=40)
    v.add_location("Gate 2", "exit", capacity=400, x=400, y=30)
    v.add_location("Gate 3", "exit", capacity=400, x=720, y=40)
    v.add_route("Floor", "West Concourse", capacity=400, length=15)
    v.add_route("Floor", "East Concourse", capacity=400, length=15)
    v.add_route("Stand West", "West Concourse", capacity=300, length=10)
    v.add_route("Stand East", "East Concourse", capacity=300, length=10)
    v.add_route("Balcony", "West Concourse", capacity=250, length=25)
    v.add_route("Balcony", "East Concourse", capacity=250, length=30)
    v.add_route("West Concourse", "Gate 1", capacity=500, length=20)
    v.add_route("West Concourse", "Gate 2", capacity=350, length=35)
    v.add_route("East Concourse", "Gate 3", capacity=400, length=20)
    v.add_route("East Concourse", "Gate 2", capacity=350, length=25)
    v.add_group("Floor crowd", "Floor", 350)
    v.add_group("West stand", "Stand West", 250)
    v.add_group("East stand", "Stand East", 200)
    v.add_group("Balcony", "Balcony", 180)
    return v


def exhibition_centre() -> Venue:
    v = Venue("Exhibition Centre", description="Visitors in five areas leaving through three exits (10 qubits).")
    v.add_location("Hall 1", "hall", x=120, y=150)
    v.add_location("Hall 2", "hall", x=400, y=120)
    v.add_location("Hall 3", "hall", x=680, y=150)
    v.add_location("Atrium", "zone", x=400, y=300)
    v.add_location("Food Court", "zone", x=600, y=420)
    v.add_location("North Corridor", "corridor", x=400, y=30)
    v.add_location("Main Exit", "exit", capacity=400, x=400, y=470)
    v.add_location("West Exit", "exit", capacity=250, x=40, y=300)
    v.add_location("East Exit", "exit", capacity=250, x=760, y=300)
    v.add_route("Hall 1", "Atrium", capacity=300, length=20)
    v.add_route("Hall 2", "Atrium", capacity=300, length=15)
    v.add_route("Hall 3", "Atrium", capacity=300, length=25)
    v.add_route("Food Court", "Atrium", capacity=250, length=10)
    v.add_route("Atrium", "Main Exit", capacity=400, length=15)
    v.add_route("Hall 1", "West Exit", capacity=200, length=30)
    v.add_route("Hall 3", "East Exit", capacity=200, length=28)
    v.add_route("Hall 2", "North Corridor", capacity=250, length=12)
    v.add_route("North Corridor", "East Exit", capacity=250, length=22)
    v.add_route("North Corridor", "West Exit", capacity=250, length=24)
    v.add_route("Food Court", "East Exit", capacity=150, length=35)
    v.add_group("Hall 1 visitors", "Hall 1", 160)
    v.add_group("Hall 2 visitors", "Hall 2", 200)
    v.add_group("Hall 3 visitors", "Hall 3", 140)
    v.add_group("Atrium visitors", "Atrium", 120)
    v.add_group("Food Court visitors", "Food Court", 100)
    return v


PRESETS = {
    "micro_hall": micro_hall,
    "small_event_hall": small_event_hall,
    "concert_venue": concert_venue,
    "exhibition_centre": exhibition_centre,
}


def get_preset(preset_id: str) -> Venue:
    if preset_id not in PRESETS:
        raise KeyError(f"Unknown preset '{preset_id}'. Options: {', '.join(PRESETS)}")
    return PRESETS[preset_id]()
