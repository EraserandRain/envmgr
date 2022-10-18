#!/usr/bin/env bash
export LC_ALL=C

cd $HOME
source $HOME/install/include/common.sh

# Other Settings
if_jammy_os disable_needrestart set_apt_mirror
set_git_config


# Install
install_env \
--node \
--python \
--cpp \
--ubuntu_docker \
--zsh


$HOME/install/zsh/update_local.sh -w
source $HOME/.zshrc