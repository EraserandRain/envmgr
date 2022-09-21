#!/usr/bin/env zsh
SCRIPTFILE=$0
ZSHFILE=
print_usage() {
    cat <<EOF
    
    Usage: $SCRIPTFILE [OPTIONS]    

    OPTIONS:
        -w : update local ~/.zshrc in WSL
        -d : update local ~/.zshrc in Docker
        -c : update local ~/.zshrc in Common
        -h : show this help and exit    

EOF
    exit 1
}

update_local_zsh() {
    cat ~/install/zsh/settings/$ZSHFILE > ~/.zshrc
    source ~/.zshrc
}

# Main
while getopts "h w d c" OPT
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
        c)
            ZSHFILE=Common
            update_local_zsh
            ;;
        *)
            print_usage
            ;;
    esac
done
