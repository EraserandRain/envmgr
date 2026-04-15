FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        openssh-server \
        procps \
        python3 \
        python3-apt \
        sudo \
        zsh \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash envmgr \
    && echo 'envmgr ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/envmgr \
    && chmod 0440 /etc/sudoers.d/envmgr \
    && install -d -m 0755 /var/run/sshd \
    && install -d -m 0700 -o envmgr -g envmgr /home/envmgr/.ssh

COPY entrypoint.sh /usr/local/bin/e2e-ssh-entrypoint
RUN chmod +x /usr/local/bin/e2e-ssh-entrypoint

HEALTHCHECK CMD pgrep -x sshd >/dev/null || exit 1

EXPOSE 22
CMD ["/usr/local/bin/e2e-ssh-entrypoint"]
