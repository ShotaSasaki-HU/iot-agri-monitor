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

# 1. ロード用の座標範囲 (Bounding Box)
AOI_BBOX = {
    "west": 132.724, "south": 34.393,
    "east": 132.733, "north": 34.404,
    "crs": "EPSG:4326"
}

# 2. 集計用の幾何学データ (GeoJSON Polygon)
# aggregate_spatial用に、BBoxの4点を結んだポリゴンを作成します
AOI_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [AOI_BBOX["west"], AOI_BBOX["south"]], # 左下
        [AOI_BBOX["east"], AOI_BBOX["south"]], # 右下
        [AOI_BBOX["east"], AOI_BBOX["north"]], # 右上
        [AOI_BBOX["west"], AOI_BBOX["north"]], # 左上
        [AOI_BBOX["west"], AOI_BBOX["south"]]  # 左下に戻る（閉じる）
    ]]
}

def calculate_optram_vwc(connection):
    """
    openEOサーバー上でOPTRAMを計算し、エリア平均の体積含水率(VWC)を取得する
    """
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=10)

    print(f"Loading collection for period: {start_date} to {end_date}")

    # 1. データロード (Bounding Boxを使用)
    cube = connection.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=AOI_BBOX,
        temporal_extent=[str(start_date), str(end_date)],
        bands=["B04", "B08", "B12", "SCL"],
        max_cloud_cover=60
    )

    # 2. クラウドマスク適用
    scl = cube.band("SCL")
    mask = (scl == 3) | (scl == 8) | (scl == 9) | (scl == 10)
    cube = cube.mask(mask)

    # 3. 時間方向の集約
    composite = cube.reduce_dimension(dimension="t", reducer="median")
    composite = composite / 10000.0

    B04 = composite.band("B04")
    B08 = composite.band("B08")
    B12 = composite.band("B12")

    # 4. OPTRAM計算
    ndvi = (B08 - B04) / (B08 + B04)
    str_val = ((1.0 - B12) ** 2) / (2.0 * B12)

    i_d, s_d = 0.00, 0.16  # Dry Edge
    i_w, s_w = 2.70, 7.10  # Wet Edge
    theta_d, theta_w = 0.05, 0.45 

    str_dry = i_d + (s_d * ndvi)
    str_wet = i_w + (s_w * ndvi)
    W = (str_val - str_dry) / (str_wet - str_dry)

    vwc_cube = W * (theta_w - theta_d) + theta_d

    # 5. 空間集約 (GeoJSON Polygonを使用)
    # ここでエラーが起きていたので、AOI_GEOMETRYを渡すように修正
    mean_vwc = vwc_cube.aggregate_spatial(
        geometries=AOI_GEOMETRY,
        reducer="mean"
    )

    print("Requesting calculation to openEO backend...")
    result_json = mean_vwc.execute()
    
    # デバッグ用に結果を表示
    # print(f"Raw result: {result_json}")

    try:
        # 結果のJSON構造に合わせて値を抽出
        # aggregate_spatialの結果は通常 [[value, ...]] のようなリスト形式で返ってきます
        if isinstance(result_json, list):
            # 最初のポリゴンの、最初の値を抽出 (時系列集約済みなので値は1つのはず)
            val = result_json[0][0]
        else:
            # 辞書型の場合のフォールバック
            val = list(result_json.values())[0]

        if val is None: 
            return None
        return float(val)
    except Exception as e:
        print(f"Parsing Error: {e}, Raw data: {result_json}")
        return 0.25

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
            vwc = max(0.0, min(1.0, vwc))

            data = {
                "vwc_satellite": round(vwc, 3),
                "last_updated": datetime.datetime.now().isoformat(),
                "status": "success"
            }
            
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
