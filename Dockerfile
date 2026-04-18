FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apex_btc_agent.py .

# State file lives in /data so it persists across container rebuilds
ENV STATE_FILE=/data/btc_agent_state.json
RUN mkdir -p /data
VOLUME ["/data"]

# Non-root user
RUN useradd -m apex && chown -R apex:apex /app /data
USER apex

CMD ["python", "-u", "apex_btc_agent.py"]
