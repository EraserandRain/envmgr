#!/usr/bin/env zsh

# Install
function install_env() {
    local ARGS=$(getopt -o '' -l ' \
        node, \
        python, \
        cpp, \
        ubuntu_docker, \
        zsh \
    ' -- "$@")
    [[ $? != 0 ]] && echo "Parse error! Terminating..." >&2 && exit 1
    eval set -- $ARGS
    while true; do
        case "$1" in
        --node)
            $HOME/install/nvm/install_nvm.sh
            load_env --nvm
            nvm install --lts
            npm i -g npm nrm pnpm
            nrm use tencent
            shift
            ;;
        --python)
            sudo apt-get -y install python3 python3-pip
            curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash
            load_env --pyenv
            shift
            ;;
        --cpp)
            sudo apt-get -y install gcc automake autoconf libtool make build-essential gdb
            shift
            ;;
        --ubuntu_docker)
            $HOME/install/docker/install_ubuntu_docker.sh
            pip3 install docker-compose -i https://mirrors.aliyun.com/pypi/simple/
            load_env --compose
            if_wsl2 wsl2_config --fix_dockerd_failed
            shift
            ;;
        --zsh)
            sudo apt-get -y install zsh
            $HOME/install/zsh/install_omz.sh --skip-chsh
            git clone https://github.com/zsh-users/zsh-autosuggestions $HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions
            git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting
            sudo sed -i '/^$/d;/^#/d;/pam_shells.so/ s/required/sufficient/' /etc/pam.d/chsh
            chsh -s /usr/bin/zsh
            shift
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Unknown Args"
            exit 1
            ;;
        esac
    done
}

# Loading
function load_env() {
    local ARGS=$(getopt -o '' -l ' \
        compose, \
        zsh:, \
        nvm, \
        vagrant, \
        alias, \
        pyenv \
    ' -- "$@")
    [[ $? != 0 ]] && echo "Parse error! Terminating..." >&2 && exit 1
    eval set -- $ARGS
    while true; do
        case "$1" in
        --compose)
            export PATH=$PATH:$HOME/.local/bin
            shift
            ;;
        --zsh)
            export ZSH="$HOME/.oh-my-zsh"
            ZSH_THEME="lambda"
            plugins=(
                git
                zsh-autosuggestions)
            source $HOME/.oh-my-zsh/oh-my-zsh.sh
            export PROMPT="%F{cyan}[$2]%f $PROMPT"
            shift 2
            ;;
        --nvm)
            export NVM_DIR="$HOME/.nvm"
            [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"                   # This loads nvm
            [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion" # This loads nvm bash_completion
            shift
            ;;
        --vagrant)
            export VAGRANT_WSL_ENABLE_WINDOWS_ACCESS=1
            export PATH="$PATH:/mnt/d/APP/virtualbox"
            shift
            ;;
        --alias)
            alias clr="clear"
            alias gac="git add . && git commit"
            alias gst="git status"
            alias gstb="git status -sb"
            alias dps="docker ps -as"
            alias dc="docker-compose"
            alias vbm="vboxmanage"
            alias cmq="mysql -h 127.0.0.1 -uroot -pmysql57"
            shift
            ;;
        --pyenv)
            export PYENV_ROOT="$HOME/.pyenv"
            export PATH="$PYENV_ROOT/bin:$PATH"
            eval "$(pyenv init --path)"
            shift
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Unknown Args"
            exit 1
            ;;
        esac
    done
}

function set_apt_mirror() {
    sudo mv /etc/apt/sources.list /etc/apt/sources.list.bak
    sudo cp -r $HOME/install/apt/ubuntu_2204 /etc/apt/sources.list
    sudo apt-get -y update
}

function disable_needrestart() {
    sudo sed -i "/$nrconf{restart}/ s|'i'|'a'|" /etc/needrestart/needrestart.conf
    sudo sed -i "/^#.*$nrconf{restart}/s/^#//" /etc/needrestart/needrestart.conf
}

function if_jammy_os() {
    [[ "$(lsb_release -rs)" == '22.04' ]] && eval $*
}

function set_git_config() {
    cd $HOME
    git config --global core.editor vim
    git config --global init.defaultBranch main
}

# WSL2
function wsl2_config() {
    local ARGS=$(getopt -o '' -l ' \
        fix_interop, \
        startup_docker \
    ' -- "$@")
    [[ $? != 0 ]] && echo "Parse error! Terminating..." >&2 && exit 1
    eval set -- $ARGS
    while true; do
        case "$1" in
        --fix_interop)
            for i in $(pstree -np -s $$ | grep -o -E '[0-9]+'); do
                if [[ -e "/run/WSL/${i}_interop" ]]; then
                    export WSL_INTEROP=/run/WSL/${i}_interop
                fi
            done
            shift
            ;;
        --startup_docker)
            local docker_status=$(ps aux | grep dockerd | grep -v grep)
            [[ -z $docker_status ]] && sudo service docker start
            shift
            ;;
        --fix_dockerd_failed)
            sudo update-alternatives --set iptables /usr/sbin/iptables-legacy
            sudo sed '/^#.*ip_forward/s/^#//g' /etc/sysctl.conf -i
            sudo sysctl -p
            sudo service docker restart
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Unknown Args"
            exit 1
            ;;
        esac
    done
}

function if_wsl2() {
    [[ "$(uname -r)" =~ 'WSL2' ]] && eval $*
}
