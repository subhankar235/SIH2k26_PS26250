FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY streaming ./streaming
COPY ml ./ml
COPY optimisation ./optimisation
COPY simulation ./simulation
COPY evaluation ./evaluation
COPY data ./data
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
