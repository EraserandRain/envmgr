#!/usr/bin/env zsh
SCRIPTFILE=$0
ZSHFILE=
print_usage() {
    cat <<EOF
    
    Usage: $SCRIPTFILE [OPTIONS]    

    OPTIONS:
        -w : update local ~/.zshrc in WSL
        -d : update local ~/.zshrc in Docker
        -r : update local ~/.zshrc in Remote Server
        -h : show this help and exit    

EOF
    exit 1
}

update_local_zsh() {
    cat ~/install/zsh/bak_for_zshrc/$ZSHFILE > ~/.zshrc
    source ~/.zshrc
    exit 0
}

# Main
while getopts "h w d r" OPT
do
    case $OPT in
        h)
            print_usage
            ;;
        w)
            ZSHFILE=wsl
            update_local_zsh
            ;;
        d)
            ZSHFILE=Docker
            update_local_zsh
            ;;
        r)
            ZSHFILE=Remote
            update_local_zsh
            ;;
        *)
            print_usage
            ;;
    esac
done
exit 0
