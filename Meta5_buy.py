import imaplib
import email
import MetaTrader5 as mt5
import time
from dotenv import load_dotenv
import os

load_dotenv()

# ----------------- EMAIL SETTINGS -----------------
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_FOLDER = "INBOX"

# ----------------- MT5 SETTINGS -----------------
ACCOUNT_NUMBER = int(os.getenv("MT5_ACCOUNT"))  # Replace with your Exness account number
PASSWORD = os.getenv("MT5_PASSWORD")
SERVER = os.getenv("MT5_SERVER")  # Replace with your broker's server name
SYMBOL = os.getenv("SYMBOL")  # Replace with the trading pair you want to trade
LOT_SIZE = os.getenv("LOT_SIZE")  # Adjust according to your risk management
TIMEFRAME = mt5.TIMEFRAME_M5  # 5-minute timeframe

# ----------------- GLOBAL VARIABLES -----------------
last_trade = None  # Stores last trade type (BUY/SELL)
last_ticket = None  # Stores last trade ticket for closing

# ----------------- FUNCTION: Connect to MT5 -----------------
def connect_mt5():
    """ Connects to the MetaTrader 5 terminal """
    if not mt5.initialize():
        print("❌ MT5 Initialization failed!")
        return False
    authorized = mt5.login(ACCOUNT_NUMBER, password=PASSWORD, server=SERVER)
    if not authorized:
        print(f"❌ MT5 Login failed. Error: {mt5.last_error()}")
        return False
    print("✅ Connected to Exness MT5!")
    return True

# ----------------- FUNCTION: Fetch Latest Email -----------------
def check_email():
    """ Fetches the latest unread email containing a trading alert """
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select(EMAIL_FOLDER)

        status, messages = mail.search(None, 'UNSEEN')  # Get unread emails

        if messages[0]:  # If unread emails exist
            latest_email_id = messages[0].split()[-1]  # Get latest email ID
            status, data = mail.fetch(latest_email_id, "(RFC822)")

            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    email_body = ""

                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                email_body += part.get_payload(decode=True).decode()
                    else:
                        email_body = msg.get_payload(decode=True).decode()

                    mail.store(latest_email_id, "+FLAGS", "\\Seen")  # Mark email as read
                    return email_body

        mail.logout()
        return None  # No new emails

    except Exception as e:
        print(f"❌ Email reading error: {str(e)}")
        return None

# ----------------- FUNCTION: Extract Trade Signal -----------------
def extract_signal_from_email(email_body):
    """ Extracts the trade signal (BUY or SELL) from the email content """
    if "Crossing" in email_body:
        return True  # Signal detected
    return False  # No trade signal found

# ----------------- FUNCTION: Close Open Position -----------------
def close_last_trade():
    """ Closes the last open trade if it exists """
    global last_ticket

    if last_ticket is None:
        return True  # No open trade to close

    position = mt5.positions_get(ticket=last_ticket)
    if not position:
        last_ticket = None
        return True  # Position already closed

    close_price = mt5.symbol_info_tick(SYMBOL).bid if position[0].type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(SYMBOL).ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": position[0].volume,
        "type": mt5.ORDER_TYPE_SELL if position[0].type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "position": last_ticket,
        "price": close_price,
        "deviation": 10,
        "magic": 0,
        "comment": "Close previous trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }

    order_result = mt5.order_send(request)
    if order_result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Closed last trade: {last_ticket}")
        last_ticket = None  # Reset last ticket
        return True
    else:
        print(f"❌ Failed to close trade: {order_result.comment}")
        return False

# ----------------- FUNCTION: Place Order on MT5 -----------------
def place_order(action):
    """ Places a new trade order on MT5 """
    global last_trade, last_ticket

    # Close previous trade if exists
    if not close_last_trade():
        return

    price = mt5.symbol_info_tick(SYMBOL).ask if action == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": float(LOT_SIZE),
        "type": order_type,
        "price": price,
        "deviation": 10,
        "magic": 0,
        "comment": "TradingView Signal Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }

    order_result = mt5.order_send(request)

    if order_result is None:
        print("❌ Order failed: order_result is None")
        print(f"🔎 Last MT5 Error: {mt5.last_error()}")
        return

    if order_result.retcode == mt5.TRADE_RETCODE_DONE:
        last_trade = action  # Update last trade
        last_ticket = order_result.order  # Store trade ticket
        print(f"✅ {action} order placed successfully at {price}")
    else:
        print(f"❌ Order failed: {order_result.comment}")

# ----------------- FUNCTION: Main Trading Bot Loop -----------------
def run_bot():
    """ Main loop to check for email alerts and execute trades """
    global last_trade

    if not connect_mt5():
        print("❌ MT5 connection failed. Exiting...")
        return
    
    print("🚀 Bot Started! Checking for TradingView alerts every 60 seconds...")

    while True:
        email_body = check_email()  # Get latest email content
        
        if email_body:
            print(f"📩 Latest Email Content:\n {email_body}")
            signal = extract_signal_from_email(email_body)  # Extract signal

            if signal:
                if last_trade is None or last_trade == "SELL":
                    action = "BUY"
                else:
                    action = "SELL"

                print(f"📊 Signal detected: Closing previous trade & Placing {action} order...")
                place_order(action)  # Place new trade
            else:
                print("🔄 No new trade signals.")
        else:
            print("🔄 No new emails detected.")

        time.sleep(10)  # Wait for 1 minute before checking again

# ----------------- RUN THE BOT -----------------
if __name__ == "__main__":
    run_bot()
