FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
# Mount a volume at /data to keep the SQLite DB across deploys
ENV DB_URL=sqlite+aiosqlite:////data/salebot.db
VOLUME /data
CMD ["python", "-m", "salebot.main"]
