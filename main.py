from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from threading import Thread
from PIL import Image
import datetime, time
import os
import sqlite3
from caption import generate_caption

app = FastAPI()
db = "images.db"

def get_db():
    return sqlite3.connect(db)
        
def insert_db(filename, processed_at, width, height, format, size):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO images(filename, processed_at, width, height, format, size, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (filename, processed_at, width, height, format, size, "processing"))
    conn.commit()
    conn.close()
    return cursor.lastrowid

def generate_thumbnail(image, filename):
    SMALL_SIZE = (75, 75)
    MEDIUM_SIZE = (100, 100)
    path = os.path.join(os.getcwd(), "images", filename)

    small = image.resize(SMALL_SIZE)
    small.save(os.path.join(path, "thumb_small.png"))
    medium = image.resize(MEDIUM_SIZE)
    medium.save(os.path.join(path, "thumb_medium.png"))
    return

def process_image(image, rowid, t):
    caption = generate_caption(image)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE images SET caption = ?, status = ? WHERE id = ?",
                   (caption, "success", rowid))
    cursor.execute("UPDATE stats SET totalTime = totalTime+?",
                   (time.time()-t,))
    conn.commit()
    conn.close()
    return

@app.post("/api/images")
async def receive_image(file: UploadFile = File(...)):
    conn = get_db()
    cursor = conn.cursor()
    filetype, format = file.content_type.split("/")
    filename, extension = os.path.splitext(file.filename)
    curr = datetime.datetime.now()
    cursor.execute("UPDATE stats SET total = total+1")
    conn.commit()

    if not (filetype == "image" and format in ["jpg", "jpeg", "png"] and extension in [".jpg", ".jpeg", ".png"]):
        cursor.execute("UPDATE stats SET failed = failed+1")
        cursor.execute(
            "INSERT INTO images(filename, processed_at, status, error) VALUES (?, ?, ?, ?)",
            (file.filename, curr, "failed", "Invalid file format"))
        conn.commit()
        raise HTTPException(status_code=400, detail="Invalid file format")
    conn.close()

    image = Image.open(file.file)
    width, height = image.size
    filetype = file.content_type

    image.save(os.getcwd() + f'\\images\\{filename}\\{file.filename}')
    filesize = os.path.getsize(os.getcwd() + f'\\images\\{filename}\\{file.filename}')
    generate_thumbnail(image, filename)
    rowid = insert_db(file.filename, curr, width, height, format, filesize)

    t = Thread(target=process_image, args=(image, rowid, time.time()))
    t.start()
    
    return {"imageID": rowid}

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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM images")
    files = cursor.fetchall()
    conn.close()

    data = []
    for file in files:
        entry = process_file(file)
        data.append(entry)
    return data

@app.get("/api/images/{id}")
async def retrieve_image(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM images WHERE id = ?", (id,))
    file = cursor.fetchone()
    conn.close()

    if file is None:
        raise HTTPException(status_code=400, detail="File not found")
    data = process_file(file)
    
    return data

@app.get("/api/images/{id}/thumbnails/{size}")
async def retrieve_thumbnail(id, size):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM images WHERE id = ?", (id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=400, detail="File not found")
    
    filename = os.path.splitext(row[1])[0]
    if size.lower() not in ["small", "medium"]:
        raise HTTPException(status_code=400, detail="Invalid size")
    
    file_path = os.getcwd() + f"/images/{filename}/thumb_{size.lower()}.png"
    
    return FileResponse(path=file_path, filename=file_path, media_type='image/png')

@app.get("/api/stats")
async def retrieve_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stats")
    total, failed, totalTime = cursor.fetchone()
    if total == 0:
        success_rate = None
        average_time = 0
    else:
        success_rate = f'{round(((total-failed)/total)*100,2)}%'
        average_time = round(totalTime/total, 2)
    stats = {
        "total": total,
        "failed": failed,
        "success_rate": success_rate,
        "average_processing_time_seconds": average_time
    }
    conn.close()
    return stats
