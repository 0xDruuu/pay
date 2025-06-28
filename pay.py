import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv
from colorama import Fore, init
import cloudscraper
from fake_useragent import UserAgent

# Inisialisasi colorama
init(convert=True, autoreset=True)

# Load environment variables
load_dotenv()

# Konfigurasi
API_BASE_URL = "https://api.revapay.ai"
AUTH_BASE_URL = "https://auth.privy.io"
PRIVY_APP_ID = "yourprivy"
AMOUNT = 35  # Jumlah USDT
NETWORK = "polygon"
DELAY_BETWEEN_TRANSACTIONS = 20  # Detik antara A->B dan B->A
DELAY_ON_RETRY = 25  # Detik untuk retry
DELAY_ON_PROXY_FAIL = 30  # Detik kalau proxy gagal
MAX_RETRIES = 3  # Maksimal retry per request

# Proxy
PROXY_USERNAME = "username"
PROXY_PASSWORD = "pw"
PROXY_HOST = "host"
ACCOUNT_A_PROXY = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:10000"
ACCOUNT_B_PROXY = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:10001"

# Akun A
ACCOUNT_A = {
    "email": os.getenv("ACCOUNT_A_EMAIL", "youremail@gmail.com"),
    "payId": "yourpayID",
    "wallet": "0xyourwallet",
    "access_token": os.getenv("ACCOUNT_A_TOKEN"),
    "refresh_token": os.getenv("ACCOUNT_A_REFRESH_TOKEN"),
    "proxy": ACCOUNT_A_PROXY
}

# Akun B
ACCOUNT_B = {
    "email": os.getenv("ACCOUNT_B_EMAIL", "youremail@gmail.com"),
    "payId": "yourpayID",
    "wallet": "0xyourwallet",
    "access_token": os.getenv("ACCOUNT_B_TOKEN"),
    "refresh_token": os.getenv("ACCOUNT_B_REFRESH_TOKEN"),
    "proxy": ACCOUNT_B_PROXY
}

# Header untuk Privy Auth
ua = UserAgent()
AUTH_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "privy-app-id": PRIVY_APP_ID,
    "User-Agent": ua.random
}

