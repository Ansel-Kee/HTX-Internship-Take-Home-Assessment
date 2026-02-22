from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from threading import Thread
from PIL import Image
import datetime
import os
import sqlite3
import time
from caption import generate_caption
# filename to form database
file = "images.db"
conn = sqlite3.connect(file)
cursor = conn.cursor()
app = FastAPI()

# creating a object
cursor.execute("SELECT * FROM stats")
total, failed, totalTime = cursor.fetchone()


def generate_thumbnail(image, filename):
    SMALL_SIZE = (75, 75)
    MEDIUM_SIZE = (100, 100)
    path = os.getcwd() + f"\images\\{filename}\\"

    image.thumbnail(SMALL_SIZE)
    image.save(path + 'thumb_small.png')
    image.thumbnail(MEDIUM_SIZE)
    image.save(path + 'thumb_medium.png')
    return

def insert_db(filename, processed_at, width, height, format, size):
    cursor.execute(
        "INSERT INTO images(filename, processed_at, width, height, format, size, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (filename, processed_at, width, height, format, size, "processing"))
    conn.commit()
    return cursor.lastrowid


def process_image(image, rowid, t):
    caption = generate_caption(image)
    cursor.execute("UPDATE images SET caption = ?, status = ? WHERE id = ?",
                   (caption, "success", rowid))
    cursor.execute("UPDATE stats SET totalTime = totalTime+?",
                   (time.time()-t,))
    conn.commit()
    return


@app.post("/api/images")
async def receive_image(file: UploadFile = File(...)):
    filetype, format = file.content_type.split("/")
    filename, extension = os.path.splitext(file.filename)
    curr = datetime.now()
    cursor.execute("UPDATE stats SET total = total+1")

    if filetype != "image":
        cursor.execute("UPDATE stats SET failed = failed+1")
        cursor.execute(
            "INSERT INTO images(filename, processed_at, status, error) VALUES (?, ?, ?)",
            (file.filename, curr, "failed", "Invalid file format"))
        conn.commit()
        raise HTTPException(status_code=400, detail="Invalid file format")

    image = Image.open(file.file)
    width, height = image.size
    filetype = file.content_type
    image.save(f'\images\\{filename}\\{file.filename}')
    size = os.path.getsize(f'\images\\{filename}\\{file.filename}')
    generate_thumbnail(image, filename)
    rowid = insert_db(file.filename, curr, width, height, format, size)

    t = Thread(target=process_image, args=(image, rowid, time.time()))
    t.start()
    conn.commit()
    return image


def process_file(file):
    id, filename, processed_at, width, height, format, size, caption, status, error = file
    if status == "success":
        entry = {
            "status": status,
            "data": {
                "image_id": id,
                "original_name": filename,
                "processed_at": processed_at,
                "metadata": {
                    "width": width,
                    "height": height,
                    "format": format,
                    "caption": caption,
                    "size_bytes": size
                },
                "thumbnails": {
                    "small": f"http://localhost:8000/api/images/{filename}/thumbnails/small",
                    "medium": f"http://localhost:8000/api/images/{filename}/thumbnails/medium"
                }
            },
            "error": "null"
        }
    else:
        entry = {
            "status": "failed",
            "data": {
                "image_id": id,
                "original_name": filename,
                "processed_at": processed_at,
                "metadata": {},
                "thumbnails": {}
            },
            "error": "invalid file format"
        }
    return entry

@app.get("/api/images")
async def retrieve_images():
    cursor.execute("SELECT * FROM images")
    files = cursor.fetchall()
    data = []
    for file in files:
        
        entry = process_file(file)
        data.append(entry)
    return data


@app.get("/api/images/{id}")
async def retrieve_images(id):
    cursor.execute("SELECT * FROM images WHERE id = ?", (id,))
    file = cursor.fetchone()
    if file is None:
        raise HTTPException(status_code=400, detail="File not found")
    data = process_file(file)
    return data


@app.get("/api/images/{id}/thumbnails/{size}")
async def retrieve_thumbnail(id, size):
    cursor.execute("SELECT * FROM images WHERE id = ?", (id,))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="File not found")
    filename = row[1]
    if size.lower() not in ["small", "medium"]:
        raise HTTPException(status_code=400, detail="Invalid size")
    file_path = f"/images/{filename}/thumb_{size.lower()}"
    return FileResponse(path=file_path, filename=file_path, media_type='image/png')


@app.get("/api/stats")
async def retrieve_stats():
    stats = {
        "total": total,
        "failed": failed,
        "success_rate": f"{round(((total-failed)/total)*100,2)}%",
        "average_processing_time_seconds": round(totalTime/total, 2)
    }
    return stats
