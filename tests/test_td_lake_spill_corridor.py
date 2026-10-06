import copy
import json
from pathlib import Path
import tempfile
import unittest

from terrain_pipeline.td_lake_spill_corridor import (
    build_lake_spill_corridors, validate_lake_spill_corridors)
from tools.prepare_td_lake_spill_corridors import file_hash, record_hash
from tools.audit_td_lake_spill_corridors import audit


def _edge(points):
    return {"face_id": "face:1", "routing_eligible": True,
            "sill_m": 11,
            "source_leaf_id": 1, "receiver_leaf_id": 2,
            "geometry": {"status": "accepted",
                "sill_m": 11,
                "source_lake_approach": {"xyz_m": [[0, 10, 0]], "all_samples_stage_covered": True},
                "cross_face": {"xyz_m": [[0, 10, 0], [1, 11, 0]], "cell_ids": [0, 1]},
                "downhill_terrain_approach": {"xyz_m": points, "cell_ids": list(range(1, len(points)+1))}}}


class LakeSpillCorridorTests(unittest.TestCase):
    def test_single_crest_candidate_retains_open_ports(self):
        result = build_lake_spill_corridors({"schema": "td-lake-spill-graph-v1",
            "identity_sha256": "a" * 64, "edges": [_edge([[1, 11, 0], [2, 10, 0], [3, 9, 0]])]})
        self.assertEqual(result["summary"]["candidate"], 1)
        self.assertFalse(result["continuous_bed_ready"])
        validate_lake_spill_corridors(result)

    def test_downstream_rise_is_rejected(self):
        result = build_lake_spill_corridors({"schema": "td-lake-spill-graph-v1",
            "identity_sha256": "a" * 64, "edges": [_edge([[1, 11, 0], [2, 9, 0], [3, 9.5, 0]])]})
        self.assertEqual(result["summary"]["rejected"], 1)

    def test_first_endpoint_crest_single_downhill_and_exact_join(self):
        edge = _edge([[1, 10, 0]])
        edge['geometry']['cross_face']['xyz_m'] = [[0, 11, 0], [1, 10, 0]]
        graph = {'schema': 'td-lake-spill-graph-v1', 'identity_sha256': 'a'*64, 'edges': [edge]}
        result = build_lake_spill_corridors(graph)
        self.assertEqual(result['summary']['candidate'], 1)
        self.assertEqual(result['corridors'][0]['profile']['crest_station'], 0)
        edge['geometry']['downhill_terrain_approach']['xyz_m'][0][1] = 9
        self.assertEqual(build_lake_spill_corridors(graph)['corridors'][0]['rejection_reasons'], ['join_xyz_mismatch'])
        edge['geometry']['downhill_terrain_approach']['xyz_m'][0][1] = 10
        edge['geometry']['downhill_terrain_approach']['cell_ids'][0] = 2
        self.assertEqual(build_lake_spill_corridors(graph)['corridors'][0]['rejection_reasons'], ['join_cell_mismatch'])

    def test_independent_audit_detects_parent_geometry_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(name, value):
                target = root/name
                target.write_text(json.dumps(value), encoding='utf8')
                return target
            graph = {'schema': 'td-lake-spill-graph-v1', 'edges': [_edge([[1, 11, 0], [2, 10, 0]])]}
            graph['identity_sha256'] = record_hash(graph)
            graph_path = write('graph.json', graph)
            index = {'cases': [{'case_id': 'baseline', 'graph': {'path': 'graph.json', 'sha256': file_hash(graph_path), 'identity_sha256': graph['identity_sha256']}}]}
            index_path = write('index.json', index)
            audit_path = write('parent-audit.json', {'status': 'passed', 'index_sha256': file_hash(index_path)})
            provenance = {'parent_index': {'path': str(index_path), 'sha256': file_hash(index_path)},
                          'parent_audit': {'path': str(audit_path), 'sha256': file_hash(audit_path)},
                          'graph': {**index['cases'][0]['graph'], 'path': str(graph_path)}, 'case_id': 'baseline'}
            result = build_lake_spill_corridors(graph, provenance=provenance)
            target = write('corridors.json', result)
            self.assertEqual(audit(target, expected_sha256=file_hash(target))['status'], 'passed')
            changed = copy.deepcopy(result)
            changed['corridors'][0]['source_geometry']['source_lake_approach']['all_samples_stage_covered'] = False
            from terrain_pipeline.td_lake_spill_corridor import _digest
            changed['identity_sha256'] = _digest({key: value for key, value in changed.items() if key != 'identity_sha256'})
            target = write('changed.json', changed)
            self.assertEqual(audit(target, expected_sha256=file_hash(target))['status'], 'failed')


if __name__ == "__main__":
    unittest.main()
