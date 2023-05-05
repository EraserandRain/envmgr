#!/usr/bin/env zsh
source $HOME/env-manager/Manifest
# Install
function install_env() {
    local ARGS=$(getopt -o '' -l ' \
        node, \
        python, \
        cpp, \
        golang, \
        ruby, \
        docker, \
        zsh, \
        ssh, \
        k8s \
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
        --ruby)
            source ${ENV_INSTALL}/ruby/main
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
        --k8s)
            source ${ENV_INSTALL}/k8s/main
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
        docker, \
        zsh:, \
        node, \
        golang, \
        ruby, \
        python, \
        vagrant, \
        alias, \
        git, \
        vim, \
        ssh, \
        proxy, \
        k8s \
    ' -- "$@")
    [[ $? != 0 ]] && echo "Parse error! Terminating..." >&2 && exit 1
    eval set -- $ARGS
    while true; do
        case "$1" in
        --docker)
            source ${ENV_LOAD}/docker/main
            shift
            ;;
        --zsh)
            source ${ENV_LOAD}/zsh/main
            shift 2
            ;;
        --node)
            source ${ENV_LOAD}/node/main
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
        --python)
            source ${ENV_LOAD}/python/main
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
        --golang)
            source ${ENV_LOAD}/golang/main
            shift
            ;;
        --ruby)
            source ${ENV_LOAD}/ruby/main
            shift
            ;;
        --ssh)
            source ${ENV_LOAD}/ssh/main
            shift
            ;;
        --proxy)
            source ${ENV_LOAD}/proxy/main
            shift
            ;;
        --k8s)
            source ${ENV_LOAD}/k8s/main
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
    local needrestart_config="/etc/needrestart/needrestart.conf"
    [[ -e $needrestart_config ]] && {
        sudo sed -i "/$nrconf{restart}/ s|'i'|'a'|" $needrestart_config
        sudo sed -i "/^#.*$nrconf{restart}/s/^#//" $needrestart_config
    }
}

function if_bionic_os() {
    [[ "$(lsb_release -rs)" == '18.04' ]] && eval $*
}

function if_jammy_os() {
    [[ "$(lsb_release -rs)" == '22.04' ]] && eval $*
}

# WSL2

function if_wsl2() {
    [[ "$(uname -r)" =~ 'WSL2' ]] && eval $*
}

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

function is_cmd_exist() {
    [[ -z $1 ]] && echo "Usage: is_cmd_exist [command1] [command2] ..." && return 1
    for cmd in "$@"; do
        if [[ $cmd == ${!#} ]]; then
            command -V $cmd >/dev/null
            return $?
        else
            command -V $cmd >/dev/null && continue || return $?
        fi
    done
}
