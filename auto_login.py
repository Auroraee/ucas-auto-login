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
USERNAME = 'your_email@mails.ucas.ac.cn'               # 替换为你的用户名
PASSWORD = 'your_password'                              # 替换为你的密码
PORTAL_URL = 'https://portal.ucas.ac.cn/'          # 校园网认证页面（Srun 深澜系统）
TEST_URL = 'https://www.baidu.com'                 # 连通性测试网站
MAX_RETRIES = 3                                    # 最大重试次数
RETRY_INTERVAL = 10                                # 重试间隔（秒）
# ==========================================

# 日志配置：输出到脚本同目录下的 auto_login.log
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, 'auto_login.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def auto_login():
    # Chrome 无头模式配置
    options = Options()
    options.add_argument('--headless=new')       # 新版无头模式
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument('--silent')

    try:
        chromedriver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"浏览器启动失败: {e}")
        return False

    try:
        # ---- 第一步：打开校园网认证页面 ----
        logger.info("[1/4] 正在打开校园网认证页面...")
        driver.get(PORTAL_URL)
        wait = WebDriverWait(driver, 20)

        # 检测是否已登录（URL 包含 success 表示已在线）
        if 'success' in driver.current_url:
            logger.info("检测到已登录状态，跳过登录步骤。")
        else:
            # ---- 第二步：填写用户名和密码 ----
            logger.info("[2/4] 正在输入账号密码...")
            username_input = wait.until(
                EC.presence_of_element_located((By.ID, 'username'))
            )
            password_input = driver.find_element(By.ID, 'password')

            username_input.clear()
            username_input.send_keys(USERNAME)
            password_input.clear()
            password_input.send_keys(PASSWORD)

            # ---- 第三步：点击登录按钮 ----
            logger.info("[3/4] 正在点击登录按钮...")
            login_btn = driver.find_element(By.ID, 'login-account')
            login_btn.click()
            time.sleep(3)

        # ---- 第四步：连通性测试 ----
        logger.info("[4/4] 正在测试网络连通性...")
        driver.get(TEST_URL)
        time.sleep(2)

        if "百度" in driver.title:
            logger.info("网络连接正常！")
            return True

        # requests 二次确认
        try:
            resp = requests.get(TEST_URL, timeout=5)
            if resp.status_code == 200:
                logger.info("网络连接正常！（requests 确认）")
                return True
        except requests.RequestException:
            pass

        logger.warning("网络不通，请检查。")
        return False

    except Exception as e:
        logger.error(f"运行出错: {e}")
        return False
    finally:
        driver.quit()


def wait_for_network(timeout=10):
    """等待网络连接就绪（开机时网络可能尚未就绪）"""
    logger.info("等待网络连接...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get('https://www.baidu.com', timeout=3)
            logger.info("网络已就绪。")
            return True
        except requests.RequestException:
            time.sleep(2)
    logger.warning("等待网络超时，仍将尝试登录...")
    return False


if __name__ == '__main__':
    logger.info("=" * 40)
    logger.info(f"校园网自动登录启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 等待网络就绪
    wait_for_network()

    # 带重试的登录
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"第 {attempt}/{MAX_RETRIES} 次尝试...")
        if auto_login():
            logger.info("任务完成。")
            break
        if attempt < MAX_RETRIES:
            logger.info(f"等待 {RETRY_INTERVAL} 秒后重试...")
            time.sleep(RETRY_INTERVAL)
    else:
        logger.error(f"已达到最大重试次数 ({MAX_RETRIES})，登录失败。")

    logger.info("脚本退出。")
