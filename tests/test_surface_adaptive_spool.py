import tempfile
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.surface_adaptive_spool import SegmentedWorkspaceSpool


class SegmentedSpoolTests(unittest.TestCase):
    def test_cross_segment_random_reads_preserve_every_byte_and_bounds(self):
        directory = Path(__file__).resolve().parents[1]/".scratch"
        with tempfile.TemporaryDirectory(dir=directory) as folder:
            spool = SegmentedWorkspaceSpool(folder,memory_limit_bytes=1024,segment_limit_bytes=8192)
            first = np.random.default_rng(18).bytes(20000)
            second = np.random.default_rng(19).bytes(31000)
            spool.write(first)
            spool.write(second)
            spool.flush()
            self.assertLessEqual(max(path.stat().st_size for path in Path(folder).iterdir()),8192)
            self.assertGreater(spool.temporary_storage_nbytes,40000)
            self.assertLessEqual(spool.resident_nbytes,1024)
            spool.seek(0)
            self.assertEqual(spool.read(),first+second)
            for offset,length in ((8000,22000),(19000,15000),(49000,2000)):
                spool.seek(offset)
                self.assertEqual(spool.read(length),(first+second)[offset:offset+length])
            spool.seek(0)
            with self.assertRaises(ValueError):
                spool.write(b"immutable")
            spool.seek(0,2)
            spool.write(b"endpoint")
            spool.seek(len(first)+len(second))
            self.assertEqual(spool.read(),b"endpoint")
            spool.close()
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_rejects_unbounded_file_and_ram_configuration(self):
        for memory,segment in ((0,1024),(2048,1024),(1024,257*1024**2)):
            with self.assertRaises(ValueError):
                SegmentedWorkspaceSpool("unused",memory_limit_bytes=memory,segment_limit_bytes=segment)


if __name__=="__main__":
    unittest.main()
