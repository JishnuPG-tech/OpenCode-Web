FROM debian:bookworm-slim

ARG OPENCODE_VERSION=1.18.3

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Download opencode binary
RUN curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" \
    | tar -xz -C /usr/local/bin opencode

# Create non-root user
RUN useradd -m -s /bin/bash opencode

# Working directory for projects
RUN mkdir -p /projects && chown opencode:opencode /projects

USER opencode
WORKDIR /projects

EXPOSE 4096

# Default: pre-create default project, init git (OpenCode requires git repo to recognize projects), and serve
CMD ["sh", "-c", "mkdir -p /projects/default && cd /projects/default && if [ ! -d .git ]; then git init && git config user.email 'opencode@local.com' && git config user.name 'OpenCode' && git commit --allow-empty -m 'Initial commit'; fi; exec opencode serve --port 4096 --hostname 0.0.0.0"]
