import tempfile
import unittest
from pathlib import Path

from tools.prepare_td_morphology_candidates import prepare


class PrepareTDMorphologyCandidatesTests(unittest.TestCase):
    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                prepare(output)


if __name__ == "__main__":
    unittest.main()
