# Autopilot runtime for the directing-stickman-videos Skill (Node 20 + FFmpeg + canvas).
# Optional: openai-whisper (CPU) for scripts/align_captions.py word alignment.
FROM node:20-bookworm-slim

ARG WITH_WHISPER=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*

RUN if [ "$WITH_WHISPER" = "1" ]; then \
      pip3 install --no-cache-dir --break-system-packages \
        --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
        torch openai-whisper ; \
    fi

WORKDIR /opt/skill
COPY skills/directing-stickman-videos/package.json skills/directing-stickman-videos/package-lock.json ./
RUN npm ci --omit=dev
COPY skills/directing-stickman-videos/ ./

ENV NODE_ENV=production
# Projects must live outside the Skill (autopilot init refuses paths under /opt/skill).
WORKDIR /work
CMD ["node", "/opt/skill/scripts/autopilot.mjs", "doctor"]
