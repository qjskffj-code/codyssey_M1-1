"""OECD 소비자물가지수(CPI) 수집 스크립트.

실행: python collect_data.py
결과:
  data/raw/oecd_coicop1999.csv   OECD API 원본 응답 (COICOP 1999 데이터셋)
  data/raw/oecd_coicop2018.csv   OECD API 원본 응답 (COICOP 2018 데이터셋, 일본용)
  data/cpi_monthly.csv           분석용으로 정리한 월별 지수 (long format)

데이터 출처: OECD Data Explorer - Consumer price indices (CPIs, HICPs)
  https://data-explorer.oecd.org/
라이선스: OECD 데이터는 CC BY 4.0으로 제공되며, 사용 시 출처(OECD)를 표기해야 한다.
"""

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://sdmx.oecd.org/public/rest/data"
START_PERIOD = "2014-01"  # 2015년 1월의 전년동월대비 상승률을 구하려면 2014년 데이터가 필요

# 항목 코드 (COICOP 분류)
CATEGORIES = {
    "CP11": "restaurants_hotels",  # 음식 및 숙박 (외식 물가의 대리 지표)
    "CP01": "food",                # 식료품 및 비주류 음료
    "CP045": "energy",             # 전기, 가스 및 기타 연료
    "_T": "all_items",             # 전체 CPI
}

# 나라별로 최신 데이터가 이어지는 데이터셋이 다르다.
# 일본은 COICOP 1999 데이터셋이 2021-06에서 끝나서 COICOP 2018 데이터셋을 쓴다.
DATASETS = {
    "coicop1999": {
        "flow": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
        "countries": ["KOR", "USA", "GBR", "DEU", "FRA"],
    },
    "coicop2018": {
        "flow": "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0",
        "countries": ["JPN"],
    },
}

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"


def fetch_oecd(flow: str, countries: list[str]) -> pd.DataFrame:
    """OECD SDMX API에서 월별 CPI 지수(원계열, 계절조정 없음)를 CSV로 받아온다."""
    # 키 순서: 국가.주기.방법론.측정.단위.항목.계절조정.변환
    key = f"{'+'.join(countries)}.M.N.CPI.IX.{'+'.join(CATEGORIES)}.N._Z"
    url = f"{BASE_URL}/{flow}/{key}"
    response = requests.get(
        url, params={"startPeriod": START_PERIOD, "format": "csv"}, timeout=120
    )
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))


def tidy(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    """분석에 필요한 컬럼만 남기고 이름을 정리한다."""
    df = raw[["REF_AREA", "EXPENDITURE", "TIME_PERIOD", "OBS_VALUE", "BASE_PER"]].rename(
        columns={
            "REF_AREA": "country",
            "EXPENDITURE": "category",
            "TIME_PERIOD": "date",
            "OBS_VALUE": "index",
            "BASE_PER": "base_period",
        }
    )
    df["category"] = df["category"].map(CATEGORIES)
    df["date"] = pd.to_datetime(df["date"])
    df["source"] = f"OECD {source}"
    return df


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    frames = []
    for name, spec in DATASETS.items():
        raw = fetch_oecd(spec["flow"], spec["countries"])
        raw.to_csv(RAW_DIR / f"oecd_{name}.csv", index=False)
        print(f"[{name}] {len(raw)}행 수집")
        frames.append(tidy(raw, name))

    cpi = pd.concat(frames).sort_values(["country", "category", "date"])
    cpi.to_csv(DATA_DIR / "cpi_monthly.csv", index=False)

    # 수집 결과 요약: 나라/항목별 데이터 수와 기간
    summary = cpi.groupby(["country", "category"])["date"].agg(["count", "min", "max"])
    print(summary)


if __name__ == "__main__":
    main()
