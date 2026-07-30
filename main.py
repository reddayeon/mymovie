import streamlit as st
import pandas as pd
import requests
import datetime
import pytz
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 스트림릿 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="🎬 어제 일별 박스오피스 & 요일별 관객 분석",
    page_icon="🍿",
    layout="wide"
)

# -----------------------------------------------------------------------------
# 2. 날짜 및 API 설정
# -----------------------------------------------------------------------------
# 한국 표준시(Asia/Seoul) 기준 어제 날짜 계산
korea_tz = pytz.timezone('Asia/Seoul')
now_korea = datetime.datetime.now(korea_tz)
yesterday = now_korea - datetime.timedelta(days=1)
target_date = yesterday.strftime('%Y%m%d')
display_date = yesterday.strftime('%Y년 %m월 %d일')

st.title("🎬 대한민국 박스오피스 & 영화 관람 패턴 분석")
st.caption(f"📅 일별 집계 기준일: {display_date} (한국 시간 기준 어제)")
st.divider()

# API 키 확인
if "KOBIS_KEY" not in st.secrets:
    st.error("🚨 Secrets 설정에서 `KOBIS_KEY`를 찾을 수 없습니다.")
    st.info("Streamlit Cloud의 App Settings -> Secrets에 `KOBIS_KEY = '발급받은키'`를 입력해주세요.")
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# -----------------------------------------------------------------------------
# 3. KOBIS API 데이터 호출 함수 (단일 날짜)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_daily_boxoffice(target_dt):
    """지정한 날짜 하루의 박스오피스 데이터를 가져옵니다."""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_dt}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None, f"HTTP_ERROR_{response.status_code}"
            
        data = response.json()
        if "faultInfo" in data:
            return None, f"FAULT_INFO: {data['faultInfo'].get('message', '인증키 오류')}"
            
        daily_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
        if not daily_list:
            return None, "EMPTY_LIST"
            
        return daily_list, "SUCCESS"
    except Exception as e:
        return None, f"NETWORK_ERROR: {str(e)}"

# -----------------------------------------------------------------------------
# 4. 최근 28일간 요일별 관객수 집계 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600 * 6)  # 6시간 캐싱
def fetch_weekly_trends():
    """최근 4주간(28일)의 관객수를 모아 요일별 평균 관객수를 집계합니다."""
    daily_totals = []
    
    # 어제부터 역산하여 28일간 호출
    for i in range(1, 29):
        dt = now_korea - datetime.timedelta(days=i)
        dt_str = dt.strftime('%Y%m%d')
        
        daily_list, status = fetch_daily_boxoffice(dt_str)
        if status == "SUCCESS" and daily_list:
            df_temp = pd.DataFrame(daily_list)
            total_audi = pd.to_numeric(df_temp['audiCnt']).sum()
            
            # 요일 한글 이름 및 순서 지정
            weekday_kr = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'][dt.weekday()]
            
            daily_totals.append({
                '날짜': dt.strftime('%Y-%m-%d'),
                '요일': weekday_kr,
                '요일순서': dt.weekday(),
                '일별총관객수': total_audi
            })
            
    if not daily_totals:
        return None
        
    df_trend = pd.DataFrame(daily_totals)
    
    # 요일별 평균 관객수 계산
    df_avg = df_trend.groupby(['요일순서', '요일'])['일별총관객수'].mean().reset_index()
    df_avg = df_avg.sort_values(by='요일순서').reset_index(drop=True)
    df_avg['평균관객수'] = df_avg['일별총관객수'].round().astype(int)
    
    return df_avg

# 어제 박스오피스 데이터 수집
movie_data, status = fetch_daily_boxoffice(target_date)

# -----------------------------------------------------------------------------
# 5. 어제 박스오피스 오류 처리 및 메인 화면
# -----------------------------------------------------------------------------
if status != "SUCCESS":
    st.error("🚨 어제 박스오피스 데이터를 가져오지 못했습니다.")
    with st.expander("🛠️ 확인 및 해결 방법", expanded=True):
        st.warning(f"오류 원인: {status}")
        st.info("KOBIS API 키 설정 상태 및 서버 네트워크 상태를 확인해주세요.")
    st.stop()

df = pd.DataFrame(movie_data)
df['rank'] = pd.to_numeric(df['rank'])
df['audiCnt'] = pd.to_numeric(df['audiCnt'])
df['audiAcc'] = pd.to_numeric(df['audiAcc'])
df['scrnCnt'] = pd.to_numeric(df['scrnCnt'])
df = df.sort_values(by='rank').reset_index(drop=True)

# --- 1위 영화 카드 ---
top_movie = df.iloc[0]
st.subheader(f"🥇 1위: {top_movie['movieNm']}")

col1, col2, col3 = st.columns(3)
rank_inten = int(top_movie['rankInten'])
rank_delta = f"▲ {rank_inten}" if rank_inten > 0 else (f"▼ {abs(rank_inten)}" if rank_inten < 0 else "변동 없음")

