"""Portable terrain artifacts, independent of game consumers."""

from .contracts import ArtifactIdentity, SurfaceWater, TerrainArtifact
from terrain_pipeline.common_infra import load_artifact, save_artifact

__all__ = ["ArtifactIdentity", "SurfaceWater", "TerrainArtifact", "load_artifact", "save_artifact"]
