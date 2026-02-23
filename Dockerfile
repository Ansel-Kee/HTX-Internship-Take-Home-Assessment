FROM python:3.9
ADD main.py .
RUN pip install -r requirements.txt
WORKDIR /
COPY . .
EXPOSE 8000
CMD ["fastapi", "dev", "main.py"]