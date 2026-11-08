import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry
from terrain_pipeline.world_river_network_io import query_node, read_network, write_network
from terrain_pipeline.td_source import make_spec
from tools.query_world_terrain_region import main as query_region
from tools.query_world_terrain_water import main as query_product


class NetworkIOTests(unittest.TestCase):
    def graph(self):
        shape = (6, 7)
        mesh = build_mesh(shape, (100, 200))
        bed = np.arange(np.prod(shape), dtype=float).reshape(shape)
        outlets = np.zeros(shape, bool)
        outlets[0] = True
        routing = route_graph(bed, outlets, mesh)
        geometry = build_irregular_channel_geometry(bed, np.ones(shape),
            np.ones(shape, bool), mesh, routing.receiver)
        graph = geometry["graph"]
        graph.update(spill_source_node=np.array([14]), spill_target_node=np.array([7]),
                     spill_volume_m3=np.array([3.]))
        return graph, geometry["graph_metadata"]

    def test_roundtrip_preserves_reaches_flags_and_separate_spill(self):
        graph, metadata = self.graph()
        with tempfile.TemporaryDirectory() as directory:
            record = write_network(directory, graph, metadata)
            saved = read_network(directory, record)
            for name in graph:
                np.testing.assert_array_equal(graph[name], saved[name])
            source = int(graph["reach_source"][0])
            node = query_node(saved, [100 + source % 7, 200 + source // 7], metadata)
            self.assertEqual(node["node_id"], source)
            self.assertEqual(node["world_xz_m"], [graph["node_x_m"][source], graph["node_z_m"][source]])
            reach = node["outgoing_reaches"][0]
            self.assertEqual(reach["target_node"], int(graph["reach_target"][0]))
            self.assertIn("projection_blocked", reach)
            self.assertIn("max_cut_limited", reach)
            spill = query_node(saved, [100, 202], metadata)["outgoing_spill_edges"]
            self.assertEqual(spill[0]["volume_m3"], 3.)
            with open(Path(directory) / record["file"], "ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "network identity"):
                read_network(directory, record)

    def test_single_product_cold_query_and_legacy_product(self):
        from terrain_pipeline.common_infra import identity
        graph, graph_metadata = self.graph()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arrays = {"final_bed_m": np.zeros((6, 7))}
            np.savez(root / "arrays.npz", **arrays)
            metadata = {"origin_native_xz": [100, 200], "shape_zx": [6, 7]}
            for with_graph in (False, True):
                if with_graph:
                    metadata["network"] = write_network(root, graph, graph_metadata)
                digest = identity(arrays, metadata)
                (root / "metadata.json").write_text(json.dumps({**metadata, "identity_sha256": digest}), encoding="utf-8")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    query_product([directory, "--native-xz", "100", "202"])
                result = json.loads(output.getvalue())
                self.assertEqual(result["river_network"] is not None, with_graph)
            with open(root / "river-network.npz", "ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "network identity"):
                query_product([directory, "--native-xz", "100", "202"])

    def test_real_solver_network_published_queried_and_corruption_rejected(self):
        from terrain_pipeline import td_source as disk
        from terrain_pipeline import td_source as memory
        from terrain_pipeline.surface_hydraulics import form_connected_region
        from terrain_pipeline.drainage import solve_disk_region as solve_disk_region

        forcing = {"runoff_m_per_year": .5, "duration_seconds": 86400.,
                   "channel_threshold_m3_s": 1e-8}
        spec = make_spec("lakes")

        def compose(spec, pages, origin, shape, **kwargs):
            z, x = np.indices(shape)
            bed = 15. - np.hypot(x - shape[1] / 2., z - shape[0] / 2.)
            ocean = np.zeros(shape, bool)
            ocean[[0, -1]] = True
            ocean[:, [0, -1]] = True
            bed[ocean] = 0.
            return {"composed_elevation_m": bed, "ocean_mask": ocean,
                    "valid_mask": np.ones(shape, bool),
                    "metadata": {"origin_native_xz": list(origin), "world_seed": 20261020}}

        with tempfile.TemporaryDirectory() as directory:
            for backend in (disk, memory):
                with self.subTest(backend=backend.__name__):
                    root = Path(directory) / backend.__name__
                    registry = backend.open_registry(root, spec, "physical", forcing, 1.)
                    if backend is disk:
                        request = backend.plan(registry, [100, 100], [24, 24])
                        kwargs = {"compose": compose, "solve": solve_disk_region}
                    else:
                        coverage = lambda *args: {"missing_cells": 0}
                        request = backend.plan(registry, [100, 100], [24, 24], [], coverage)
                        kwargs = {"compose": compose, "form": form_connected_region,
                                  "render": lambda arrays, origin, path: None}
                    component = backend.prepare(root, registry, request, [], spec, **kwargs)
                    product_root = root / "versions" / component["version"]
                    if backend is disk:
                        _, metadata = disk.read_disk_manifest(root, component, registry["world_identity"])
                        self.assertEqual(metadata["network"]["file"], "water/river-network.npz")
                        hit = disk.plan_disk_region(registry, [105, 105], [1, 1])
                    else:
                        _, metadata = memory.read_region_component(root, component, registry["world_identity"])
                        hit = memory.plan_region_store(registry, [105, 105], [1, 1], [], coverage)
                    graph = read_network(product_root, metadata["network"])
                    self.assertGreater(graph["reach_source"].size, 0)
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        query_region([str(root), "--native-xz", "105", "105"])
                    result = json.loads(output.getvalue())
                    self.assertEqual(result["river_network"]["node_id"], 125)
                    self.assertEqual(result["river_network"]["world_xz_m"],
                                     [graph["node_x_m"][125], graph["node_z_m"][125]])
                    with open(product_root / metadata["network"]["file"], "ab") as stream:
                        stream.write(b"changed network")
                    with self.assertRaisesRegex(ValueError, "network identity"):
                        backend.prepare(root, registry, hit, [], spec, **kwargs)
                    with self.assertRaisesRegex(ValueError, "network identity"):
                        query_region([str(root), "--native-xz", "105", "105"])
                    registry["world"]["revision" if backend is disk else "preparation_revision"] = "old-D8"
                    (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        backend.open_registry(root, spec, "physical", forcing, 1.)


if __name__ == "__main__":
    unittest.main()
