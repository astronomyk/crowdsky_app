"""Pluggable sources of candidate targets for the planner.

The planner asks a *target source* for a pool of clusters, then picks
from that pool using the user's preferences and visibility constraints.
This indirection lets us swap the source later (e.g. a CrowdSky API
returning under-observed clusters) without changing the planner.
"""

from __future__ import annotations

from typing import Protocol

from .target_catalogue import Cluster, load_shortlist


class TargetSource(Protocol):
    """Anything that can yield a list of :class:`Cluster` candidates."""

    name: str

    def candidates(self) -> list[Cluster]:
        ...


class HuntShortlistSource:
    """Local Hunt+24 shortlist baked into the app."""

    name = "Hunt+24 shortlist"

    def candidates(self) -> list[Cluster]:
        return list(load_shortlist())


class CrowdSkyUnderObservedSource:
    """Stub: future API call to crowdsky.univie.ac.at.

    The server will return a ranked list of clusters that other observers
    have under-sampled.  For now this is a placeholder that falls back to
    the local shortlist with a flag so the UI can label it differently.
    """

    name = "CrowdSky under-observed (coming soon)"

    def candidates(self) -> list[Cluster]:
        # TODO: real implementation once the endpoint exists.  Expect
        # something like:
        #     ids = crowdsky_client.get_under_observed_cluster_ids()
        #     return [c for c in load_shortlist() if c.name in ids]
        return list(load_shortlist())


def get_default_source() -> TargetSource:
    return HuntShortlistSource()
