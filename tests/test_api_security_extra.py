import hashlib
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from chuma_ip_factory import CHUMA
from chuma_ip_factory.api import API
from chuma_ip_factory.video_combain import VideoCombain


def _server(factory, token="secret", video=None):
    previous = (API.factory, API.admin_token, getattr(API, "video_combain", None))
    API.factory, API.admin_token, API.video_combain = factory, token, video or VideoCombain(factory)
    server = HTTPServer(("127.0.0.1", 0), API)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, previous


def _restore(server, previous):
    server.shutdown()
    server.server_close()
    API.factory, API.admin_token, API.video_combain = previous


def test_artifact_download_rejects_symlink_escape():
    d = tempfile.TemporaryDirectory()
    root = Path(d.name) / "media"
    root.mkdir(parents=True, exist_ok=True)
    outside = Path(d.name) / "outside.bin"
    outside.write_bytes(b"secret-outside")
    link = root / "link.bin"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        d.cleanup()
        return

    factory = CHUMA(Path(d.name) / "db.sqlite", root)
    owner = factory.owner()
    cid = factory.create_character(owner, "Symlink Guard")
    aid = "ART-SYMLINK"
    factory.store.db.execute(
        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            aid, owner, cid, None, None, "test", "application/octet-stream",
            str(link), hashlib.sha256(outside.read_bytes()).hexdigest(),
            "test", "READY", int(__import__("time").time()),
        ),
    )
    factory.store.commit()
    server, previous = _server(factory)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/artifacts/{aid}",
            headers={"Authorization": "Bearer secret", "X-Owner-ID": owner},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "symlink escape was served"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            assert json.loads(exc.read().decode())["error"] == "forbidden"
    finally:
        _restore(server, previous)
        factory.store.close()
        d.cleanup()


def test_artifact_download_requires_owner_header_even_for_valid_artifact():
    d = tempfile.TemporaryDirectory()
    root = Path(d.name) / "media"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "valid.bin"
    path.write_bytes(b"private")
    factory = CHUMA(Path(d.name) / "db.sqlite", root)
    owner = factory.owner()
    cid = factory.create_character(owner, "Owner Header")
    aid = "ART-NO-OWNER"
    factory.store.db.execute(
        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            aid, owner, cid, None, None, "test", "application/octet-stream",
            str(path), hashlib.sha256(b"private").hexdigest(),
            "test", "READY", int(__import__("time").time()),
        ),
    )
    factory.store.commit()
    server, previous = _server(factory)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/artifacts/{aid}",
            headers={"Authorization": "Bearer secret"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "artifact was served without owner scope"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            assert json.loads(exc.read().decode())["error"] == "owner_forbidden"
    finally:
        _restore(server, previous)
        factory.store.close()
        d.cleanup()
