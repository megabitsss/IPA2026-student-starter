"""Part 4 student implementation."""

import os
import requests

WEBEX_API_BASE = 'https://webexapis.com/v1'


class WebexClient:
    def __init__(self, token=None, session=None):
        if token is None:
            token = os.environ.get("WEBEX_BOT_TOKEN")
        if not token:
            raise PermissionError("Webex bot token is required")
        self.token = token
        self.session = session if session is not None else requests.Session()

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
        }

    def get_message(self, message_id):
        url = f"{WEBEX_API_BASE}/messages/{message_id}"
        resp = self.session.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def download_file(self, file_url):
        resp = self.session.get(file_url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.content

    def send_message(self, room_id, text):
        url = f"{WEBEX_API_BASE}/messages"
        payload = {"roomId": room_id, "text": text}
        resp = self.session.post(url, headers=self.headers, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
