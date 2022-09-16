#!/usr/bin/env zsh
function setDevice() {
    return $1
}

function loadPath() {
    export PATH=$PATH:$HOME/.local/bin
}

function loadZsh() {
    export ZSH="$HOME/.oh-my-zsh"
    ZSH_THEME="lambda"
    plugins=(
        git
        zsh-autosuggestions)
}

function loadNvm() {
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
}

function loadAlias(){
    alias clr="clear"
    alias gac="git add . && git commit"
    alias gst="git status"
    alias dps="docker ps -as"
    alias dc="docker-compose"
}

function reload(){
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
