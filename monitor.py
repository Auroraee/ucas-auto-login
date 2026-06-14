"""
校园网智能监控脚本
- 始终以"连通性"为第一判据：掉线即重连
- 流量 49~50GB（掉线高发区间）：每 3 分钟检测一次
- 其它区间：每 30 分钟检测一次
- 兜底：连续两次流量读数完全相同（疑似掉线后 API 返回缓存值）也会触发重连
"""
import os
import json
import shutil
import sys
import tempfile
import time
import logging
import requests
from datetime import datetime
from logging.handlers import RotatingFileHandler
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ================= 配置区 =================
PORTAL_URL = 'https://portal.ucas.ac.cn/'
TEST_URL = 'https://www.baidu.com'
TRAFFIC_API = 'https://portal.ucas.ac.cn/cgi-bin/rad_user_info'
TRAFFIC_LOW_GB = 49                # 掉线风险区间起点
TRAFFIC_HIGH_GB = 50               # 掉线风险区间终点（超过后不再频繁检测）
IDLE_CHECK_INTERVAL = 1800         # 正常时检测间隔（秒），30 分钟
ACTIVE_CHECK_INTERVAL = 180        # 风险区间检测间隔（秒），3 分钟
MAX_LOGIN_RETRIES = 3              # 单次登录最大重试次数
# 账号密码从 config.json 读取（该文件已被 .gitignore 忽略）
# ==========================================

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, 'monitor.log')
CHROME_PROFILE_ROOT = os.path.join(LOG_DIR, 'chrome_profiles')
CHROME_TEMP_ROOT = os.path.join(LOG_DIR, 'chrome_temp')
CONFIG_FILE = os.path.join(LOG_DIR, 'config.json')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def load_credentials():
    """从 config.json 读取账号密码；文件不存在时报错并退出。"""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"未找到配置文件: {CONFIG_FILE}")
        logger.error("请复制 config.example.json 为 config.json，并填入你的校园网账号密码。")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg['username'], cfg['password']
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"配置文件格式错误: {e}")
        sys.exit(1)


USERNAME, PASSWORD = load_credentials()


def build_chrome_options():
    os.makedirs(CHROME_PROFILE_ROOT, exist_ok=True)
    os.makedirs(CHROME_TEMP_ROOT, exist_ok=True)
    os.environ['TEMP'] = CHROME_TEMP_ROOT
    os.environ['TMP'] = CHROME_TEMP_ROOT
    profile_dir = tempfile.mkdtemp(prefix='profile_', dir=CHROME_PROFILE_ROOT)

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-component-extensions-with-background-pages')
    options.add_argument('--log-level=3')
    options.add_argument('--silent')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    # Headless Chrome defaults to a small viewport; the portal footer can overlap
    # the login button at that size and intercept Selenium's click.
    options.add_argument('--window-size=1366,900')
    options.add_argument('--force-device-scale-factor=1')
    options.add_argument(f'--user-data-dir={profile_dir}')
    return options, profile_dir


def cleanup_chrome_profile(profile_dir):
    if not profile_dir:
        return
    try:
        shutil.rmtree(profile_dir, ignore_errors=True)
    except Exception as e:
        logger.warning(f"清理 Chrome 临时目录失败: {e}")


def log_page_state(driver, reason):
    try:
        logger.error(f"{reason}: url={driver.current_url}, title={driver.title}")
        screenshot = os.path.join(LOG_DIR, f"monitor_login_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        driver.save_screenshot(screenshot)
        logger.error(f"已保存失败截图: {screenshot}")
    except Exception as e:
        logger.error(f"记录页面状态失败: {e}")


def fill_login_form(driver, wait):
    if 'success' in driver.current_url:
        return False

    try:
        username_input = wait.until(EC.presence_of_element_located((By.ID, 'username')))
        password_input = wait.until(EC.presence_of_element_located((By.ID, 'password')))
    except TimeoutException:
        if 'success' in driver.current_url:
            return False
        raise

    username_input.clear()
    username_input.send_keys(USERNAME)
    password_input.clear()
    password_input.send_keys(PASSWORD)
    return True


def click_login_button(driver, wait):
    login_btn = wait.until(EC.presence_of_element_located((By.ID, 'login-account')))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_btn)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", login_btn)


def get_traffic_gb():
    """通过 Srun API 获取已用流量（GB），离线时返回 None。

    带 cache-buster 参数，避免中间缓存返回旧值。
    """
    try:
        # _t 时间戳防止任何中间层缓存返回旧数据
        resp = requests.get(TRAFFIC_API, params={'_t': int(time.time() * 1000)}, timeout=5)
        if resp.status_code == 200 and ',' in resp.text:
            fields = resp.text.split(',')
            if len(fields) >= 7 and fields[6].isdigit():
                return int(fields[6]) / (1024 ** 3)
    except requests.RequestException:
        pass
    return None


