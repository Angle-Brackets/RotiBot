FROM python:3.12-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .

# Copy any other necessary files (adjust based on your bot structure)
COPY . .

# Start the bot
CMD ["python3", "main.py", "--music", "--show-cog-load"]