# HuggingFace Space (Docker SDK) for the apartment-agent dashboard.
# Installs the agent straight from the public GitHub repo and serves the FastAPI app (backend +
# static frontend) on the HF port 7860. Secrets (SUPABASE_*, LLM keys, etc.) come from the Space's
# "Variables and secrets" settings as environment variables.
FROM python:3.12-slim

# git is needed to pip-install from the GitHub repo
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces require the container to run as a non-root user (uid 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# Pin to a ref (branch/tag/sha). Bump or "Factory rebuild" the Space to pull newer code.
ARG AGENT_REF=main
RUN pip install --no-cache-dir --user \
    "munich-apartment-agent[web] @ git+https://github.com/AliAlpOezer/munich-apartment-agent.git@${AGENT_REF}"

# Runtime data in writable, ephemeral locations (free Spaces have no persistent disk)
ENV CHECKPOINT_DB=/home/user/app/agent_state.sqlite \
    WIKI_DIR=/home/user/app/wiki

EXPOSE 7860
CMD ["python", "-m", "apartment_agent.web", "--host", "0.0.0.0", "--port", "7860"]
