FROM python:3.10-slim

# Purana ffmpeg aur naya p7zip-full dono install kiye gaye hain
RUN apt-get update && apt-get install -y \
    ffmpeg \
    p7zip-full \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# Sabhi requirements install karne ke liye
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
