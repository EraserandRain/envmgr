#!/usr/bin/env zsh
ZSHFILE=
print_usage() {
    cat <<EOF
    
    Usage: $0 [OPTIONS]    

    OPTIONS:
        -w : update local ~/.zshrc in WSL
        -u : update local ~/.zshrc in Ubuntu-Docker
        -h : show this help and exit    

EOF
    exit 1
}

update_wsl() {
    $ZSHFILE=wsl
    cat ~/install/zsh/bak_for_zshrc/$ZSHFILE >~/.zshrc
    source ~/.zshrc
    exit 0
}

update_ubuntu() {
    $ZSHFILE=ubuntu_docker
    cat ~/install/zsh/bak_for_zshrc/$ZSHFILE >~/.zshrc
    source ~/.zshrc
    exit 0
}

# Main
while getopts "h w u" OPT
do
    case $OPT in
        h)
            print_usage
            ;;
        w)
            update_wsl
            ;;
        u)
            update_ubuntu
            ;;
    esac
done
exit 0