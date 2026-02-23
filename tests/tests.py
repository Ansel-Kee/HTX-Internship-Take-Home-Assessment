import os
import sys
import sqlite3
import datetime
import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.append(os.getcwd())

import main

path = os.getcwd() + "/images/test/"
if os.path.isfile(os.path.join(path, "thumb_small.png")):
    os.remove(os.path.join(path, "thumb_small.png"))
if os.path.isfile(os.path.join(path, "thumb_medium.png")):
    os.remove(os.path.join(path, "thumb_medium.png"))

@pytest.fixture(scope="function")
def test_db(tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    processed_at TEXT,
                    width INTEGER,
                    height INTEGER,
                    format TEXT,
                    size INTEGER,
                    caption TEXT,
                    status TEXT,
                    error TEXT
                )"""
    )
    cursor.execute(
        """CREATE TABLE stats (
                    total INTEGER,
                    failed INTEGER,
                    totalTime REAL
                )"""
    )
    cursor.execute("INSERT INTO stats(total, failed, totalTime) VALUES (0,0,0)")
    conn.commit()
    conn.close()
    yield str(db_file)


@pytest.fixture(scope="function")
def client(test_db, monkeypatch):
    def override_get_db():
        return sqlite3.connect(test_db)

    main.app.dependency_overrides[main.get_db] = override_get_db
    monkeypatch.setattr(main, "get_db", override_get_db)

    # make sure the working directory contains an images folder for thumbnail tests
    images_root = os.path.join(os.getcwd(), "images")
    os.makedirs(images_root, exist_ok=True)

    with TestClient(main.app) as client:
        yield client


def test_generate_thumbnail():
    name = "test"
    path = os.getcwd() + "/images/test/"
    img = Image.open(os.path.join(path, f"{name}.jpg"))

    main.generate_thumbnail(img, name)
    assert os.path.isfile(os.path.join(path, "thumb_small.png"))

    small = Image.open(os.path.join(path, "thumb_small.png"))
    assert small.size == (75, 75)

    assert os.path.isfile(os.path.join(path, "thumb_medium.png"))
    medium = Image.open(os.path.join(path, "thumb_medium.png"))
    assert medium.size == (100, 100)


def test_insert_file(test_db, monkeypatch):
    # patch the helper used by insert_db so that it points at the temporary file
    monkeypatch.setattr(main, "get_db", lambda: sqlite3.connect(test_db))

    # verify helpers that do not require HTTP
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    rowid = main.insert_db("bar.png", now, 1, 1, "png", 123)
    cursor.execute("SELECT filename, status FROM images WHERE id = ?", (rowid,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "bar.png"
    assert row[1] == "processing"
    conn.close()

def test_process_file():
    # process_file should format a successful entry correctly
    success_doc = (1, "bar.png", datetime.datetime.now(), 1, 1, "png", 123, "", "success", None)
    out = main.process_file(success_doc)
    assert out["status"] == "success"
    assert out["data"]["original_name"] == "bar.png"

    fail_doc = (2, "baz.png", datetime.datetime.now(), 0, 0, "png", 0, None, "failed", "err")
    out2 = main.process_file(fail_doc)
    assert out2["status"] == "failed"

def test_successful_upload_and_stats(client, test_db):
    file_path = os.getcwd() + "/images/test/test.jpg"
    with open(file_path, "rb") as f:
        response = client.post(
            "/api/images",
            files={"file": ("test.jpg", f, "image/jpeg")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "imageID" in data

    # stats should have been incremented
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT total, failed FROM stats")
    total, failed = cur.fetchone()
    assert total == 1
    assert failed == 0
    conn.close()


def test_invalid_upload(client):
    # any non-image or wrong mime type should fail
    with open(__file__, "rb") as f:
        resp = client.post(
            "/api/images",
            files={"file": ("test.txt", f, "text/plain")},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid file format"


def test_retrieve_images_endpoints(client, test_db):
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    now = datetime.datetime.now()
    cur.execute(
        "INSERT INTO images(filename, processed_at, width, height, format, size, caption, status) VALUES (?,?,?,?,?,?,?,?)",
        ("foo.jpg", now, 10, 10, "jpeg", 100, "c", "success"),
    )
    cur.execute(
        "INSERT INTO images(filename, processed_at, width, height, format, size, caption, status) VALUES (?,?,?,?,?,?,?,?)",
        ("bar.png", now, 20, 20, "png", 200, None, "failed"),
    )
    conn.commit()
    # look up the id of the first row by filename to avoid off-by-one logic
    cur.execute("SELECT id FROM images WHERE filename = ?", ("foo.jpg",))
    rowid1 = cur.fetchone()[0]
    conn.close()

    r_all = client.get("/api/images")
    assert r_all.status_code == 200
    lst = r_all.json()
    assert any(item["data"]["original_name"] == "foo.jpg" for item in lst)

    r_one = client.get(f"/api/images/{rowid1}")
    assert r_one.status_code == 200
    assert r_one.json()["data"]["original_name"] == "foo.jpg"

    r_not = client.get("/api/images/999")
    assert r_not.status_code == 400


def test_thumbnail_endpoints(client, test_db):
    # prepare folders that the endpoint will look in
    filename = "test"
    folder = os.path.join(os.getcwd(), "images", filename)
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "thumb_small.png"), "wb").close()
    open(os.path.join(folder, "thumb_medium.png"), "wb").close()

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    now = datetime.datetime.now()
    cur.execute(
        "INSERT INTO images(filename, processed_at, width, height, format, size, caption, status) VALUES (?,?,?,?,?,?,?,?)",
        (f"{filename}.jpg", now, 1, 1, "jpeg", 1, "", "success"),
    )
    rowid = cur.lastrowid
    conn.commit()
    conn.close()

    r_sm = client.get(f"/api/images/{rowid}/thumbnails/small")
    assert r_sm.status_code == 200
    r_md = client.get(f"/api/images/{rowid}/thumbnails/medium")
    assert r_md.status_code == 200

    r_invalid = client.get(f"/api/images/{rowid}/thumbnails/large")
    assert r_invalid.status_code == 400

    r_notfound = client.get("/api/images/999/thumbnails/small")
    assert r_notfound.status_code == 400


def test_stats_endpoint(client, test_db):
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("UPDATE stats SET totalTime = ?, total = ?, failed = ?", (10, 4, 1))
    conn.commit()
    conn.close()
    r = client.get("/api/stats")
    data = r.json()
    assert data["total"] == 4
    assert data["failed"] == 1
    assert data["success_rate"] == "75.0%"
    assert data["average_processing_time_seconds"] == 2.5

    # when there are no images total should be handled gracefully
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("UPDATE stats SET totalTime = ?, total = ?, failed = ?", (0, 0, 0))
    conn.commit()
    conn.close()
    r2 = client.get("/api/stats")
    assert r2.json()["success_rate"] is None
    assert r2.json()["average_processing_time_seconds"] == 0
