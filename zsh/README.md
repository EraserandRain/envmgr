# 备份并同步 `~/.zshrc` 文件至 Github
检查 `cron` 运行
```zsh
sudo service cron status
crontab -l
```
编辑 `crontab`
```zsh
crontab -e
```
```zsh
* */1 * * *   sudo ntpdate ntp.aliyun.com
* */2 * * *   cat ~/.zshrc > ~/install/zsh/zshrc.bak
    ## backup ~/.zshrc
* */6 * * *   ~/install/zsh/zshrc-push.sh > /dev/null
```

## 更新本地 `~/.zshrc` 文件
执行 `zsh/zshrc-update.sh` 即可
