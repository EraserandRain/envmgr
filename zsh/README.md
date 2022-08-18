## Project Description
| **Project** | **Description** |
| - | - |
|install_omz.sh|Install ohmyzsh|
|update_local.sh|update local zshrc (~/.zshrc)|
|sync_bak.sh|sync local zshrc (~/.zshrc) to `bak_for_zshrc`|

## Usage
### 备份并同步 `~/.zshrc` 文件至 Github

`crontab` 配置( `crontab -e` )
```zsh
* */1 * * *   sudo ntpdate ntp.aliyun.com
* */2 * * *   ~/install/zsh/sync_bak.sh
* */6 * * *   ~/install/deploy.sh > /dev/null
```