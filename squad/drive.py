"""Scoped Google Drive blob backups. Runtime-only credentials; no credential-bearing logs."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = 'https://www.googleapis.com'
TOKEN = 'https://oauth2.googleapis.com/token'
PROJECT = 'investment-discovery-squad'


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class HTTP:
    def request(self, method, url, *, headers=None, body=None, max_bytes=2_000_000):
        target = urllib.parse.urlsplit(url)
        if target.scheme != 'https' or target.hostname not in {'www.googleapis.com', 'oauth2.googleapis.com'} or target.port not in (None, 443):
            raise ValueError('Drive transport requires an approved Google HTTPS endpoint')
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as stream:
                raw = stream.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise ValueError('Drive response exceeded the configured size limit')
                return Response(stream.status, dict(stream.headers), raw)
        except urllib.error.HTTPError as exc:
            # Do not echo response bodies, request URLs, OAuth forms or tokens.
            code = exc.code
            exc.close()
            return Response(code, {}, b'')
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError('Drive network request failed; inspect remote backup state before retry') from None


class Drive:
    def __init__(self, settings, *, http=None):
        self.config = settings['storage']['cloud_backup']
        self.profile_id = settings['profile_id']
        self.http = http or HTTP()
        self.token = None
        self.expires = 0

    def _refresh(self):
        keys = ('SQUAD_GOOGLE_REFRESH_TOKEN', 'SQUAD_GOOGLE_CLIENT_ID', 'SQUAD_GOOGLE_CLIENT_SECRET')
        if not all(os.environ.get(key) for key in keys):
            raise ValueError('Drive authorization required: bind Google OAuth refresh token, client ID and client secret in runtime secrets')
        body = urllib.parse.urlencode({'refresh_token': os.environ[keys[0]], 'client_id': os.environ[keys[1]],
                                      'client_secret': os.environ[keys[2]], 'grant_type': 'refresh_token'}).encode()
        response = self.http.request('POST', TOKEN, headers={'Content-Type': 'application/x-www-form-urlencoded'}, body=body)
        if response.status != 200:
            raise ValueError('Drive OAuth refresh failed; reauthorize the backup app')
        value = json.loads(response.body)
        if not value.get('access_token'):
            raise ValueError('Drive OAuth response contained no usable token')
        self.token = value['access_token']
        self.expires = time.monotonic() + max(0, int(value.get('expires_in', 3600)) - 60)

    def request(self, method, path, *, body=None, headers=None, maximum=2_000_000):
        if not self.token or time.monotonic() >= self.expires:
            self._refresh()
        url = path if path.startswith('https://') else API + path
        if urllib.parse.urlsplit(url).hostname != 'www.googleapis.com':
            raise ValueError('Invalid Drive upload-session destination')
        result = self.http.request(method, url, headers={**(headers or {}), 'Authorization': 'Bearer ' + self.token}, body=body, max_bytes=maximum)
        if result.status == 401:
            self._refresh()
            result = self.http.request(method, url, headers={**(headers or {}), 'Authorization': 'Bearer ' + self.token}, body=body, max_bytes=maximum)
        if result.status not in (200, 201):
            raise ValueError(f'Drive HTTP {result.status}; no verified cloud backup was recorded')
        return result

    def metadata(self, file_id):
        file_id = urllib.parse.quote(file_id, safe='')
        return json.loads(self.request('GET', f'/drive/v3/files/{file_id}?fields=id,name,size,createdTime,parents,appProperties,mimeType,md5Checksum').body)

    def folder(self):
        metadata = self.metadata(self.config['folder_id'])
        if metadata.get('mimeType') != 'application/vnd.google-apps.folder':
            raise ValueError('Configured Drive destination is not an authorized folder')
        return metadata

    def list(self):
        self.folder()
        files, page = [], None
        while True:
            query = f"'{self.config['folder_id']}' in parents and trashed=false and appProperties has {{key='project' and value='{PROJECT}'}} and appProperties has {{key='profile_id' and value='{self.profile_id}'}}"
            args = {'q': query, 'pageSize': 100, 'fields': 'nextPageToken,files(id,name,size,createdTime,parents,appProperties,md5Checksum)'}
            if page:
                args['pageToken'] = page
            payload = json.loads(self.request('GET', '/drive/v3/files?' + urllib.parse.urlencode(args)).body)
            files.extend(payload.get('files', []))
            page = payload.get('nextPageToken')
            if not page:
                return files
            if len(files) > 10_000:
                raise ValueError('Backup inventory exceeds the bounded listing limit')

    def check_capacity(self, size, files):
        if size > self.config['max_archive_bytes']:
            raise ValueError('Snapshot exceeds the configured archive-size limit')
        used = sum(int(file.get('size', 0)) for file in files)
        if used + size > self.config['max_bytes']:
            raise ValueError('Backup budget exhausted; preserve usable copies and review retention; no paid upgrade attempted')
        quota = json.loads(self.request('GET', '/drive/v3/about?fields=storageQuota').body)['storageQuota']
        if quota.get('limit') and int(quota['usage']) + size > int(quota['limit']):
            raise ValueError('Google account storage is full; Gmail/Photos share this allowance')

    def upload(self, path, manifest, sha256):
        files = self.list()
        for file in files:
            props = file.get('appProperties', {})
            if props.get('sha256') == sha256 and props.get('setup_identity') == manifest['setup_identity'] and int(file.get('size', 0)) == path.stat().st_size:
                return file  # Recover an upload whose successful response was lost.
        size = path.stat().st_size
        self.check_capacity(size, files)
        metadata = {'name': path.name, 'parents': [self.config['folder_id']], 'mimeType': 'application/zip',
                    'appProperties': {'project': PROJECT, 'profile_id': self.profile_id,
                                      'setup_identity': manifest['setup_identity'], 'sha256': sha256}}
        response = self.request('POST', '/upload/drive/v3/files?uploadType=resumable&fields=id,name,size,createdTime,parents,appProperties,md5Checksum',
                                headers={'Content-Type': 'application/json', 'X-Upload-Content-Type': 'application/zip',
                                         'X-Upload-Content-Length': str(size)}, body=json.dumps(metadata).encode())
        location = next((v for k, v in response.headers.items() if k.lower() == 'location'), None)
        target = urllib.parse.urlsplit(location or '')
        if target.scheme != 'https' or target.hostname != 'www.googleapis.com' or target.port not in (None, 443) or not target.path.startswith('/upload/drive/') or target.username:
            raise ValueError('Drive returned an invalid resumable-upload URL')
        result = self.request('PUT', location, headers={'Content-Type': 'application/zip', 'Content-Length': str(size)}, body=path.read_bytes())
        return json.loads(result.body)

    def download(self, file_id, *, expected_identity=None):
        metadata = self.metadata(file_id)
        props = metadata.get('appProperties', {})
        if props.get('project') != PROJECT or props.get('profile_id') != self.profile_id:
            raise ValueError('Drive file belongs to another project/profile')
        if self.config['folder_id'] not in metadata.get('parents', []):
            raise ValueError('Drive file is outside the reviewed backup folder')
        if expected_identity and props.get('setup_identity') != expected_identity:
            raise ValueError('Drive backup ledger identity differs')
        size = int(metadata.get('size', 0))
        if not 0 < size <= self.config['max_archive_bytes']:
            raise ValueError('Invalid backup size or configured archive limit exceeded')
        result = self.request('GET', '/drive/v3/files/' + urllib.parse.quote(file_id, safe='') + '?alt=media', maximum=size)
        if len(result.body) != size:
            raise ValueError('Drive download size mismatch')
        import hashlib
        if hashlib.sha256(result.body).hexdigest() != props.get('sha256'):
            raise ValueError('Drive download checksum mismatch')
        return metadata, result.body
