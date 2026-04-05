import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import folium
from streamlit_folium import st_folium
import math

# 페이지 설정
st.set_page_config(page_title="TVWS 기기 사용 현황 대시보드", layout="wide")

# 거리 계산 함수 (하버사인 공식)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # 지구의 반지름 (km)
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

# 데이터 로드 및 전처리
@st.cache_data
def load_data(file):
    # 업로드된 파일을 읽어옵니다.
    df = pd.read_csv(file, encoding='utf-8')
    
    # 날짜 데이터 변환 (에러 발생 시 NaT로 처리)
    df['최종 채널사용일'] = pd.to_datetime(df['최종 채널사용일'], errors='coerce')
    
    # 1. 기기 상태 분류
    now = datetime.now()
    twenty_four_hours_ago = now - timedelta(hours=24)
    start_of_2026 = datetime(2026, 1, 1)
    
    def get_status(date):
        if pd.isna(date):
            return '상태불명'
        elif date < start_of_2026:
            return '미사용 (26년 이전)'
        elif date < twenty_four_hours_ago:
            return '주의 (24시간 경과)'
        else:
            return '정상 (사용중)'
            
    df['장비상태'] = df['최종 채널사용일'].apply(get_status)
    
    # 2. 마스터-슬레이브 거리 계산
    coords_dict = df.set_index('기기일련번호')[['최종설치위치좌표(위도)', '최종설치위치좌표(경도)']].to_dict('index')
    
    def calculate_distance(row):
        partner_id = row['통신상대방기기일련번호']
        if pd.notna(partner_id) and partner_id in coords_dict:
            lat1, lon1 = row['최종설치위치좌표(위도)'], row['최종설치위치좌표(경도)']
            lat2, lon2 = coords_dict[partner_id]['최종설치위치좌표(위도)'], coords_dict[partner_id]['최종설치위치좌표(경도)']
            
            if pd.notna(lat1) and pd.notna(lon1) and pd.notna(lat2) and pd.notna(lon2):
                return round(haversine(lat1, lon1, lat2, lon2), 3)
        return None

    df['연결거리(km)'] = df.apply(calculate_distance, axis=1)
    
    return df

# 메인 대시보드 UI
def main():
    st.title("📡 TVWS 가용채널 및 기기 운용 대시보드")
    st.markdown("왼쪽 사이드바에 사이트에서 다운로드하신 **CSV 파일**을 업로드해주시면 대시보드가 자동으로 생성됩니다.")
    
    # 파일 업로더 (GitHub 배포 시 웹 화면에서 파일을 올릴 수 있게 해주는 핵심 코드)
    uploaded_file = st.sidebar.file_uploader("TVWS 통계 CSV 파일 업로드", type=['csv'])
    
    if uploaded_file is not None:
        try:
            df = load_data(uploaded_file)
            
            # --- 상단 요약 KPI ---
            st.markdown("### 📊 전체 기기 운용 요약")
            col1, col2, col3, col4 = st.columns(4)
            
            total_devices = len(df)
            active_devices = len(df[df['장비상태'] == '정상 (사용중)'])
            warning_devices = len(df[df['장비상태'] == '주의 (24시간 경과)'])
            inactive_devices = len(df[df['장비상태'] == '미사용 (26년 이전)'])
            
            col1.metric("전체 등록 기기", f"{total_devices} 대")
            col2.metric("🟢 정상 (24시간 이내)", f"{active_devices} 대")
            col3.metric("🟠 주의 (24시간 경과)", f"{warning_devices} 대")
            col4.metric("🔴 미사용 (26년 이전)", f"{inactive_devices} 대")
            
            # --- 상태별 데이터 탭 ---
            st.markdown("### 📋 상세 데이터 조회")
            tab1, tab2, tab3 = st.tabs(["전체 데이터", "마스터-슬레이브 거리 정보", "지도 위치 보기"])
            
            with tab1:
                st.dataframe(df[['기기일련번호', '기기유형A', '장비상태', '최종 채널사용일', '통신상대방기기일련번호']])
                
            with tab2:
                st.write("마스터와 연결된 슬레이브 기기들의 직선 거리 정보입니다.")
                dist_df = df.dropna(subset=['연결거리(km)'])
                st.dataframe(dist_df[['기기일련번호', '기기유형A', '장비상태', '통신상대방기기일련번호', '연결거리(km)']])
                
            with tab3:
                st.write("최종 설치 위치 좌표를 기반으로 한 기기 위치도입니다.")
                valid_coords = df.dropna(subset=['최종설치위치좌표(위도)', '최종설치위치좌표(경도)'])
                if not valid_coords.empty:
                    center_lat = valid_coords['최종설치위치좌표(위도)'].mean()
                    center_lon = valid_coords['최종설치위치좌표(경도)'].mean()
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                    
                    color_map = {
                        '정상 (사용중)': 'green',
                        '주의 (24시간 경과)': 'orange',
                        '미사용 (26년 이전)': 'red',
                        '상태불명': 'gray'
                    }
                    
                    for idx, row in valid_coords.iterrows():
                        folium.CircleMarker(
                            location=[row['최종설치위치좌표(위도)'], row['최종설치위치좌표(경도)']],
                            radius=5,
                            popup=f"ID: {row['기기일련번호']}<br>상태: {row['장비상태']}<br>유형: {row['기기유형A']}",
                            color=color_map.get(row['장비상태'], 'gray'),
                            fill=True,
                            fill_opacity=0.7
                        ).add_to(m)
                    
                    st_folium(m, width=1000, height=500)
                else:
                    st.warning("유효한 위치 좌표 데이터가 없습니다.")

        except Exception as e:
            st.error(f"데이터를 처리하는 중 오류가 발생했습니다: {e}")
            st.info("파일 형식이 맞는지 다시 한 번 확인해주세요.")
    else:
        st.info("👈 좌측 메뉴에서 다운로드하신 CSV 파일을 드래그해서 올려주세요!")

if __name__ == "__main__":
    main()
