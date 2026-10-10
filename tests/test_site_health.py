"""Public sharing metadata and navigation work without a mission session."""

import os
import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

os.environ["GAME_MODE"] = "demo"
os.environ["MASTER_SECRET"] = "verification-master-secret-with-at-least-32-characters"

from fastapi.testclient import TestClient

import app
from security import AbuseLedger


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.links = []
        self.downloads = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[attrs.get("property") or attrs.get("name")] = attrs.get("content")
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag == "button" and "data-download" in attrs:
            self.downloads.append(attrs)


class SiteHealthTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        ledger = patch.object(app, "ledger", AbuseLedger(Path(directory.name) / "ledger.sqlite3"))
        ledger.start()
        self.addCleanup(ledger.stop)
        self.client = TestClient(app.app, base_url="https://game.test")
        self.addCleanup(self.client.close)

    def test_anonymous_pages_include_complete_cards_and_public_image(self):
        for origins in ((), ("https://public.test",)):
            with patch.object(app, "settings", replace(app.settings, public_origins=origins)):
                origin = origins[0] if origins else "https://game.test"
                for route in ("/", "/guide", "/demo"):
                    with self.subTest(origins=origins, route=route):
                        response = self.client.get(route)
                        self.assertEqual(response.status_code, 200)
                        self.assertNotIn("__PUBLIC_ORIGIN__", response.text)
                        meta = PageParser(response.text).meta
                        self.assertEqual(meta["og:url"], origin + route)
                        self.assertEqual(meta["twitter:card"], "summary_large_image")
                        self.assertEqual(meta["og:title"], meta["twitter:title"])
                        self.assertTrue(meta["og:title"])
                        self.assertEqual(meta["og:description"], meta["description"])
                        self.assertEqual(meta["og:description"], meta["twitter:description"])
                        self.assertEqual(meta["og:image"], meta["twitter:image"])
                        self.assertTrue(meta["og:image"].startswith(origin + "/"))
                        image = self.client.get(urlsplit(meta["og:image"]).path)
                        self.assertEqual(image.status_code, 200)
                        self.assertEqual(image.headers["content-type"], "image/jpeg")
                        self.assertTrue(image.content.startswith(b"\xff\xd8"))

    def test_anonymous_navigation_has_no_protected_download_links(self):
        for route in ("/", "/guide", "/demo"):
            page = PageParser(self.client.get(route).text)
            for href in page.links:
                if href.startswith("/"):
                    self.assertEqual(self.client.get(href).status_code, 200, href)
            if route == "/":
                self.assertEqual(len(page.downloads), 4)
                self.assertEqual(
                    {button["data-download"] for button in page.downloads},
                    {"/api/export", "/api/certificate"},
                )
                self.assertTrue(all(button["type"] == "button" for button in page.downloads))
        for route in ("/api/export", "/api/certificate"):
            self.assertEqual(self.client.get(route).status_code, 401)


if __name__ == "__main__":
    unittest.main()