def log_with_timestamp(message, color=Fore.WHITE):
    """Log dengan timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{color}[{timestamp}] {message}")

def create_session(proxy):
    """Buat session dengan cloudscraper dan proxy"""
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False},
        delay=10
    )
    session.proxies = {"http": proxy, "https": proxy}
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get("http://ipinfo.io/ip", timeout=15)
            if response.status_code == 200:
                log_with_timestamp(f"Proxy {proxy} aktif, IP: {response.text.strip()}", Fore.GREEN)
                return session
            else:
                log_with_timestamp(f"Proxy {proxy} gagal, status: {response.status_code}, coba lagi ({attempt+1}/{MAX_RETRIES})...", Fore.RED)
                time.sleep(DELAY_ON_PROXY_FAIL)
        except requests.RequestException as e:
            log_with_timestamp(f"Error tes proxy {proxy}: {e}, coba lagi ({attempt+1}/{MAX_RETRIES})...", Fore.RED)
            time.sleep(DELAY_ON_PROXY_FAIL)
    log_with_timestamp(f"Proxy {proxy} gagal setelah {MAX_RETRIES} percobaan, skip.", Fore.RED)
    return None

def update_env_file():
    """Update .env file dengan token terbaru"""
    try:
        with open(".env", "w") as f:
            f.write(
                f"ACCOUNT_A_EMAIL={ACCOUNT_A['email']}\n"
                f"ACCOUNT_A_TOKEN={ACCOUNT_A['access_token'] or ''}\n"
                f"ACCOUNT_A_REFRESH_TOKEN={ACCOUNT_A['refresh_token'] or ''}\n"
                f"ACCOUNT_B_EMAIL={ACCOUNT_B['email']}\n"
                f"ACCOUNT_B_TOKEN={ACCOUNT_B['access_token'] or ''}\n"
                f"ACCOUNT_B_REFRESH_TOKEN={ACCOUNT_B['refresh_token'] or ''}\n"
            )
        log_with_timestamp("Updated .env file with latest tokens", Fore.GREEN)
    except Exception as e:
        log_with_timestamp(f"Error updating .env file: {e}", Fore.RED)

def refresh_access_token(account):
    """Refresh access token menggunakan refresh token"""
    session = create_session(account["proxy"])
    if not session:
        return False
    log_with_timestamp(f"Refreshing token for {account['email']}...", Fore.YELLOW)
    try:
        payload = {"refresh_token": account["refresh_token"]}
        response = session.post(f"{AUTH_BASE_URL}/api/v1/refresh", json=payload, headers=AUTH_HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        account["access_token"] = data["token"]
        update_env_file()
        log_with_timestamp(f"Token refreshed for {account['email']}: {account['access_token'][:10]}...", Fore.GREEN)
        return True
    except requests.RequestException as e:
        log_with_timestamp(f"Error refreshing token for {account['email']}: {e}", Fore.RED)
        if e.response:
            log_with_timestamp(f"Response: {e.response.text} (Status: {e.response.status_code})", Fore.RED)
        return False

def login_passwordless(account):
    """Login ulang via passwordless"""
    session = create_session(account["proxy"])
    if not session:
        return False
    log_with_timestamp(f"Requesting OTP for {account['email']}...", Fore.YELLOW)
    try:
        payload = {"email": account["email"]}
        response = session.post(f"{AUTH_BASE_URL}/api/v1/passwordless/init", json=payload, headers=AUTH_HEADERS, timeout=15)
        response.raise_for_status()
        log_with_timestamp(f"OTP sent to {account['email']}, check no-reply@mail.privy.io", Fore.GREEN)
        code = input(Fore.YELLOW + f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Masukkan kode OTP untuk {account['email']}: ")
        payload = {
            "email": account["email"],
            "code": code,
            "mode": "login-or-sign-up"
        }
        response = session.post(f"{AUTH_BASE_URL}/api/v1/passwordless/authenticate", json=payload, headers=AUTH_HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        account["access_token"] = data["token"]
        account["refresh_token"] = data["refresh_token"]
        update_env_file()
        log_with_timestamp(f"Login successful for {account['email']}, new token: {account['access_token'][:10]}...", Fore.GREEN)
        return True
    except requests.RequestException as e:
        log_with_timestamp(f"Error during login for {account['email']}: {e}", Fore.RED)
        if e.response:
            log_with_timestamp(f"Response: {e.response.text} (Status: {e.response.status_code})", Fore.RED)
        return False

def get_headers(account):
    """Buat header untuk akun tertentu"""
    if not account["access_token"] or not account["refresh_token"]:
        log_with_timestamp(f"Token kosong untuk {account['email']}, coba login...", Fore.RED)
        if not login_passwordless(account):
            return None
    return {
        "Authorization": f"Bearer {account['access_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": ua.random
    }

def check_balance(account):
    """Cek saldo USDT akun"""
    session = create_session(account["proxy"])
    if not session:
        return None
    log_with_timestamp(f"Checking balance for {account['email']}...", Fore.YELLOW)
    try:
        response = session.get(f"{API_BASE_URL}/api/users/me", headers=get_headers(account), timeout=15)
        response.raise_for_status()
        data = response.json()
        balance = data.get("user", {}).get("balance", {}).get("usdt", 0)
        log_with_timestamp(f"Balance for {account['email']}: {balance} USDT", Fore.GREEN)
        return balance
    except requests.RequestException as e:
        if e.response and e.response.status_code == 401:
            log_with_timestamp(f"Token expired for {account['email']}, refreshing...", Fore.RED)
            if refresh_access_token(account):
                return check_balance(account)
            log_with_timestamp("Refresh token failed, try manual login", Fore.RED)
            if login_passwordless(account):
                return check_balance(account)
        log_with_timestamp(f"Error checking balance for {account['email']}: {e}", Fore.RED)
        if e.response:
            log_with_timestamp(f"Response: {e.response.text} (Status: {e.response.status_code})", Fore.RED)
        return None

def get_user_info(account):
    """Ambil info user dari /api/users/me"""
    session = create_session(account["proxy"])
    if not session:
        return None
    log_with_timestamp(f"Fetching user info for {account['email']}...", Fore.YELLOW)
    try:
        headers = get_headers(account)
        if not headers:
            return None
        response = session.get(f"{API_BASE_URL}/api/users/me", headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        account["wallet"] = data["user"]["walletAddress"]
        account["payId"] = data["user"]["payId"]
        log_with_timestamp(f"User info for {account['email']}: Wallet={account['wallet']}, PayID={account['payId']}", Fore.GREEN)
        return data
    except requests.RequestException as e:
        if e.response and e.response.status_code == 401:
            log_with_timestamp(f"Token expired for {account['email']}, refreshing...", Fore.RED)
            if refresh_access_token(account):
                return get_user_info(account)
            log_with_timestamp("Refresh token failed, try manual login", Fore.RED)
            if login_passwordless(account):
                return get_user_info(account)
        log_with_timestamp(f"Error fetching user info for {account['email']}: {e}", Fore.RED)
        if e.response:
            log_with_timestamp(f"Response: {e.response.text} (Status: {e.response.status_code})", Fore.RED)
        return None

def send_transaction(account, to_payid, amount, network):
    """Kirim transaksi via AI Revapay"""
    session = create_session(account["proxy"])
    if not session:
        return None, None
    log_with_timestamp(f"Sending {amount} USDT from {account['email']} to {to_payid}...", Fore.RED)
    payload = {
        "message": f"send {amount} usdt on {network} to {to_payid}(ID)",
        "roomId": None
    }
    for attempt in range(MAX_RETRIES):
        try:
            headers = get_headers(account)
            if not headers:
                return None, None
            response = session.post(f"{API_BASE_URL}/api/message/create-message", json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            room_id = data["data"]["data"]["roomCreated"]["roomId"]
            log_with_timestamp(f"Transaction sent from {account['email']}: {payload['message']}, RoomID={room_id}", Fore.CYAN)
            return data, room_id
        except requests.RequestException as e:
            if e.response and e.response.status_code == 401:
                log_with_timestamp(f"Token expired for {account['email']}, refreshing...", Fore.RED)
                if refresh_access_token(account):
                    return send_transaction(account, to_payid, amount, network)
                log_with_timestamp("Refresh token failed, try manual login", Fore.RED)
                if login_passwordless(account):
                    return send_transaction(account, to_payid, amount, network)
            log_with_timestamp(f"Error sending transaction from {account['email']}: {e}, coba lagi ({attempt+1}/{MAX_RETRIES})...", Fore.RED)
            if e.response:
                log_with_timestamp(f"Response: {e.response.text} (Status: {e.response.status_code})", Fore.RED)
            time.sleep(DELAY_ON_PROXY_FAIL)
    log_with_timestamp(f"Gagal kirim transaksi dari {account['email']} setelah {MAX_RETRIES} percobaan.", Fore.RED)
    return None, None

def check_transaction_status(account, room_id):
    """Cek status transaksi dari riwayat pesan"""
    session = create_session(account["proxy"])
    if not session:
        return False
    log_with_timestamp(f"Checking transaction status for {account['email']} (RoomID: {room_id})...", Fore.YELLOW)
    for attempt in range(MAX_RETRIES):
        try:
            headers = get_headers(account)
            if not headers:
                return False
            response = session.get(f"{API_BASE_URL}/api/message/get-message/{room_id}", headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            for msg in data["data"]:
                log_with_timestamp(f"Message: {msg['messageContent']}, IsSystem: {msg['isSystem']}, Action: {msg['action']}", Fore.LIGHTBLUE_EX)
                if "isError" in msg and msg["isError"]:
                    log_with_timestamp(f"Transaction failed: {msg['messageContent']}", Fore.RED)
                    return False
            return True
        except requests.RequestException as e:
            if e.response and e.response.status_code == 401:
                log_with_timestamp(f"Token expired for {account['email']}, refreshing...", Fore.RED)
                if refresh_access_token(account):
                    return check_transaction_status(account, room_id)
                log_with_timestamp("Refresh token failed, try manual login", Fore.RED)
                if login_passwordless(account):
                    return check_transaction_status(account, room_id)
            log_with_timestamp(f"Error checking transaction status for {account['email']}: {e}, coba lagi ({attempt+1}/{MAX_RETRIES})...", Fore.RED)
            if e.response:
                log_with_timestamp(f"Response: {e.response.text} (Status: {e.response.status_code})", Fore.RED)
            time.sleep(DELAY_ON_PROXY_FAIL)
    log_with_timestamp(f"Gagal cek status transaksi untuk {account['email']} setelah {MAX_RETRIES} percobaan.", Fore.RED)
    return False

def main():
    """Fungsi utama untuk memproses transaksi bolak-balik"""
    # Minta jumlah transaksi
    try:
        num_transactions = int(input(Fore.YELLOW + "Masukkan jumlah transaksi bolak-balik: "))
        if num_transactions <= 0:
            log_with_timestamp("Jumlah transaksi harus lebih dari 0!", Fore.RED)
            return
    except ValueError:
        log_with_timestamp("Masukkan angka yang valid!", Fore.RED)
        return

    # Cek info akun A dan B
    log_with_timestamp(f"Memeriksa info akun A ({ACCOUNT_A['email']})...", Fore.YELLOW)
    if not get_user_info(ACCOUNT_A):
        log_with_timestamp("Gagal ambil info akun A, stop.", Fore.RED)
        return
    log_with_timestamp(f"Memeriksa info akun B ({ACCOUNT_B['email']})...", Fore.YELLOW)
    if not get_user_info(ACCOUNT_B):
        log_with_timestamp("Gagal ambil info akun B, stop.", Fore.RED)
        return

    # Cek saldo akun A dan B
    balance_a = check_balance(ACCOUNT_A)
    if balance_a is None or balance_a < AMOUNT:
        log_with_timestamp(f"Saldo tidak cukup untuk Akun A ({ACCOUNT_A['email']}): {balance_a} USDT, butuh {AMOUNT} USDT", Fore.RED)
        return
    balance_b = check_balance(ACCOUNT_B)
    if balance_b is None or balance_b < AMOUNT:
        log_with_timestamp(f"Saldo tidak cukup untuk Akun B ({ACCOUNT_B['email']}): {balance_b} USDT, butuh {AMOUNT} USDT", Fore.RED)
        return

    # Loop transaksi bolak-balik
    for i in range(num_transactions):
        log_with_timestamp(f"\nTransaksi bolak-balik ke-{i+1}:", Fore.LIGHTYELLOW_EX)

        # Akun A kirim ke Akun B
        log_with_timestamp(f"Akun A ({ACCOUNT_A['payId']}) mengirim {AMOUNT} USDT ke {ACCOUNT_B['payId']}...", Fore.RED)
        tx1, room_id_a = send_transaction(ACCOUNT_A, ACCOUNT_B["payId"], AMOUNT, NETWORK)
        if not tx1:
            log_with_timestamp("Transaksi dari A ke B gagal, coba lagi setelah 25 detik...", Fore.RED)
            log_with_timestamp(f"Menunggu {DELAY_ON_RETRY} detik sebelum retry...", Fore.YELLOW)
            time.sleep(DELAY_ON_RETRY)
            tx1, room_id_a = send_transaction(ACCOUNT_A, ACCOUNT_B["payId"], AMOUNT, NETWORK)
            if not tx1:
                log_with_timestamp("Transaksi dari A ke B gagal lagi, stop.", Fore.RED)
                return
        log_with_timestamp(f"Menunggu {DELAY_BETWEEN_TRANSACTIONS} detik sebelum cek status transaksi A...", Fore.YELLOW)
        time.sleep(DELAY_BETWEEN_TRANSACTIONS)
        if not check_transaction_status(ACCOUNT_A, room_id_a):
            log_with_timestamp("Transaksi dari A ke B gagal, coba lagi setelah 25 detik...", Fore.RED)
            log_with_timestamp(f"Menunggu {DELAY_ON_RETRY} detik sebelum retry...", Fore.YELLOW)
            time.sleep(DELAY_ON_RETRY)
            tx1, room_id_a = send_transaction(ACCOUNT_A, ACCOUNT_B["payId"], AMOUNT, NETWORK)
            if not tx1 or not check_transaction_status(ACCOUNT_A, room_id_a):
                log_with_timestamp("Transaksi dari A ke B gagal lagi, stop.", Fore.RED)
                return

        # Delay sebelum Akun B kirim balik
        log_with_timestamp(f"Menunggu {DELAY_BETWEEN_TRANSACTIONS} detik sebelum Akun B kirim balik...", Fore.YELLOW)
        time.sleep(DELAY_BETWEEN_TRANSACTIONS)

        # Akun B kirim balik ke Akun A
        log_with_timestamp(f"Akun B ({ACCOUNT_B['payId']}) mengirim {AMOUNT} USDT kembali ke {ACCOUNT_A['payId']}...", Fore.RED)
        tx2, room_id_b = send_transaction(ACCOUNT_B, ACCOUNT_A["payId"], AMOUNT, NETWORK)
        if not tx2:
            log_with_timestamp("Transaksi balik dari B ke A gagal, coba lagi setelah 25 detik...", Fore.RED)
            log_with_timestamp(f"Menunggu {DELAY_ON_RETRY} detik sebelum retry...", Fore.YELLOW)
            time.sleep(DELAY_ON_RETRY)
            tx2, room_id_b = send_transaction(ACCOUNT_B, ACCOUNT_A["payId"], AMOUNT, NETWORK)
            if not tx2:
                log_with_timestamp("Transaksi balik dari B ke A gagal lagi, stop.", Fore.RED)
                return
        log_with_timestamp(f"Menunggu {DELAY_BETWEEN_TRANSACTIONS} detik sebelum cek status transaksi B...", Fore.YELLOW)
        time.sleep(DELAY_BETWEEN_TRANSACTIONS)
        if not check_transaction_status(ACCOUNT_B, room_id_b):
            log_with_timestamp("Transaksi balik dari B ke A gagal, coba lagi setelah 25 detik...", Fore.RED)
            log_with_timestamp(f"Menunggu {DELAY_ON_RETRY} detik sebelum retry...", Fore.YELLOW)
            time.sleep(DELAY_ON_RETRY)
            tx2, room_id_b = send_transaction(ACCOUNT_B, ACCOUNT_A["payId"], AMOUNT, NETWORK)
            if not tx2 or not check_transaction_status(ACCOUNT_B, room_id_b):
                log_with_timestamp("Transaksi balik dari B ke A gagal lagi, stop.", Fore.RED)
                return

        log_with_timestamp(f"Transaksi bolak-balik ke-{i+1} selesai!", Fore.GREEN)

    log_with_timestamp(f"\nSemua {num_transactions} transaksi bolak-balik selesai!", Fore.GREEN)

if __name__ == "__main__":
    main()