 
FROM python:3.12-slim

 
WORKDIR /app

 
COPY pyproject.toml ./
COPY src/ src/
COPY config/ config/
COPY migrations/ migrations/
COPY alembic.ini ./

 
RUN pip install --no-cache-dir .

 
CMD ["python", "-m", "src.etl.scheduler"]