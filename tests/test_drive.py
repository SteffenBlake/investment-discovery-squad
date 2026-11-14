import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment_engine.configuration import build_runtime_settings
from investment_engine.drive import Drive, HTTP, PROJECT, Response
from tests.fixtures import completed_installation


def response(value, status=200, headers=None):
    return Response(status, headers or {}, json.dumps(value).encode())


class FakeHTTP:
    def __init__(self, responses):
        self.responses = [response({'access_token': 'fictional-runtime-token', 'expires_in': 3600}), *responses]
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError('Unexpected HTTP request')
        return self.responses.pop(0)


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = build_runtime_settings(completed_installation(self.root))
        self.env = patch.dict(os.environ, {'SQUAD_GOOGLE_REFRESH_TOKEN': 'fictional-refresh', 'SQUAD_GOOGLE_CLIENT_ID': 'fictional-client', 'SQUAD_GOOGLE_CLIENT_SECRET': 'fictional-secret'}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_oauth_refresh_on_401_retries_with_new_token(self):
        with patch.dict(os.environ, {'SQUAD_GOOGLE_REFRESH_TOKEN': 'fictional-refresh', 'SQUAD_GOOGLE_CLIENT_ID': 'fictional-client', 'SQUAD_GOOGLE_CLIENT_SECRET': 'fictional-secret'}):
            http = FakeHTTP([Response(401, {}, b''), response({'access_token': 'new-fictional-token', 'expires_in': 3600}), response({'ok': True})])
            result = Drive(self.settings, http=http).request('GET', '/drive/v3/about?fields=storageQuota')
            self.assertEqual(result.status, 200)
            self.assertEqual(http.calls[-1][2]['headers']['Authorization'], 'Bearer new-fictional-token')
            self.assertEqual(http.calls[2][1], 'https://oauth2.googleapis.com/token')

    def test_failed_authorization_error_does_not_echo_token_or_http_body(self):
        http = FakeHTTP([Response(403, {}, b'fictional-runtime-token')])
        with self.assertRaises(ValueError) as error:
            Drive(self.settings, http=http).request('GET', '/drive/v3/about')
        self.assertNotIn('fictional-runtime-token', str(error.exception))

    def test_all_refresh_credentials_required_before_any_network_request(self):
        http = FakeHTTP([])
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'refresh token, client ID and client secret'):
                Drive(self.settings, http=http).request('GET', '/drive/v3/about')
        self.assertEqual(http.calls, [])

    def test_account_quota_and_app_budget_block_upload_before_creation(self):
        drive = Drive(self.settings, http=FakeHTTP([response({'storageQuota': {'usage': '990', 'limit': '1000'}})]))
        with self.assertRaisesRegex(ValueError, 'account storage'):
            drive.check_capacity(100, [])
        drive = Drive(self.settings, http=FakeHTTP([]))
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            drive.check_capacity(2000, [{'size': str(self.settings['storage']['cloud_backup']['max_bytes'])}])

    def test_resumable_upload_uses_reviewed_folder_and_download_verifies_bytes(self):
        path = self.root / 'backup.zip'
        path.write_bytes(b'fictional-archive')
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        metadata = {'id': 'remote-id', 'size': str(path.stat().st_size), 'parents': ['fictional-folder'],
                    'appProperties': {'project': PROJECT, 'profile_id': 'test-owner', 'setup_identity': 'owner', 'sha256': checksum}}
        http = FakeHTTP([response({'mimeType': 'application/vnd.google-apps.folder'}), response({'files': []}),
                         response({'storageQuota': {'usage': '0', 'limit': '15000000000'}}),
                         response({}, headers={'Location': 'https://www.googleapis.com/upload/drive/v3/files?upload_id=fixture'}),
                         response(metadata), response(metadata), Response(200, {}, path.read_bytes())])
        drive = Drive(self.settings, http=http)
        remote = drive.upload(path, {'setup_identity': 'owner'}, checksum)
        self.assertEqual(remote['id'], 'remote-id')
        observed, data = drive.download(remote['id'], expected_identity='owner')
        self.assertEqual(data, path.read_bytes())
        created = json.loads(http.calls[4][2]['body'])
        self.assertEqual(created['parents'], ['fictional-folder'])
        self.assertNotIn('fictional-runtime-token', http.calls[4][2]['body'].decode())

    def test_completed_upload_is_reused_after_lost_response(self):
        path = self.root / 'backup.zip'
        path.write_bytes(b'fixture')
        metadata = {'id': 'already-uploaded', 'size': '7', 'appProperties': {'sha256': 'digest', 'setup_identity': 'owner'}}
        http = FakeHTTP([response({'mimeType': 'application/vnd.google-apps.folder'}), response({'files': [metadata]})])
        result = Drive(self.settings, http=http).upload(path, {'setup_identity': 'owner'}, 'digest')
        self.assertEqual(result['id'], 'already-uploaded')
        self.assertEqual(len(http.calls), 3)

    def test_upload_session_cannot_redirect_credentials_to_another_host(self):
        path = self.root / 'backup.zip'
        path.write_bytes(b'fixture')
        http = FakeHTTP([response({'mimeType': 'application/vnd.google-apps.folder'}), response({'files': []}),
                         response({'storageQuota': {'usage': '0', 'limit': '100000'}}),
                         response({}, headers={'Location': 'https://attacker.invalid/upload/drive/v3/files'})])
        with self.assertRaisesRegex(ValueError, 'invalid resumable'):
            Drive(self.settings, http=http).upload(path, {'setup_identity': 'owner'}, 'digest')
        self.assertEqual(len(http.calls), 5)

    def test_download_rejects_wrong_folder_identity_and_corruption(self):
        metadata = {'id': 'id', 'size': '4', 'parents': ['fictional-folder'],
                    'appProperties': {'project': PROJECT, 'profile_id': 'test-owner', 'setup_identity': 'owner', 'sha256': 'wrong'}}
        http = FakeHTTP([response(metadata), Response(200, {}, b'data')])
        with self.assertRaisesRegex(ValueError, 'checksum'):
            Drive(self.settings, http=http).download('id', expected_identity='owner')
        with self.assertRaisesRegex(ValueError, 'identity'):
            Drive(self.settings, http=FakeHTTP([response(metadata)])).download('id', expected_identity='other')

    def test_transport_rejects_non_google_or_plaintext_destinations(self):
        for url in ('http://www.googleapis.com/a', 'https://attacker.invalid/a'):
            with self.assertRaisesRegex(ValueError, 'approved Google'):
                HTTP().request('GET', url)
