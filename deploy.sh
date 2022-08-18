#!/bin/bash
current_date=`date -d '0 day' "+%y%m%d"`
cd ~/install
git add .
git commit -m 'autoPush'
git push -u origin master
echo "autoPush_$current_date"
exit 0