def is_online():
    """检测外网是否真正连通。

    关键点：未登录时访问 baidu 会被 302 重定向到 portal，portal 页本身返回 200，
    所以不能只看状态码。用 allow_redirects=False 后，只有未重定向（即真正能上外网）
    才会拿到 200。
    """
    try:
        resp = requests.get(TEST_URL, timeout=5, allow_redirects=False)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def do_login():
    """用 Selenium 执行一次登录"""
    options, profile_dir = build_chrome_options()

    chromedriver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
    service = ChromeService(executable_path=chromedriver_path)

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"浏览器启动失败: {e}")
        cleanup_chrome_profile(profile_dir)
        return False

    try:
        driver.get(PORTAL_URL)

        if 'success' in driver.current_url:
            logger.info("已登录，无需重复登录。")
            return True

        wait = WebDriverWait(driver, 20)
        should_click = fill_login_form(driver, wait)

        if should_click:
            click_login_button(driver, wait)
            time.sleep(5)
        else:
            logger.info("已登录，无需点击登录按钮。")

        # 二次确认：用 requests（allow_redirects=False）判断是否真正连通外网。
        # 不再用 selenium 跳转 TEST_URL + 读 title，避免页面缓存导致误判。
        if is_online():
            logger.info("登录成功！")
            return True

        logger.warning("登录后仍无法上网。")
        return False

    except Exception as e:
        logger.error(f"登录出错: {e}")
        log_page_state(driver, "登录流程失败")
        return False
    finally:
        driver.quit()
        cleanup_chrome_profile(profile_dir)


def relogin():
    """带重试的登录"""
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        logger.info(f"登录尝试 {attempt}/{MAX_LOGIN_RETRIES}...")
        if do_login():
            return True
        if attempt < MAX_LOGIN_RETRIES:
            time.sleep(5)
    logger.error("登录重试全部失败。")
    return False


def main():
    logger.info("=" * 40)
    logger.info(f"校园网智能监控启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"掉线风险区间: {TRAFFIC_LOW_GB}~{TRAFFIC_HIGH_GB} GB")

    # 记录上一次流量，用于"流量长期不增长 → 疑似掉线"兜底判断
    last_traffic_gb = None

    while True:
        # ---- 第一步：连通性检测（永远是第一判据）----
        online = is_online()

        # ---- 第二步：读取流量（用于决定检测频率 + 兜底）----
        traffic = get_traffic_gb()
        if traffic is not None:
            logger.info(f"当前流量: {traffic:.2f} GB" + (" [在线]" if online else " [离线]"))

        # ---- 第三步：掉线即重连（无论流量区间）----
        if not online:
            logger.warning("检测到掉线，正在重新登录...")
            time.sleep(5)
            if relogin():
                logger.info("重连成功！")
            else:
                logger.error("重连失败。")
            # 重连后重置流量基线，避免用旧值做"不增长"判断
            last_traffic_gb = None
            # 重连刚结束，给点时间再进入下一轮，用风险区间的短间隔
            time.sleep(ACTIVE_CHECK_INTERVAL)
            continue

        # ---- 第四步：在线状态下，流量不增长兜底 ----
        # 在线但流量读数长时间纹丝不动（说明 API 可能返回缓存值，
        # 实际已掉线而 is_online 误判），强制重连一次。
        if traffic is not None and last_traffic_gb is not None and traffic == last_traffic_gb:
            logger.warning(f"流量连续两次为 {traffic:.2f} GB 无变化，疑似掉线（API 返回缓存值），触发重连。")
            if relogin():
                logger.info("重连成功！")
            last_traffic_gb = None
            time.sleep(ACTIVE_CHECK_INTERVAL)
            continue
        last_traffic_gb = traffic

        # ---- 第五步：根据流量区间决定下次检测间隔 ----
        if traffic is not None and TRAFFIC_LOW_GB <= traffic <= TRAFFIC_HIGH_GB:
            logger.warning(f"流量 {traffic:.2f} GB 处于掉线风险区间，{ACTIVE_CHECK_INTERVAL // 60} 分钟后再次检测。")
            time.sleep(ACTIVE_CHECK_INTERVAL)
        else:
            interval_min = IDLE_CHECK_INTERVAL // 60
            logger.info(f"流量正常，{interval_min} 分钟后再次检查。")
            time.sleep(IDLE_CHECK_INTERVAL)


if __name__ == '__main__':
    main()
