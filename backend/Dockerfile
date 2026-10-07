FROM python:3.11-slim

# Cài đặt các thư viện hệ thống cần thiết cho OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy thư viện và cài đặt
COPY requirements.txt requirements_bot.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements_bot.txt
RUN pip install pillow-heif

# Copy toàn bộ mã nguồn
COPY . .

# Tạo thư mục tạm
RUN mkdir -p uploads temp

# Chạy bot Telegram
CMD ["python", "bot.py"]
