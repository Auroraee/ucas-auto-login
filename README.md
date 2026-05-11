# UCAS 校园网自动登录 & 智能监控

国科大（UCAS）校园网 Srun 深澜认证系统的自动登录工具。支持单次登录和长期后台监控，能在流量到达 49~50 GB 掉线高发区间时自动检测并重连。

## 功能

- **自动登录** — 通过 Selenium 无头 Chrome 自动填写账密、点击登录
- **智能监控** — 后台持续运行，根据流量区间动态调整检测频率
  - 流量 < 49 GB 或 > 50 GB：每 30 分钟轻量检查一次
  - 流量 49~50 GB（掉线高发区间）：每 3 分钟密集检测，断线自动重连
- **开机自启** — 通过 Windows 计划任务实现开机自动运行（SYSTEM 账户，无需登录）

## 环境要求

- Windows 10/11
- [Python 3.x](https://www.python.org/downloads/)（建议 3.8+）
- [Google Chrome](https://www.google.com/chrome/) 浏览器
- ChromeDriver（版本需与 Chrome 匹配）

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/your_username/ucas-auto-login.git
cd ucas-auto-login
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 下载 ChromeDriver

访问 [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/)，下载与你的 Chrome 版本匹配的 ChromeDriver，将 `chromedriver.exe` 放到项目根目录。

> 查看 Chrome 版本：打开 Chrome → 地址栏输入 `chrome://version` → 查看版本号

### 4. 配置账号密码

编辑 `auto_login.py` 和 `monitor.py`，找到配置区，替换为你的校园网账号：

```python
USERNAME = 'your_email@mails.ucas.ac.cn'    # 你的学号邮箱
PASSWORD = 'your_password'                   # 你的密码
```

## 使用方式

### 方式一：单次登录

双击 `run_auto_login.bat`，或命令行运行：

```bash
python auto_login.py
```

适合手动测试是否能正常登录。

### 方式二：后台监控（推荐）

双击 `run_monitor.bat`，或命令行运行：

```bash
python monitor.py
```

脚本会持续在后台运行，自动检测网络状态并在掉线时重连。

### 方式三：开机自启

以管理员身份运行 PowerShell：

```powershell
.\setup_autostart.ps1
```

这会创建一个 Windows 计划任务，开机后 30 秒自动启动监控（SYSTEM 账户，无需登录）。

> 注意：`setup_autostart.ps1` 会自动检测 Python 路径并覆盖 `run_monitor.bat`，以确保 SYSTEM 账户能正确找到 Python 解释器。

要移除开机自启：

```powershell
.\remove_autostart.ps1
```

## 文件说明

```
auto_login.py         # 单次自动登录脚本
monitor.py            # 智能监控脚本（长期运行）
run_auto_login.bat    # 单次登录的启动器
run_monitor.bat       # 监控脚本的启动器
setup_autostart.ps1   # 配置开机自启（管理员运行）
remove_autostart.ps1  # 移除开机自启
requirements.txt      # Python 依赖
```

## 可选配置

在 `monitor.py` 中可调整以下参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TRAFFIC_LOW_GB` | 49 | 掉线风险区间起点（GB） |
| `TRAFFIC_HIGH_GB` | 50 | 掉线风险区间终点（GB） |
| `IDLE_CHECK_INTERVAL` | 1800 | 正常检测间隔（秒） |
| `ACTIVE_CHECK_INTERVAL` | 180 | 风险区间检测间隔（秒） |
| `MAX_LOGIN_RETRIES` | 3 | 单次登录最大重试次数 |

## 常见问题

**Q: ChromeDriver 版本不匹配怎么办？**
A: 打开 `chrome://version` 查看 Chrome 版本，去 [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) 下载对应版本的 ChromeDriver。

**Q: 计划任务运行了但没登录成功？**
A: 检查 `monitor.log` 日志文件。常见原因是 ChromeDriver 版本不匹配或账号密码配置错误。

**Q: 支持其他学校的校园网吗？**
A: 本工具针对国科大 Srun 深澜认证系统。如果你的学校也使用 Srun 系统，修改 `PORTAL_URL` 即可尝试。

## License

[MIT](LICENSE)
