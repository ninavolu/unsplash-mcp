FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies first for better layer caching.
# (We install deps directly rather than building the project as a wheel,
# which avoids build-backend assumptions about the source layout.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# FastMCP serves Streamable HTTP at /mcp on $PORT (default 8000).
EXPOSE 8000

CMD ["python", "server.py"]
