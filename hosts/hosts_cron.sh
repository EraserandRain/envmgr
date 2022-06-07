#!/bin/bash
export LC_ALL=C
wget https://raw.githubusercontent.com/ineo6/hosts/master/hosts -O hosts_tmp
sed -i '/^#/d' hosts_tmp
sed -i '/^$/d' hosts_tmp
sum=$(cat hosts_tmp|wc -l)
for (( i=0;i<"$sum";i++ ))
do
    ip_arr[$i]=$(awk '{print $1}' hosts_tmp|awk -v awkVar="$[$i+1]" 'NR==awkVar')
    domain_arr[$i]=$(awk '{print $2}' hosts_tmp|awk -v awkVar="$[$i+1]" 'NR==awkVar')
    current="${ip_arr[$i]} https://${domain_arr[$i]}"
    domain=${domain_arr[$i]}
    sed -i "$ a ${current}" hosts_tmp
    sudo sed -i "/github/d" /etc/hosts
    sudo bash -c "cat hosts_tmp >> /etc/hosts"
done
sudo echo "# GitHub hosts update at `date -d '0 day' '+%Y-%m-%d %X' `" >> /etc/hosts
exit 0