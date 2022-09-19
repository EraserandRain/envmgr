#!/usr/bin/env bash

# define
netDeps="iputils-ping net-tools iproute2 curl wget"
otherDeps="git psmisc vim lrzsz"
pythonDeps="python3 python3-pip"
cppDeps="gcc automake autoconf libtool make build-essential gdb"

# set workdir
cd ~

# set repo mirror
sed -i -r 's#http://(archive|security).ubuntu.com#http://mirrors.tuna.tsinghua.edu.cn#g' /etc/apt/sources.list
apt-get -y update
apt-get -y upgrade
apt-get -y install apt-utils
apt-get -y install $netDeps
apt-get -y install $otherDeps

# install Node,nrm,pnpm
git clone https://github.com/EraserandRain/install.git
~/install/nvm/install-nvm.sh
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
nvm install --lts
npm i -g npm nrm pnpm
nrm use tencent

# install python3
apt-get -y install ${pythonDeps} 

# install cpp
apt-get -y install ${cppDeps} 

# install zsh
apt-get -y install zsh 
~/install/zsh/install_omz.sh --skip-chsh 
chsh -s /usr/bin/zsh 
git clone https://github.com/zsh-users/zsh-autosuggestions ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions 
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting 
~/install/zsh/update_local.sh -d
