import streamlit as st
import pandas as pd
import requests
import time
import re
import json
import base64
import uuid
from io import BytesIO

# ==========================================
# ⚙️ 1. API 키 세팅 (이사님 환경에 맞게 기입)
# ==========================================
# [우편번호 검색용] 네이버 Maps API 키
NCP_CLIENT_ID = "d9sim98wio"
NCP_CLIENT_SECRET = "NJX9IonEkf4QpwdElne0pmsQgbn4BVdLNhE5lflh"

# [사진 인식용] 네이버 CLOVA OCR 키 (추가 발급 필요)
OCR_SECRET_KEY = "cnltdEtBb1d5aWFubEhhV0pHc3VqSGJWRVhwU0JKTGk="
OCR_INVOKE_URL = "http://clovaocr-api-kr.ncloud.com/external/v1/57843/fd754354ae24c0225b0f571c6ea4457f452f953a0150b27a80f69a3e98d13a77"

# ==========================================
# 🧠 2. 핵심 무인화 엔진 (기능 함수)
# ==========================================
def get_naver_zipcode(address):
    """주소를 던지면 네이버가 우편번호를 반환합니다."""
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
            return "[검색실패: 없는주소]"
    except requests.exceptions.HTTPError as e:
        return f"[API오류: {e.response.status_code}]" # 에러 원인 가시화
    except Exception as e:
        return "[시스템오류]"

def extract_text_via_ocr(image_bytes):
    """수기 송장 사진을 네이버 OCR 서버로 보내 글자를 텍스트로 뽑아옵니다."""
    if not OCR_SECRET_KEY or OCR_SECRET_KEY == "여기에_CLOVA_OCR_SECRET을_넣으세요":
        return "[오류: OCR API 키가 세팅되지 않았습니다.]"
        
    headers = {
        "X-OCR-SECRET": OCR_SECRET_KEY,
        "Content-Type": "application/json"
    }
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(round(time.time() * 1000)),
        "images": [{"format": "jpg", "name": "handwritten_invoice", "data": image_b64}]
    }
    
    try:
        response = requests.post(OCR_INVOKE_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        res_json = response.json()
        # 읽어낸 글자들을 띄어쓰기로 이어 붙여 반환
        texts = [field['inferText'] for field in res_json['images'][0]['fields']]
        return " ".join(texts)
    except Exception as e:
        return f"[OCR 추출 실패: {e}]"

def parse_smart_order_line(line):
    """지능형 텍스트 분석기: 전화번호를 기준으로 이름과 주소를 추적합니다."""
    line = line.strip()
    if not line: return None
    
    # 1. 엑셀에서 복붙하여 탭(\t)으로 구분된 경우 (가장 정확)
    if '\t' in line:
        parts = line.split('\t')
        return {
            "받는사람": parts[0].strip() if len(parts) > 0 else "",
            "전화번호": parts[1].strip() if len(parts) > 1 else "",
            "주소": parts[2].strip() if len(parts) > 2 else "",
            "상품명": parts[3].strip() if len(parts) > 3 else ""
        }
    
    # 2. 중구난방 띄어쓰기 텍스트의 경우 (정규식 추적)
    # 010-1234-5678, 010 1234 5678, 01012345678 등 인식
    phone_pattern = r'(01[016789][-.\s]?\d{3,4}[-.\s]?\d{4})'
    match = re.search(phone_pattern, line)
    
    if match:
        phone = match.group(1).strip()
        # 전화번호 앞은 이름
        name = line[:match.start()].strip()
        # 전화번호 뒤는 나머지 (주소 + 상품명)
        rest = line[match.end():].strip()
        
        # 상품명이 슬래시(/)나 콤마(,)로 명확히 구분되어 있다면 분리, 아니면 주소에 몰빵하여 짤림 방지
        product = ""
        if '/' in rest:
            split_rest = rest.split('/', 1) # 첫 번째 슬래시 기준 1번만 자름
            address = split_rest[0].strip()
            product = split_rest[1].strip()
        else:
            address = rest
            
        return {"받는사람": name, "전화번호": phone, "주소": address, "상품명": product}
    
    # 전화번호 패턴이 없으면 전체를 주소록에 일단 담아둠 (데이터 누락 방지)
    return {"받는사람": "[확인요망]", "전화번호": "", "주소": line, "상품명": ""}

# ==========================================
# 🖥️ 3. 웹사이트 UI 화면
# ==========================================
st.set_page_config(page_title="보람한돈 무인 주문소 V3", layout="wide")
st.title("🐷 보람한돈 100% 무인 주문 접수처 (AI 이미지 판독 탑재)")

# ------------------------------------------
# 업로드 영역
# ------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("📸 1. 수기 송장 사진 업로드")
    st.info("명절 특수! 글씨가 적힌 사진을 올리면 AI가 알아서 읽어냅니다.")
    uploaded_files = st.file_uploader("이미지 첨부", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

with col2:
    st.subheader("📝 2. 카톡/문자 내역 복붙")
    st.info("이름 010-1111-2222 주소 / 상품명 (상품명 앞에는 / 를 붙여주시면 완벽합니다)")
    text_input = st.text_area("텍스트 입력:", height=200)

# ------------------------------------------
# 실행 영역
# ------------------------------------------
if st.button("🚀 데이터 통합 및 우편번호 변환 시작!", use_container_width=True):
    if not text_input.strip() and not uploaded_files:
        st.error("⚠️ 사진을 올리거나 주문 텍스트를 입력해 주세요!")
    else:
        with st.spinner("로봇이 사진을 읽고 주소를 분석 중입니다... (최대 1~2분 소요)"):
            parsed_data = []
            
            # 1. 텍스트 데이터 1차 처리
            if text_input.strip():
                for line in text_input.strip().split('\n'):
                    parsed = parse_smart_order_line(line)
                    if parsed: parsed_data.append(parsed)
            
            # 2. 업로드된 이미지 OCR 처리
            if uploaded_files:
                for img_file in uploaded_files:
                    image_bytes = img_file.read()
                    ocr_text = extract_text_via_ocr(image_bytes)
                    
                    # OCR이 읽어낸 텍스트를 줄바꿈 기준으로 쪼개어 다시 분석
                    # (실제 영수증 형태에 따라 추가 로직이 필요할 수 있으나 기본 방어 로직 적용)
                    if ocr_text and not ocr_text.startswith("[오류"):
                        parsed = parse_smart_order_line(ocr_text)
                        if parsed: parsed_data.append(parsed)
                    else:
                        st.error(f"사진 인식 오류: {ocr_text}")
            
            if not parsed_data:
                st.warning("분석할 수 있는 유효한 주문 데이터가 없습니다.")
                st.stop()
                
            df = pd.DataFrame(parsed_data)
            
            # 3. 네이버 API 우편번호 검색
            zipcodes = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total = len(df)
            for i, addr in enumerate(df['주소']):
                status_text.text(f"우편번호 찾는 중... ({i+1}/{total})")
                zipcodes.append(get_naver_zipcode(addr))
                time.sleep(0.1) # 튕김 방지
                progress_bar.progress((i + 1) / total)
                
            df['우편번호'] = zipcodes
            
            # 열 정렬
            cols = ['받는사람', '전화번호', '우편번호', '주소', '상품명']
            df = df[cols]
            
            st.success("🎉 변환 완료! 아래 표를 확인하세요. 엑셀은 하단 버튼으로 다운로드 가능합니다.")
            st.dataframe(df)
            
            # 엑셀 다운로드 (보안 위해 메모리 버퍼 사용)
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
