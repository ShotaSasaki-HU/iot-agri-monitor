import time
import json
import os
import random
import datetime

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAT_FILE = os.path.join(DATA_DIR, "sat_state.json")
SENSOR_FILE = os.path.join(DATA_DIR, "ground_state.json")

# 【デモ用操作パラメータ】
# ここを 0.3 とかに書き換えて保存すると、地上センサが急激に乾燥/湿潤してアラートが出る
SHIFT_AMOUNT = 0.0  # +0.3: 異常に湿っている, -0.3: 異常に乾いている

def get_satellite_baseline():
    """衛星の最新推定値をベースラインとして取得"""
    if os.path.exists(SAT_FILE):
        try:
            with open(SAT_FILE, "r") as f:
                data = json.load(f)
                return data.get("vwc_satellite", 0.25) # デフォルト0.25
        except:
            pass
    return 0.25

def run_sensor_loop():
    print(f"Virtual Ground Sensor Started. (Shift: {SHIFT_AMOUNT})")
    
    while True:
        # 1. 衛星データをチラ見（正解データの取得）
        baseline = get_satellite_baseline()
        
        # 2. ノイズの付与 (センサの揺らぎ: 標準偏差 0.01)
        noise = random.gauss(0, 0.01)
        
        # 3. 異常値の注入 (SHIFT_AMOUNT)
        simulated_vwc = baseline + noise + SHIFT_AMOUNT
        
        # 物理的限界 (0.0 ~ 1.0)
        simulated_vwc = max(0.0, min(1.0, simulated_vwc))
        
        # 4. データ保存
        output = {
            "vwc_ground": round(simulated_vwc, 3),
            "timestamp": time.time(),
            "shift_applied": SHIFT_AMOUNT
        }
        
        # Atomic Write
        tmp_file = SENSOR_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(output, f)
        os.replace(tmp_file, SENSOR_FILE)
        
        time.sleep(5) # 5秒ごとに更新

if __name__ == "__main__":
    run_sensor_loop()
