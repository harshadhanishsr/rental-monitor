FROM python:3.11-slim

WORKDIR /app

# Install Chromium system dependencies manually (--with-deps fails on Debian trixie
# due to renamed font packages: ttf-unifont→fonts-unifont, ttf-ubuntu-font-family removed)
RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 fonts-unifont \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

RUN mkdir -p /app/data

CMD ["python", "-u", "main.py"]
