#!/bin/bash

## descrition: auto push zshrc.bak to github
cd ~/install
git add .
git commit -m 'autoPush'
git push -u origin master
exit 0
