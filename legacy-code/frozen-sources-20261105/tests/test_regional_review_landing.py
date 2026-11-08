from pathlib import Path
import tempfile
import unittest

from tools.verify_regional_review_landing import build_landing
from terrain_pipeline.mountain_source_adapter import file_sha256


class LandingTests(unittest.TestCase):
    def test_no_copy_fixed_links_and_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'verification/page.html'
            path.parent.mkdir()
            path.write_text('saved')
            index = {'schema': 'regional-single-landing-v1',
                'source_identity': '81d12179658ed02fefc94883cea1ce32888ff36199952d2bd88f68eb576f8cb2',
                'entries': [{'id': '2d', 'label': '<map>', 'path': 'verification/page.html',
                    'sha256': file_sha256(path), 'scope': 'saved only'}], 'limitations': ['not a natural outlet']}
            page = build_landing(index, root=root)
            self.assertIn('href="/verification/page.html"', page)
            self.assertIn('&lt;map&gt;', page)
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                build_landing(index, root=root)


if __name__ == '__main__':
    unittest.main()
