"""Public boundary checks with temporary database metadata, no media fixtures."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from checkoutcheck import server


class PublicReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data = patch.object(server, 'DATA', Path(self.directory.name))
        self.data.start()
        server.initialize()
        self.private_id = 'a'*32
        with server.db() as connection:
            connection.execute("INSERT INTO runs(id,suite_id,status,created,updated,request_key,request_hash,data) VALUES (?,?,?,0,0,?,?,?)",
                               (self.private_id, 'private', 'queued', 'private', 'hash', '{}'))
        self.environment = patch.dict(os.environ, CHECKOUTCHECK_READ_ONLY='1')
        self.environment.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        self.data.stop()
        self.directory.cleanup()

    def test_public_ui_and_health_are_readable(self):
        for path in ('/', '/app.js', '/perception.js', '/style.css', '/v1/state', '/v1/health', '/v1/perception'):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        state = self.client.get('/v1/state').json()
        self.assertTrue(state['runtime']['read_only'])
        self.assertEqual(state['runs'], [])
        self.assertEqual(self.client.get('/v1/health').json()['worker'], 'disabled_read_only')

    def test_write_routes_and_private_records_are_blocked(self):
        for path in ('/v1/assets', '/v1/cases', '/v1/suites', '/v1/runs', '/v1/perception/runs',
                     '/v1/videos/clip/analyze', '/v1/scan-logs/validate', '/v1/runs/'+self.private_id+'/cancel'):
            for method in ('post', 'put', 'delete'):
                response = getattr(self.client, method)(path, headers={'X-CheckoutCheck': 'local'})
                self.assertEqual(response.status_code, 403, path)
        for path in ('/v1/media/private', '/openapi.json', '/private-data/workbench.sqlite'):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        for suffix in ('', '/export'):
            self.assertEqual(self.client.get('/v1/runs/'+self.private_id+suffix).status_code, 404)

    def test_database_itself_rejects_writes(self):
        with server.db() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute('DELETE FROM runs')

    def test_cool_artifacts_are_explicitly_allowlisted(self):
        self.assertEqual(self.client.get('/v1/cool').json(), {'available': False})
        self.assertEqual(self.client.get('/v1/cool/stock').status_code, 404)
        self.assertEqual(self.client.get('/v1/cool/private').status_code, 403)
        self.assertEqual(self.client.post('/v1/cool', json={}).status_code, 403)

    def test_separate_snapshot_is_used(self):
        snapshot = Path(self.directory.name)/'review.sqlite'
        with server.db() as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
            target.execute('PRAGMA journal_mode=DELETE')
            target.execute('DELETE FROM runs')
        with patch.dict(os.environ, CHECKOUTCHECK_REVIEW_DB=str(snapshot)):
            with server.db() as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM runs').fetchone()[0], 0)

    def test_read_only_lifespan_starts_no_worker(self):
        with patch.object(server.threading, 'Thread') as thread:
            with TestClient(server.app) as client:
                self.assertEqual(client.get('/v1/health').status_code, 200)
            thread.assert_not_called()


if __name__ == '__main__':
    unittest.main()
