import time
import json
import os
import ssl
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# --- 設定 ---
load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAT_FILE = os.path.join(DATA_DIR, "sat_state.json")
SENSOR_FILE = os.path.join(DATA_DIR, "ground_state.json")
CERT_DIR = os.path.join(BASE_DIR, "certs")

# MQTT設定 (BさんのPCのIPを指定)
BROKER = os.getenv("MQTT_BROKER_IP") 
PORT = 8883
TOPIC = "iot/field/raspi_01/live"

# ロジック閾値
THRESHOLD_DIFF = 0.15   # 0.15 (15%) 以上ズレたらコンフリクト
DROUGHT_LEVEL = 0.15    # 15% 以下なら乾燥

def read_data():
    """2つの最新データを読み込む"""
    sat_data = {"vwc_satellite": 0.25} # デフォルト
    ground_data = {"vwc_ground": 0.25}
    
    if os.path.exists(SAT_FILE):
        try:
            with open(SAT_FILE, "r") as f: sat_data = json.load(f)
        except: pass
        
    if os.path.exists(SENSOR_FILE):
        try:
            with open(SENSOR_FILE, "r") as f: ground_data = json.load(f)
        except: pass
        
    return sat_data.get("vwc_satellite"), ground_data.get("vwc_ground")

def judge_status(sat_val, ground_val):
    """判定ロジックの実装"""
    diff = abs(sat_val - ground_val)
    
    # 判定1: 乖離チェック
    if diff > THRESHOLD_DIFF:
        return "SENSOR_CONFLICT"
    
    # 判定2: 両方とも乾燥しているか
    if sat_val < DROUGHT_LEVEL and ground_val < DROUGHT_LEVEL:
        return "CRITICAL_DROUGHT"
    
    # それ以外
    return "OK"

def main():
    # MQTTクライアント設定
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    
    # 証明書設定 (MQTTS + クライアント認証)
    client.tls_set(
        ca_certs=os.path.join(CERT_DIR, "ca.crt"),
        certfile=os.path.join(CERT_DIR, "publisher.crt"),
        keyfile=os.path.join(CERT_DIR, "publisher.key"),
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )
    # LAN内なのでホスト名検証は無効化
    client.tls_insecure_set(True)

    print(f"Connecting to Broker {BROKER}...")
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    print("Publishing loop started.")
    try:
        while True:
            # 1. データ収集
            sat_val, ground_val = read_data()
            
            # 2. 判定
            status = judge_status(sat_val, ground_val)
            
            # 3. ペイロード作成
            payload = {
                "device_id": "raspi_01",
                "timestamp": time.time(),
                "data": {
                    "vwc_satellite": sat_val,
                    "vwc_ground": ground_val,
                    "diff": round(abs(sat_val - ground_val), 3),
                    "status": status
                }
            }
            
            # 4. 送信
            client.publish(TOPIC, json.dumps(payload), qos=1)
            print(f"[{status}] Sat:{sat_val:.2f} / Gnd:{ground_val:.2f}")
            
            time.sleep(10) # 10秒ごとに報告

    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
