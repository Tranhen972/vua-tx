FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# RUN apt-get update && apt-get install -y gcc

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# IMPORTANT: Admin Panel Templates
COPY templates/ templates/

# Grant permissions
RUN chown -R 1000:1000 /app && chmod -R 777 /app

USER root
# RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

EXPOSE 7860

CMD ["python", "-u", "main.py"]
