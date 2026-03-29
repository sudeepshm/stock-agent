FROM condaforge/mambaforge:latest

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install TA-Lib and numpy from conda-forge to avoid building the C extension from source
RUN mamba install -y -c conda-forge ta-lib numpy psycopg2 && mamba clean -afy

WORKDIR /app/backend

# Copy source
COPY . /app/backend

# Upgrade pip and wheel, then install remaining pip requirements (TA-Lib already provided by conda)
RUN python -m pip install --upgrade pip setuptools wheel

# Ensure redis-py is available for `import redis.asyncio as aioredis` in the code
RUN pip install redis==5.0.0

# Install remaining Python packages via conda-forge to avoid pip network/build issues
# This covers FastAPI, Uvicorn, SQLAlchemy, pandas, yfinance, and others.
RUN mamba install -y -c conda-forge \
	fastapi uvicorn aioredis pydantic sqlalchemy minio boto3 requests pandas yfinance \
	python-dotenv pillow python-multipart matplotlib && mamba clean -afy

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
