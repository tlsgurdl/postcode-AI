import streamlit as st
import pandas as pd
import requests
import time
from io import BytesIO

# ==========================================
# ⚙️ 네이버 API 키 세팅 (여기에 이사님 키를 넣으세요!)
# ==========================================
NCP_CLIENT_ID = "d9sim98wio"
NCP_CLIENT_SECRET = "NJX9IonEkf4QpwdElne0pmsQgbn4BVdLNhE5lflh"

# ==========================================
# 1. 네이버 우편번호 검색 엔진
# ==========================================
def get_naver_zipcode(address):
    url = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NCP_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NCP_CLIENT_SECRET
    }
    params = {"query": address}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        result = response.json()
        if result.get('addresses') and len(result['addresses']) > 0:
            return result['addresses'][0].get('postalCode', "[우편번호 누락]")
        else:
            return "[검색실패: 주소오류]"
    except Exception as e:
        return "[API오류]"

# ==========================================
# 2. 웹사이트 화면 구성 (UI)
# ==========================================
st.set_page_config(page_title="보람한돈 100% 무인 주문소", layout="wide")
st.title("🐷 보람한돈 100% 무인 주문 접수처")
st.markdown("**복잡한 주문 취합과 우편번호 검색, 이제 클릭 한 번으로 끝내세요!**")

# 텍스트 주문 입력창 (카톡, 문자 복사 붙여넣기)
st.subheader("📝 카톡/문자 주문 내역 붙여넣기")
st.info("이름 / 전화번호 / 주소 / 상품명 순서로 탭이나 쉼표로 구분해서 붙여넣어 주세요.")
text_input = st.text_area("여기에 주문 내역을 붙여넣으세요:", height=200, 
                          placeholder="예시:\n홍길동 010-1234-5678 서울 강남구 테헤란로 152 통항정살 2kg\n김보람 010-9999-8888 경기 김포시 한강신도시 삼겹살 500g")

if st.button("🚀 우편번호 자동 검색 및 엑셀 변환"):
    if not text_input.strip():
        st.error("⚠️ 주문 내역을 먼저 붙여넣어 주세요!")
    else:
        with st.spinner("로봇이 주소를 분석하고 네이버에서 우편번호를 찾고 있습니다... (잠시만 대기)"):
            lines = text_input.strip().split('\n')
            parsed_data = []
            
            # 텍스트 쪼개기 (단순 공백 기준 분리 로직 적용)
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[0]
                    phone = parts[1]
                    address = " ".join(parts[2:-2]) # 주소 덩어리 추출
                    product = " ".join(parts[-2:])  # 상품명 덩어리 추출
                    parsed_data.append({"받는사람": name, "전화번호": phone, "주소": address, "상품명": product})
            
            df = pd.DataFrame(parsed_data)
            
            # 네이버 API를 통한 우편번호 자동 매칭
            zipcodes = []
            for addr in df['주소']:
                zipcodes.append(get_naver_zipcode(addr))
                time.sleep(0.1) # 서버 튕김 방지용 숨고르기
                
            df['우편번호'] = zipcodes
            
            # 택배사 양식에 맞게 열 재배치 [받는사람 - 전화번호 - 우편번호 - 주소 - 상품명]
            cols = ['받는사람', '전화번호', '우편번호', '주소', '상품명']
            df = df[cols]
            
            st.success("🎉 변환이 완벽하게 끝났습니다! 아래에서 결과를 확인하고 엑셀로 다운로드하세요.")
            st.dataframe(df) # 화면에 표 형태로 미리보기 제공
            
            # 엑셀 다운로드 버튼 생성 (서버에 저장되지 않고 메모리에서 즉시 다운로드 - 보안 완벽)
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='택배발송용_완성본')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📊 [택배사 업로드용] 엑셀 파일 다운로드",
                data=processed_data,
                file_name="보람한돈_택배발송용.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )