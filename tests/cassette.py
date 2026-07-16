"""Cassette stile VCR per l'API Telegram: registrano richieste e risposte reali,
i test le riproducono passando dall'intero stack python-telegram-bot senza rete."""

import json
import base64
from pathlib import Path

from telegram.request import BaseRequest, HTTPXRequest


CASSETTE_DIR = Path(__file__).parent / 'cassettes'
FAKE_TOKEN = '123456:TEST-TOKEN'


def scrub_token(url: str, token: str) -> str:
  return url.replace(token, FAKE_TOKEN)


def cassette_path(name: str) -> Path:
  return CASSETTE_DIR / f'{name}.json'


class RecordingRequest(HTTPXRequest):
  def __init__(self, token: str, entries: list):
    super().__init__(connect_timeout=10, read_timeout=30, write_timeout=30)
    self._token = token
    self._entries = entries

  async def do_request(self, url, method, request_data=None, **kwargs):
    status, payload = await super().do_request(url, method, request_data=request_data, **kwargs)
    self._entries.append(
      {
        'url': scrub_token(url, self._token),
        'params': dict(request_data.parameters) if request_data else {},
        'status': status,
        'body': base64.b64encode(payload).decode(),
      }
    )
    return status, payload


class ReplayRequest(BaseRequest):
  def __init__(self, entries: list):
    self._entries = entries
    self._index = 0

  @property
  def read_timeout(self):
    return None

  async def initialize(self):
    pass

  async def shutdown(self):
    pass

  @property
  def played(self) -> int:
    return self._index

  async def do_request(self, url, method, request_data=None, **kwargs):
    assert self._index < len(self._entries), f'richiesta non prevista dalla cassetta (attese {len(self._entries)})'
    entry = self._entries[self._index]
    self._index += 1

    params = dict(request_data.parameters) if request_data else {}
    expected = entry['params']
    differences = {
      key: (params.get(key), expected.get(key))
      for key in set(params) | set(expected)
      if params.get(key) != expected.get(key)
    }
    assert url == entry['url'], f'url diverso da quello registrato: {url} != {entry["url"]}'
    assert not differences, f'parametri diversi da quelli registrati: {json.dumps(differences, ensure_ascii=False)}'
    return entry['status'], base64.b64decode(entry['body'])


def save_cassette(name: str, entries: list) -> None:
  CASSETTE_DIR.mkdir(exist_ok=True)
  cassette_path(name).write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')


def load_cassette(name: str) -> list:
  return json.loads(cassette_path(name).read_text(encoding='utf-8'))
