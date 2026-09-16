"""한국 외식 물가의 원가 요인 데이터 수집 스크립트.

실행: python collect_cost_drivers.py
결과:
  data/cost_drivers_monthly.csv   국제 유가·환율·세계 식료품 가격 (월별)
  data/kor_minimum_wage.csv       한국 최저임금 (연간)

왜 이 지표들인가:
  한국의 전기·가스 요금(CP045)은 정부가 인상 시점을 조절하기 때문에 국제 에너지
  가격을 곧바로 반영하지 않는다. 그래서 요금 규제의 영향을 받지 않는 지표
  (국제 유가, 세계 식료품 가격)를 원화로 환산해 외식 물가와 비교한다.
  인건비는 리포트에서 가설로만 언급했던 요인이라 최저임금을 함께 받는다.

데이터 출처:
  - 국제 유가(브렌트유), 원/달러 환율, IMF 세계 식료품 가격지수: FRED (미국 세인트루이스 연준)
    https://fred.stlouisfed.org/  (인증키 불필요)
  - 한국 최저임금: OECD Data Explorer, Minimum wages at current prices (NCU)
    https://data-explorer.oecd.org/  (인증키 불필요, CC BY 4.0)
"""

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
OECD_MW_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.ELS.SAE,DSD_EARNINGS@MW_CURP,/KOR......"
)
START = "2014-01-01"

# FRED 시리즈 ID와 설명
FRED_SERIES = {
    "MCOILBRENTEU": ("brent_usd", "브렌트유 현물가격 (달러/배럴)"),
    "EXKOUS": ("usdkrw", "원/달러 환율 (월평균)"),
    "PFOODINDEXM": ("food_index_usd", "IMF 세계 식료품 가격지수 (2016=100, 달러 기준)"),
}

DATA_DIR = Path("data")


def fetch_fred(series_id: str) -> pd.Series:
    response = requests.get(FRED_URL, params={"id": series_id}, timeout=120)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text), parse_dates=["observation_date"])
    frame = frame.rename(columns={"observation_date": "date", series_id: "value"})
    # FRED는 결측을 "."으로 표시한다
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.set_index("date")["value"].dropna()


def fetch_minimum_wage() -> pd.DataFrame:
    response = requests.get(OECD_MW_URL, params={"startPeriod": "2014", "format": "csv"}, timeout=120)
    response.raise_for_status()
    raw = pd.read_csv(StringIO(response.text))
    # 같은 최저임금을 시급·일급·월급·연봉으로 모두 제공하므로 시급(H)만 남긴다
    hourly = raw[raw["PAY_PERIOD"] == "H"]
    wage = hourly[["TIME_PERIOD", "OBS_VALUE"]].rename(
        columns={"TIME_PERIOD": "year", "OBS_VALUE": "hourly_krw"}
    ).sort_values("year").reset_index(drop=True)
    wage["yoy_pct"] = wage["hourly_krw"].pct_change() * 100
    return wage


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    monthly = {}
    for series_id, (name, description) in FRED_SERIES.items():
        series = fetch_fred(series_id)
        monthly[name] = series
        print(f"[{name}] {len(series)}개월, {series.index.min():%Y-%m} ~ {series.index.max():%Y-%m}  # {description}")

    drivers = pd.DataFrame(monthly).loc[START:]
    # 원화 기준 수입 원가: 국제 가격이 올라도 환율이 내리면 국내 부담은 덜하다
    drivers["brent_krw"] = drivers["brent_usd"] * drivers["usdkrw"]
    drivers["food_index_krw"] = drivers["food_index_usd"] * drivers["usdkrw"]
    drivers.index.name = "date"
    drivers.round(4).to_csv(DATA_DIR / "cost_drivers_monthly.csv")
    print(f"\ndata/cost_drivers_monthly.csv 저장: {len(drivers)}행")
    print(drivers.tail(3).round(1).to_string())

    wage = fetch_minimum_wage()
    wage.round(2).to_csv(DATA_DIR / "kor_minimum_wage.csv", index=False)
    print(f"\ndata/kor_minimum_wage.csv 저장: {len(wage)}행")
    print(wage.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