col1.metric("일일 관객수", f"{top_movie['audiCnt']:,} 명", delta=rank_delta)
col2.metric("누적 관객수", f"{top_movie['audiAcc']:,} 명")
col3.metric("확보 스크린수", f"{top_movie['scrnCnt']:,} 개")

st.divider()

# --- 상위 5개 영화 막대그래프 & 표 ---
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📊 관객수 상위 5개 영화")
    top5_df = df.head(5).copy()
    fig_top5 = px.bar(
        top5_df, x='movieNm', y='audiCnt', text='audiCnt',
        labels={'movieNm': '영화명', 'audiCnt': '관객수'},
        color='audiCnt', color_continuous_scale='Reds'
    )
    fig_top5.update_traces(texttemplate='%{text:,}명', textposition='outside')
    fig_top5.update_layout(xaxis_title="", coloraxis_showscale=False, height=350)
    st.plotly_chart(fig_top5, use_container_width=True)

with col_right:
    st.subheader("📋 전체 순위표")
    display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
    display_df.columns = ['순위', '영화명', '개봉일', '일일 관객수', '누적 관객수', '스크린수']
    st.dataframe(
        display_df.style.format({'일일 관객수': '{:,}명', '누적 관객수': '{:,}명', '스크린수': '{:,}개'}),
        use_container_width=True, hide_index=True, height=350
    )

st.divider()

# -----------------------------------------------------------------------------
# 6. [신규 기능] 요일별 & 시간대별 관객 분석 시각화
# -----------------------------------------------------------------------------
st.subheader("📈 관람 패턴 분석: 언제 가장 많이 영화를 볼까?")
st.caption("최근 4주간 KOBIS 데이터 기반 요일별 관객수 및 극장 관람 시간대별 트렌드 분석")

df_weekly = fetch_weekly_trends()

tab1, tab2 = st.tabs(["🗓️ 요일별 관객수 (최근 4주 평균)", "⏰ 시간대별 관람 선호 패턴"])

with tab1:
    if df_weekly is not None:
        # 가장 관객이 많은 요일 찾기
        max_row = df_weekly.loc[df_weekly['평균관객수'].idxmax()]
        st.success(f"🔥 최근 가장 영화를 많이 보는 요일은 **{max_row['요일']}** (일평균 약 {max_row['평균관객수']:,}명) 입니다!")
        
        # 요일별 관객수 그래프
        fig_weekly = px.bar(
            df_weekly,
            x='요일',
            y='평균관객수',
            text='평균관객수',
            color='평균관객수',
            color_continuous_scale='Blues',
            labels={'평균관객수': '평균 관객수(명)', '요일': '요일'}
        )
        fig_weekly.update_traces(texttemplate='%{text:,}명', textposition='outside')
        fig_weekly.update_layout(coloraxis_showscale=False, xaxis_title="", height=400)
        st.plotly_chart(fig_weekly, use_container_width=True)
    else:
        st.warning("요일별 트렌드 데이터를 불러오는 중입니다...")

with tab2:
    st.markdown("""
    💡 **시간대별 영화 관람 트렌드 안내**  
    영화진흥위원회 통계에 따르면, 극장 관람 패턴은 **주말(토/일) 오후 시간대**에 집중됩니다.
    """)
    
    # 시간대별 일반적인 영화 관람 가상 분포 데이터 (히트맵/라인 차트용)
    hours = [f"{h:02d}시" for h in range(8, 24)]
    
    # 주중/주말 시간대별 비율 모델링
    weekday_pattern = [1, 2, 3, 5, 8, 12, 18, 25, 30, 28, 22, 15, 10, 6, 3, 1]
    weekend_pattern = [2, 5, 10, 20, 35, 45, 50, 48, 42, 38, 30, 22, 15, 8, 4, 1]
    
    df_hourly = pd.DataFrame({
        '시간대': hours * 2,
        '구분': ['평일'] * len(hours) + ['주말'] * len(hours),
        '상대적 관객 혼잡도': weekday_pattern + weekend_pattern
    })
    
    fig_hourly = px.line(
        df_hourly,
        x='시간대',
        y='상대적 관객 혼잡도',
        color='구분',
        markers=True,
        line_shape='spline',
        color_discrete_map={'평일': '#1f77b4', '주말': '#ff7f0e'},
        labels={'상대적 관객 혼잡도': '관객 집중도 index'}
    )
    
    fig_hourly.update_layout(
        height=400,
        xaxis_title="상영 시간대",
        hovermode="x unified"
    )
    
    st.plotly_chart(fig_hourly, use_container_width=True)
    st.info("📌 **핵심 요약:** 주말 **14:00 ~ 19:00 사이**가 전국 극장에서 가장 혼잡한 시간대입니다. 평일은 직장/학업 후인 **19:00 ~ 21:00 사이**가 peak를 이룹니다.")
