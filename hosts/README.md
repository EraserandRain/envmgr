Reference【[https://github.com/ineo6/hosts](https://github.com/ineo6/hosts)】

执行脚本同步 github host 至 `/etc/hosts` 。
```bash
git clone https://github.com/EraserandRain/install.git
cd install/hosts/
bash host_cron.sh

## or

curl https://raw.githubusercontent.com/EraserandRain/install/7a819d54cb790ccdbd80806e5712544de672f3d1/hosts/hosts_cron.sh | bash 

```