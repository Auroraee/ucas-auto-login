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
PORTAL_URL = 'https://portal.ucas.ac.cn/'          # 校园网认证页面（Srun 深澜系统）
TEST_URL = 'https://www.baidu.com'                 # 连通性测试网站
MAX_RETRIES = 3                                    # 最大重试次数
RETRY_INTERVAL = 10                                # 重试间隔（秒）
# 账号密码从 config.json 读取（该文件已被 .gitignore 忽略）
# ==========================================

# 日志配置：输出到脚本同目录下的 auto_login.log
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, 'auto_login.log')
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
        screenshot = os.path.join(LOG_DIR, f"login_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
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


def auto_login():
    options, profile_dir = build_chrome_options()

    try:
        chromedriver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"浏览器启动失败: {e}")
        cleanup_chrome_profile(profile_dir)
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
            should_click = fill_login_form(driver, wait)

            # ---- 第三步：点击登录按钮 ----
            if should_click:
                logger.info("[3/4] 正在点击登录按钮...")
                click_login_button(driver, wait)
                time.sleep(5)
            else:
                logger.info("[3/4] 检测到已登录，跳过点击。")

        # ---- 第四步：连通性测试 ----
        logger.info("[4/4] 正在测试网络连通性...")
        driver.get(TEST_URL)
        time.sleep(2)

        if "百度" in driver.title:
            logger.info("网络连接正常！")
            return True

        # requests 二次确认（allow_redirects=False：未登录时会被 302 到 portal，
        # 若跟随重定向 portal 页也是 200 会误判为在线）
        try:
            if is_online():
                logger.info("网络连接正常！（requests 确认）")
                return True
        except requests.RequestException:
            pass

        logger.warning("网络不通，请检查。")
        return False

    except Exception as e:
        logger.error(f"运行出错: {e}")
        log_page_state(driver, "登录流程失败")
        return False
    finally:
        driver.quit()
        cleanup_chrome_profile(profile_dir)


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


def wait_for_network(timeout=30):
    """等待底层网络就绪（开机时网卡/DHCP 可能尚未就绪）。

    判断标准：能够连上 portal 服务器（无论是否已登录）。一旦能连上 portal，
    就说明底层网络通了，可以开始尝试登录。如果一开始就能直接上 baidu，那
    说明已经在线，无需登录。
    """
    logger.info("等待底层网络就绪...")
    start = time.time()
    while time.time() - start < timeout:
        # 已经能上外网 → 不用等
        if is_online():
            logger.info("网络已就绪且已在线。")
            return True
        # 能连到 portal → 底层网络通了，可以尝试登录
        try:
            requests.get(PORTAL_URL, timeout=3)
            logger.info("底层网络已就绪。")
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
