FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY interface/ interface/
COPY ontology/ ontology/
COPY reports/ reports/
COPY scripts/ scripts/

# Flask listens on 5050
EXPOSE 5050

# Bind to 0.0.0.0 so Docker can route traffic in
CMD ["python", "src/api.py", "--host", "0.0.0.0", "--port", "5050"]
