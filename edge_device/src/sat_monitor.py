import openeo
import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "sat_state.json")

load_dotenv(os.path.join(BASE_DIR, ".env"))

# 監視エリアの定義
AOI = {
    "west": 132.724, "south": 34.393,
    "east": 132.733, "north": 34.404,
    "crs": "EPSG:4326"
}

def calculate_optram_vwc(connection):
    """
    openEOサーバー上でOPTRAMを計算し、エリア平均の体積含水率(VWC)を取得する
    """
    # 過去10日間のデータを検索 (Sentinel-2は5日回帰なので必ず1-2枚はあるはず)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=10)

    # 1. データロード (B04:Red, B08:NIR, B12:SWIR)
    cube = connection.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=AOI,
        temporal_extent=[str(start_date), str(end_date)],
        bands=["B04", "B08", "B12", "SCL"],
        max_cloud_cover=60
    )

    # 2. クラウドマスク適用
    scl = cube.band("SCL")
    # 3:Shadow, 8:Medium, 9:High, 10:Cirrus
    mask = (scl == 3) | (scl == 8) | (scl == 9) | (scl == 10)
    cube = cube.mask(mask)

    # 3. 時間方向の集約 (Median合成で雲の影響を軽減)
    # 値を0-1.0の反射率に正規化 (S2は通常0-10000)
    composite = cube.reduce_dimension(dimension="t", reducer="median")
    composite = composite / 10000.0

    B04 = composite.band("B04")
    B08 = composite.band("B08")
    B12 = composite.band("B12")

    # 4. OPTRAM計算
    # 4.1 NDVI
    ndvi = (B08 - B04) / (B08 + B04)

    # 4.2 STR (Shortwave Infrared Transformed Reflectance)
    # STR = (1 - R_swir)^2 / (2 * R_swir)
    str_val = ((1.0 - B12) ** 2) / (2.0 * B12)

    # 4.3 パラメータ設定 (Walnut Gulch S2 Scenario 1 from Paper)
    i_d, s_d = 0.00, 0.16  # Dry Edge
    i_w, s_w = 2.70, 7.10  # Wet Edge
    theta_d, theta_w = 0.05, 0.45 # 残留～飽和含水率

    # 4.4 正規化水分量 W の計算
    str_dry = i_d + (s_d * ndvi)
    str_wet = i_w + (s_w * ndvi)
    W = (str_val - str_dry) / (str_wet - str_dry)

    # 4.5 体積含水率 (VWC) への変換
    vwc_cube = W * (theta_w - theta_d) + theta_d

    # 5. 空間集約 (エリア全体の平均値を算出)
    mean_vwc = vwc_cube.aggregate_spatial(
        geometries=AOI,
        reducer="mean"
    )

    # 計算実行 (同期処理)
    print("Requesting calculation to openEO backend...")
    result_json = mean_vwc.execute()
    
    # JSON構造から値を取り出す (戻り値は時系列リストの形式だが、reduce_tしているので1つ)
    # ※ openEOのバージョンやバックエンドにより戻り値の構造が微妙に違う場合があるので注意
    # 通常は [[value]] または {date: value} のような形式
    try:
        # 簡易的な取り出し（実環境に合わせて調整してください）
        val = result_json[0][0] if isinstance(result_json, list) else list(result_json.values())[0]
        if val is None: return None
        return float(val)
    except:
        print(f"Unexpected result format: {result_json}")
        return 0.25 # フォールバック値

def main():
    try:
        print("Connecting to openEO...")
        conn = openeo.connect(url="openeo.dataspace.copernicus.eu")
        conn.authenticate_oidc_client_credentials(
            client_id=os.getenv('OPENEO_CLIENT_ID'),
            client_secret=os.getenv('OPENEO_CLIENT_SECRET'),
        )

        vwc = calculate_optram_vwc(conn)
        
        if vwc is not None:
            # 物理的範囲(0.0-1.0)にクリップ
            vwc = max(0.0, min(1.0, vwc))

            data = {
                "vwc_satellite": round(vwc, 3),
                "last_updated": datetime.datetime.now().isoformat(),
                "status": "success"
            }
            
            # Atomic Write
            tmp_file = STATE_FILE + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(data, f)
            os.replace(tmp_file, STATE_FILE)
            print(f"Satellite VWC Updated: {vwc:.3f}")
        else:
            print("No valid satellite data found (clouds?). Keeping old data.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
