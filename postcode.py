import streamlit as st
import pandas as pd
import requests
import time
import re
from io import BytesIO

# ==========================================
# ⚙️ 1. API 키 세팅
# ==========================================
# [우편번호] 카카오 REST API 키 (이것만 있으면 평생 무료!)
KAKAO_REST_API_KEY = "6e8d0ef74f5ae0a2f74769058235b074"

# ==========================================
# 🧠 2. 100% 무인화 핵심 엔진 (텍스트 정제 & 주소 검색)
# ==========================================
def get_kakao_zipcode(address):
    """카카오 로컬 API로 우편번호 검색"""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {"query": address}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        result = response.json()
        if result['documents']:
            doc = result['documents'][0]
            if doc.get('road_address') and doc['road_address'].get('zone_no'):
                return doc['road_address']['zone_no']
            elif doc.get('address') and doc['address'].get('zip_code'):
                return doc['address']['zip_code']
            else:
                return "[우편번호 누락]"
        else:
            return "[검색실패: 없는주소]"
    except Exception:
        return "[API오류]"

def parse_smart_order_line(line):
    """지능형 텍스트 분석기 (순번 제거 및 띄어쓰기 오류 교정)"""
    line = line.strip()
    if not line: return None
    
    phone_pattern = r'(01[016789][-.\s]*\d{3,4}[-.\s]*\d{4})'
    match = re.search(phone_pattern, line)
    
    if match:
        raw_phone = match.group(1)
        phone = re.sub(r'\s+', '', raw_phone) # 전화번호 안의 공백 싹 제거
        
        name_part = line[:match.start()].strip()
        name = re.sub(r'^\d+[\s.]*', '', name_part) # 이름 앞의 순번 깔끔하게 제거
        
        rest = line[match.end():].strip()
        rest = re.sub(r'^[/,-]\s*', '', rest) 
        
        if '/' in rest:
            parts = rest.rsplit('/', 1)
            address = parts[0].strip()
            product = parts[1].strip()
        else:
            address = rest
            product = ""
            
        return {"받는사람": name, "전화번호": phone, "주소": address, "상품명": product}
    
    return {"받는사람": "[확인요망]", "전화번호": "", "주소": line, "상품명": ""}

# ==========================================
# 🖥️ 3. 웹사이트 UI 화면 (초경량 디자인)
# ==========================================
st.set_page_config(page_title="보람한돈 무인 주문소 V5.0", layout="wide")
st.title("🐷 보람한돈 100% 무인 주문 접수처 (초경량 텍스트 전용)")

st.subheader("📝 카톡/문자 내역 복사 & 붙여넣기")
st.info("이름 010-1111-2222 주소 (상품명이 있다면 끝에 / 삼겹살 500g)")
text_input = st.text_area("카톡이나 문자로 받은 주문 내역, 또는 카리나가 정제해준 텍스트를 여기에 붙여넣으세요:", height=300)

if st.button("🚀 데이터 통합 및 우편번호 변환 시작!", use_container_width=True):
    if not text_input.strip():
        st.error("⚠️ 주문 텍스트를 먼저 입력해 주세요!")
    else:
        with st.spinner("로봇이 주소를 분석하여 카카오에서 우편번호를 찾는 중입니다..."):
            parsed_data = []
            
            for line in text_input.strip().split('\n'):
                parsed = parse_smart_order_line(line)
                if parsed: parsed_data.append(parsed)
            
            if not parsed_data:
                st.warning("분석할 수 있는 유효한 주문 데이터가 없습니다.")
                st.stop()
                
            df = pd.DataFrame(parsed_data)
            zipcodes = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total = len(df)
            for i, addr in enumerate(df['주소']):
                if len(addr) < 5:
                    zipcodes.append("[확인요망]")
                else:
                    status_text.text(f"카카오에서 우편번호 찾는 중... ({i+1}/{total})")
                    zipcodes.append(get_kakao_zipcode(addr))
                time.sleep(0.1) 
                progress_bar.progress((i + 1) / total)
                
            df['우편번호'] = zipcodes
            
            cols = ['받는사람', '전화번호', '우편번호', '주소', '상품명']
            df = df[cols]
            
            st.success("🎉 완벽하게 변환이 완료되었습니다! 엑셀로 다운로드하세요.")
            st.dataframe(df)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='택배발송용')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📊 택배사 업로드용 엑셀 다운로드",
                data=processed_data,
                file_name="보람한돈_주문취합본.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
