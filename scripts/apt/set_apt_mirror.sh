#!/usr/bin/env bash
destr=$(lsb_release -is)
version=$(lsb_release -rs)
sudo mv /etc/apt/sources.list /etc/apt/sources.list.bak
sudo cp -r ./source/${destr}_${version} /etc/apt/sources.list
sudo apt-get -y update
