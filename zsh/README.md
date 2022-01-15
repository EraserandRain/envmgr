# 备份并同步 `~/.zshrc` 文件至 Github
检查 `cron` 运行
```zsh
sudo service cron status
crontab -l
```
编辑 `crontab`
```zsh
crontab -e

* */1 * * *   sudo ntpdate ntp.aliyun.com
* */2 * * *   cat ~/.zshrc > ~/install/zsh/zshrc.bak
    ## backup ~/.zshrc
* */2 * * *   ~/install/zsh/zshrc-push.sh > /dev/null
```