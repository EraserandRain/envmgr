#!/usr/bin/env zsh

source PROJECT_ENV
# Install
function install_env() {
    local ARGS=$(getopt -o '' -l ' \
        node, \
        python, \
        cpp, \
        golang, \
        docker, \
        zsh, \
        ssh \
    ' -- "$@")
    [[ $? != 0 ]] && echo "Parse error! Terminating..." >&2 && exit 1
    eval set -- $ARGS
    while true; do
        case "$1" in
        --node)
            source ${ENV_INSTALL}/node/main
            shift
            ;;
        --python)
            source ${ENV_INSTALL}/python/main
            shift
            ;;
        --cpp)
            source ${ENV_INSTALL}/cpp/main
            shift
            ;;
        --golang)
            source ${ENV_INSTALL}/golang/main
            shift
            ;;
        --docker)
            source ${ENV_INSTALL}/docker/main
            shift
            ;;
        --zsh)
            source ${ENV_INSTALL}/zsh/main
            shift
            ;;
        --ssh)
            source ${ENV_INSTALL}/ssh/main
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
        pyenv, \
        apt, \
        git, \
        vim, \
        ssh \
    ' -- "$@")
    [[ $? != 0 ]] && echo "Parse error! Terminating..." >&2 && exit 1
    eval set -- $ARGS
    while true; do
        case "$1" in
        --compose)
            source ${ENV_LOAD}/compose/main
            shift
            ;;
        --zsh)
            source ${ENV_LOAD}/zsh/main
            shift 2
            ;;
        --nvm)
            source ${ENV_LOAD}/nvm/main
            shift
            ;;
        --vagrant)
            source ${ENV_LOAD}/vagrant/main
            shift 
            ;;
        --alias)
            source ${ENV_LOAD}/alias/main
            shift
            ;;
        --pyenv)
            source ${ENV_LOAD}/pyenv/main
            shift
            ;;
        --apt)
            source ${ENV_LOAD}/apt/main
            shift
            ;;
        --git)
            source ${ENV_LOAD}/git/main
            shift
            ;;
        --vim)
            source ${ENV_LOAD}/vim/main
            shift
            ;;
        --ssh)
            source ${ENV_LOAD}/ssh/main
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

function disable_needrestart() {
    sudo sed -i "/$nrconf{restart}/ s|'i'|'a'|" /etc/needrestart/needrestart.conf
    sudo sed -i "/^#.*$nrconf{restart}/s/^#//" /etc/needrestart/needrestart.conf
}

function if_jammy_os() {
    [[ "$(lsb_release -rs)" == '22.04' ]] && eval $*
}

# WSL2
function wsl2_config() {
    local ARGS=$(getopt -o '' -l ' \
        fix_interop, \
        startup_docker, \
        fix_dockerd_failed \
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
            sudo apt-get install -y iptables arptables ebtables
            sudo update-alternatives --set iptables /usr/sbin/iptables-legacy
            sudo sed '/^#.*ip_forward/s/^#//g' /etc/sysctl.conf -i
            sudo sysctl -p
            sudo service docker restart
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

function if_wsl2() {
    [[ "$(uname -r)" =~ 'WSL2' ]] && eval $*
}
