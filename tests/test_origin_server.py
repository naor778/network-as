import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_server import origin_server


class OriginPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.files = root / 'files'
        self.files.mkdir()
        (self.files / 'hello.txt').write_bytes(b'hello')
        (root / 'private.txt').write_bytes(b'private-content')
        self.patch = patch.object(origin_server, '__file__', str(root / 'origin_server.py'))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def request(self, path):
        return origin_server.handle_request(f'GET {path} HTTP/1.1\r\n\r\n')

    def test_normal_file(self):
        response = self.request('/hello.txt')
        self.assertTrue(response.startswith(b'HTTP/1.1 200'))
        self.assertTrue(response.endswith(b'hello'))

    def test_parent_directory_is_forbidden(self):
        response = self.request('/../private.txt')
        self.assertTrue(response.startswith(b'HTTP/1.1 403'))
        self.assertNotIn(b'private-content', response)

    def test_similarly_named_sibling_directory_is_forbidden(self):
        sibling = self.files.parent / 'files-backup'
        sibling.mkdir()
        (sibling / 'private.txt').write_bytes(b'private-content')
        self.assertTrue(self.request('/../files-backup/private.txt').startswith(b'HTTP/1.1 403'))

    def test_external_symlink_is_forbidden_and_not_listed(self):
        (self.files / 'link.txt').symlink_to(self.files.parent / 'private.txt')
        self.assertTrue(self.request('/link.txt').startswith(b'HTTP/1.1 403'))
        self.assertNotIn(b'link.txt', self.request('/'))

    def test_missing_file(self):
        self.assertTrue(self.request('/missing.txt').startswith(b'HTTP/1.1 404'))


if __name__ == '__main__':
    unittest.main()
