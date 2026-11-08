# The places MCP server over stdio, serving release 2: docker run -i pgl
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY data/sources ./data/sources
COPY data/landmarks.json ./data/landmarks.json
COPY models ./models
RUN pip install --no-cache-dir .
ENTRYPOINT ["python", "-m", "pgl.servers.places"]
