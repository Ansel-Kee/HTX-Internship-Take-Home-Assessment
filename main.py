from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from threading import Thread
from PIL import Image
import datetime
import os
import sqlite3
from caption import generate_caption

# filename to form database
file = "images.db"
conn = sqlite3.connect(file)
cursor = conn.cursor()
app = FastAPI()

# creating a object 
def generate_thumbnail(image, curr, filename, extension):
    SMALL_SIZE = (75, 75)
    MEDIUM_SIZE = (100, 100)
    path = f"\images\\{filename}\\"

    image.thumbnail(SMALL_SIZE)
    image.save(path + 'thumb_small.png')
    image.thumbnail(MEDIUM_SIZE)
    image.save(path + 'thumb_medium.png')
    return

def insert_db(filename, processed_at, width, height, format, size):
    data = (filename, processed_at, width, height, format, size, "processing")
    cursor.execute("INSERT INTO images(filename, processed_at, width, height, format, size, status) VALUES (?, ?, ?, ?, ?, ?, ?)", data )
    conn.commit()
    return cursor.lastrowid

def process_image(image, rowid):
    caption = generate_caption(image)
    cursor.execute("UPDATE images SET caption = ?, status = ? WHERE id = ?", (caption, "complete", rowid))
    conn.commit()
    return

@app.post("/api/images")
async def receive_image(file: UploadFile = File(...)):
    filetype, format = file.content_type.split("/")
    if filetype != "image":
        return

    filename, extension = os.path.splitext(file.filename)
    image = Image.open(file.file)

    curr = datetime.now()
    width, height = image.size
    filetype = file.content_type
    image.save(f'\images\\{filename}\\{file.filename}')
    size = os.path.getsize(f'\images\\{filename}\\{file.filename}')
    generate_thumbnail(image, curr, filename, extension)
    rowid = insert_db(file.filename, curr, width, height, format, size)

    t = Thread(target=process_image, args=(image, rowid))
    t.start()
    return image

@app.get("/api/images")
async def retrieve_images():
    return

@app.get("/api/images/{id}/thumbnails/{size}")
async def retrieve_thumbnail():
    return
@app.get("/api/stats")
async def retrieve_stats():
    successRate = ""
    avgTime = ""
    stats = {
        "SuccessRate": successRate,
        "AverageTime": avgTime
        }
    return stats