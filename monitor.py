"""
校园网智能监控脚本
- 流量 < 49GB 或 > 50GB：每 30 分钟用 requests 轻量检查一次
- 流量 49~50GB：每 3 分钟检测连通性，断线自动重连（此区间频繁掉线）
"""
import os
import sys
import time
import logging
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================= 配置区 =================
USERNAME = 'your_email@mails.ucas.ac.cn'
PASSWORD = 'your_password'
PORTAL_URL = 'https://portal.ucas.ac.cn/'
TEST_URL = 'https://www.baidu.com'
TRAFFIC_API = 'https://portal.ucas.ac.cn/cgi-bin/rad_user_info'
TRAFFIC_LOW_GB = 49                # 掉线风险区间起点
TRAFFIC_HIGH_GB = 50              # 掉线风险区间终点（超过后不再频繁检测）
IDLE_CHECK_INTERVAL = 1800         # 正常时检测间隔（秒），30 分钟
ACTIVE_CHECK_INTERVAL = 180        # 风险区间检测间隔（秒），3 分钟
MAX_LOGIN_RETRIES = 3              # 单次登录最大重试次数
# ==========================================

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, 'monitor.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def get_traffic_gb():
    """通过 Srun API 获取已用流量（GB），离线时返回 None"""
    try:
        resp = requests.get(TRAFFIC_API, timeout=5)
        if resp.status_code == 200 and ',' in resp.text:
            fields = resp.text.split(',')
            if len(fields) > 6 and fields[6].isdigit():
                return int(fields[6]) / (1024 ** 3)
    except requests.RequestException:
        pass
    return None


def is_online():
    """检测外网是否连通"""
    try:
        resp = requests.get(TEST_URL, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def do_login():
    """用 Selenium 执行一次登录"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument('--silent')

    chromedriver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
    service = ChromeService(executable_path=chromedriver_path)

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"浏览器启动失败: {e}")
        return False

    try:
        driver.get(PORTAL_URL)

        if 'success' in driver.current_url:
            logger.info("已登录，无需重复登录。")
            return True

        wait = WebDriverWait(driver, 20)
        username_input = wait.until(EC.presence_of_element_located((By.ID, 'username')))
        password_input = driver.find_element(By.ID, 'password')

        username_input.clear()
        username_input.send_keys(USERNAME)
        password_input.clear()
        password_input.send_keys(PASSWORD)

        driver.find_element(By.ID, 'login-account').click()
        time.sleep(3)

        driver.get(TEST_URL)
        time.sleep(2)

        if "百度" in driver.title:
            logger.info("登录成功！")
            return True

        try:
            if requests.get(TEST_URL, timeout=5).status_code == 200:
                logger.info("登录成功！")
                return True
        except requests.RequestException:
            pass

        logger.warning("登录后仍无法上网。")
        return False

    except Exception as e:
        logger.error(f"登录出错: {e}")
        return False
    finally:
        driver.quit()


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

    while True:
        traffic = get_traffic_gb()

        if traffic is not None:
            logger.info(f"当前流量: {traffic:.2f} GB")

            if TRAFFIC_LOW_GB <= traffic <= TRAFFIC_HIGH_GB:
                # ---- 49~50GB：掉线风险区间，密集监控 ----
                logger.warning(f"流量 {traffic:.2f} GB 处于掉线风险区间，进入密集监控")
                while True:
                    if not is_online():
                        logger.warning("检测到掉线，正在重新登录...")
                        time.sleep(5)
                        if relogin():
                            logger.info("重连成功！")
                        else:
                            logger.error("重连失败，3 分钟后重试。")
                    else:
                        # 检查流量是否已离开风险区间
                        new_traffic = get_traffic_gb()
                        if new_traffic is not None and not (TRAFFIC_LOW_GB <= new_traffic <= TRAFFIC_HIGH_GB):
                            logger.info(f"流量 {new_traffic:.2f} GB，已离开风险区间，恢复正常监控。")
                            break
                    time.sleep(ACTIVE_CHECK_INTERVAL)
            else:
                # ---- 正常区间：轻量检查 ----
                logger.info(f"流量正常，{IDLE_CHECK_INTERVAL // 60} 分钟后再次检查。")
        else:
            # API 不通，可能已掉线
            logger.warning("无法获取流量信息，可能已掉线，尝试重新登录...")
            time.sleep(5)
            if relogin():
                logger.info("重连成功！")
            else:
                logger.error("重连失败，5 分钟后重试。")
                time.sleep(300)
                continue

        time.sleep(IDLE_CHECK_INTERVAL)


if __name__ == '__main__':
    main()
