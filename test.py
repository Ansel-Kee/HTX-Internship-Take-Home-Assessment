import main
from PIL import Image
import os

def test_thumbnails():
    cwd = os.getcwd()
    image = Image.open(cwd+"\\images\\ntu\\ntu.jpg")
    main.generate_thumbnail(image, "ntu")
    assert os.path.isfile(cwd+"\\images\\ntu\\thumb_small.png") and os.path.isfile(cwd+"\\images\\ntu\\thumb_medium.png")