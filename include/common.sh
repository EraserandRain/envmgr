#!/usr/bin/env zsh
function set_device() {
    return $1
}

function load_path() {
    export PATH=$PATH:$HOME/.local/bin
}

function load_zsh() {
    export ZSH="$HOME/.oh-my-zsh"
    ZSH_THEME="lambda"
    plugins=(
        git
        zsh-autosuggestions)
}

function load_nvm() {
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
}

function load_alias(){
    alias clr="clear"
    alias gac="git add . && git commit"
    alias gst="git status"
    alias dps="docker ps -as"
    alias dc="docker-compose"
}

function reload_zsh(){
    source ~/.oh-my-zsh/oh-my-zsh.sh
    export PROMPT="%F{cyan}[$1]%f $PROMPT"
}

function fix_wsl2_interop() {
    for i in $(pstree -np -s $$ | grep -o -E '[0-9]+'); do
        if [[ -e "/run/WSL/${i}_interop" ]]; then
            export WSL_INTEROP=/run/WSL/${i}_interop
        fi
    done
}

function install_python3_env() {
    sudo apt-get -y install python3 python3-pip
}

function install_cpp_env() {
    sudo apt-get -y install gcc automake autoconf libtool make build-essential gdb
}

function install_node_env() {
    sudo ~/install/nvm/install-nvm.sh
    load_nvm
    nvm install --lts 
    npm i -g npm nrm pnpm
    nrm use tencent 
}

function install_ubuntu_docker() {
    ~/install/docker/install_ubuntu_docker.sh
}


function install_docker_compose() {
    install_python3_env
    pip3 install docker-compose -i https://mirrors.aliyun.com/pypi/simple/
    load_path
}

function install_zsh() {
    sudo apt-get -y install zsh 
    ~/install/zsh/install_omz.sh --skip-chsh
    sudo chsh -s /usr/bin/zsh
    git clone https://github.com/zsh-users/zsh-autosuggestions ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions
    git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting 
}