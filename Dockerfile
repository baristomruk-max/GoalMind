FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set up user and working directory (required for HF Spaces)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Install Python requirements
COPY --chown=user requirements.txt /app/
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application files (with correct permissions)
COPY --chown=user . /app/

# Hugging Face Spaces expose port 7860
ENV PORT=7860
EXPOSE 7860

# Define start command to use gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app", "--workers", "1", "--threads", "4", "--timeout", "120"]
