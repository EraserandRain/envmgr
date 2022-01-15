#!/bin/bash

## descrition
    ## This script is used for
        ## 1.auto push zshrc.bak to github
cd ~/install
git add .
git commit -m 'autoPush'
git push -u origin master
exit 0
