#!/usr/bin/env bash

PYTHON_DEFAULT="3.10.4"

# Install pyenv
curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"

cat >> $HOME/.bashrc <<EOF
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
EOF

# Install python3 (default 3.10.4) and pip3
sudo apt update
sudo apt install -y build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev curl \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
wget https://npm.taobao.org/mirrors/python/${PYTHON_DEFAULT}/Python-${PYTHON_DEFAULT}.tar.xz -P ~/.pyenv/cache
pyenv install ${PYTHON_DEFAULT}
pyenv global ${PYTHON_DEFAULT}
pip3 install --upgrade pip

# Install Ansible
pip3 install ansible ansible-lint

# Checkout Repo env-manager
git clone https://github.com/EraserandRain/env-manager
