"""Part 4 student implementation."""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integration import process_request
from app.webex_client import WEBEX_API_BASE, WebexClient


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor if processor is not None else process_request

    def handle_event(self, event):
        """Process a Webex messages/created event."""
        if not isinstance(event, dict):
            return None

        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        event_data = event.get("data")
        if not isinstance(event_data, dict):
            return None

        # Ignore messages from the bot itself before API call
        if event_data.get("personId") == self.bot_person_id:
            return None

        message_id = event_data.get("id")
        if not message_id:
            return None

        message = self.client.get_message(message_id)
        if not isinstance(message, dict):
            return None

        # Check author of fetched message to prevent reply loops
        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        mentioned_people = message.get("mentionedPeople") or []
        files = message.get("files") or []

        if len(files) > 1:
            result = {"status": "error", "result": "multiple_attachments"}
            if room_id:
                self.client.send_message(room_id, json.dumps(result))
            return result

        if len(files) == 0:
            result = self.processor(
                mentioned_people,
                None,
                self.bot_person_id,
            )
            if room_id:
                self.client.send_message(room_id, json.dumps(result))
            return result

        # Exactly 1 attachment
        file_url = files[0]
        content = self.client.download_file(file_url)

        with TemporaryDirectory() as tmp_dir:
            temp_path = Path(tmp_dir) / "request.yaml"
            if isinstance(content, str):
                temp_path.write_text(content, encoding="utf-8")
            else:
                temp_path.write_bytes(content)

            result = self.processor(
                mentioned_people,
                temp_path,
                self.bot_person_id,
            )

        if room_id:
            self.client.send_message(room_id, json.dumps(result))
        return result


def make_http_handler(submit_event):
    """Create an HTTP request handler class that forwards valid events to submit_event."""
    class WebhookHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code, data):
            payload = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"status": "ok", "result": "healthy"})
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/webhook":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                except (ValueError, TypeError):
                    content_length = 0

                if content_length < 1 or content_length > 1_000_000:
                    self._send_json(400, {"status": "error", "result": "invalid_event"})
                    return

                try:
                    body = self.rfile.read(content_length)
                    data = json.loads(body.decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError("Body must be a JSON object")
                except Exception:
                    self._send_json(400, {"status": "error", "result": "invalid_event"})
                    return

                submit_event(data)
                self._send_json(200, {"status": "ok", "result": "accepted"})
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    return WebhookHandler


def main():
    """Start the webhook HTTP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", 8000))
    token = os.environ.get("WEBEX_BOT_TOKEN")

    client = None
    bot_person_id = os.environ.get("BOT_PERSON_ID")

    if token:
        try:
            client = WebexClient(token=token)
            if not bot_person_id:
                resp = client.session.get(
                    f"{WEBEX_API_BASE}/people/me",
                    headers=client.headers,
                    timeout=10,
                )
                resp.raise_for_status()
                bot_person_id = resp.json().get("id")
        except Exception as e:
            logging.warning("Could not initialize Webex client: %s", e)

    handler = (
        WebexEventHandler(client, bot_person_id)
        if client and bot_person_id
        else None
    )

    executor = ThreadPoolExecutor(max_workers=1)

    def submit_event(event_data):
        if handler:
            executor.submit(handler.handle_event, event_data)
        else:
            logging.warning("Event submitted but WebexEventHandler is not ready")

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    logging.info("Serving webhook on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        executor.shutdown(wait=False)


if __name__ == "__main__":
    main()
