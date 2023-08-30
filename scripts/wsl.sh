#!/bin/bash

function info(){
    echo -e "\e[32m[Info]\e[0m: $1"
}

function warn(){
    echo -e "\e[33m[Warning]\e[0m: $1"
}

function err(){
    echo "[Error]: $1"
}

function check_python_version() {
    local python_version=$(python3 -V | awk '{print $2}')
    local major_version=$(python3 -V 2>&1 | awk '{split($2, version, "."); print version[1]}')
    local minor_version=$(python3 -V 2>&1 | awk '{split($2, version, "."); print version[2]}')
    # Check if Python version is less than 3.6
    if [[ $major_version -lt 3 || ($major_version -eq 3 && $minor_version -lt 6) ]]; then
        err "Python version is less than 3.6. Required Python 3.6 or higher."
        exit 1
    fi
    # Continue executing other script logic
    info "Python version ${python_version} is acceptable. Continue with the script."
}

function check_path() {
    local bashrc_path="${HOME}/.bashrc"
    local check_path_rc=$(echo $PATH | tr ':' '\n' | grep "$HOME/.local/bin")
    local check_profile_rc=$(grep "export PATH=\$PATH:\$HOME/.local/bin" "$bashrc_path")

    if [[ -z $check_path_rc ]]; then
        warn "$HOME/.local/bin is not in PATH"
        if [[ -z $check_profile_rc ]]; then
            echo 'export PATH=$PATH:$HOME/.local/bin' >> "$bashrc_path"
            info "Success to Add the path to $bashrc_path"
        else
            warn "The export PATH already exists in $bashrc_path, please reload the terminal"
        fi
    else
        info "$HOME/.local/bin is in PATH"
    fi
}

function installation() {
    sudo apt -y update
    sudo apt -y upgrade
    sudo apt -y install make python3-pip

    # Check if $HOME/.local/bin is already in $PATH
    check_path

    pip3 install ansible ansible-lint
    ansible-galaxy collection install community.general
    ansible-galaxy install gantsign.oh-my-zsh rvm.ruby
    info "Success to install dependencies!"
}

# Main
check_python_version
installation
