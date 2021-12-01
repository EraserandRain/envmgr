# 应用安装配置
## 自动同步 `~/.zshrc` 文件至 Github
检查 `cron` 运行
```bash
service cron status
crontab -l
```
编辑 `crontab`
```bash
crontab -e

* */1 * * *   sudo ntpdate ntp.aliyun.com
* */2 * * *   cat ~/.zshrc > ~/install/zsh/zshrc.bak
    ## backup ~/.zshrc
* */2 * * *   ~/install/autopushtoGithub.sh > /dev/null
```