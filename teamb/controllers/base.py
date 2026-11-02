"""Common controller interface (Aditya's design).

    reset(config, seed, topology)   once before the run
    observe(observation)            every step — sensor data only (detectors / probes),
                                    ground truth only when observation_source == "oracle"
    propose_action(state)           every step — {junction: "EW" | "NS" | None}
                                    None (or a missing junction) means "keep the current green"
    log(step)                       optional diagnostics

The safety supervisor validates the proposal and runs yellow/all-red, so a controller
never builds SUMO state strings itself.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

REGISTRY: dict[str, type["Controller"]] = {}


def register(cls: type["Controller"]) -> type["Controller"]:
    REGISTRY[cls.name] = cls
    return cls


class Controller(ABC):
    name = "base"
    label = "Base controller"
    description = ""
    owner = ""
    observation_source = "detector"  # "detector" | "probe" | "fused" | "oracle"

    def __init__(self, **params):
        self.params = params
        self.observation: dict | None = None
        self.topology = None
        self.config: dict = {}
        self.seed = 0

    def reset(self, config: dict, seed: int, topology) -> None:
        self.config, self.seed, self.topology = config, seed, topology
        self.observation = None

    def observe(self, observation: dict) -> None:
        self.observation = observation

    @abstractmethod
    def propose_action(self, state: dict) -> dict[str, str | None]: ...

    def log(self, step: int) -> dict | None:
        return None

    # --- optional hooks used by the digital twin ---------------------------
    def pending_recommendation(self) -> dict | None:
        """A plan waiting for an engineer's approval (AI recommender)."""
        return None

    def handle_command(self, command: dict) -> dict | None:
        """React to a twin command such as {"type": "approve"}; return a short status."""
        return None

    def drain_events(self) -> list[dict]:
        """Events the controller wants in the run log / twin, e.g. {"t", "type": "plan_applied", ...}."""
        return []

    def summary(self) -> dict | None:
        """Controller-specific results for summary.json (e.g. the plan the AI recommender applied)."""
        return None

    def describe(self) -> dict:
        return {"name": self.name, "label": self.label, "description": self.description, "owner": self.owner}

    def close(self) -> None:
        pass


def make_controller(name: str, **params) -> Controller:
    if name not in REGISTRY:
        raise KeyError(f"unknown controller '{name}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[name](**params)


def available() -> list[dict]:
    return [cls(**{}).describe() for cls in REGISTRY.values()]
