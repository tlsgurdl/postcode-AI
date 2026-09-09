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
# ⚙️ 1. API 키 세팅 
# ==========================================
NCP_CLIENT_ID = "d9sim98wio"
NCP_CLIENT_SECRET = "NJX9IonEkf4QpwdElne0pmsQgbn4BVdLNhE5lflh"

OCR_SECRET_KEY = "cnltdEtBb1d5aWFubEhhV0pHc3VqSGJWRVhwU0JKTGk="
OCR_INVOKE_URL = "https://mnq7p7qzj1.apigw.ntruss.com/custom/v1/57843/fd754354ae24c0225b0f571c6ea4457f452f953a0150b27a80f69a3e98d13a77/general"

# ==========================================
# 🧠 2. 100% 무인화 핵심 엔진
# ==========================================
def get_naver_zipcode(address):
    """네이버 Geocoding API로 우편번호 검색 (401 에러 방어 포함)"""
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
        # 401 에러 발생 시 실무자가 직관적으로 원인을 알 수 있도록 표시
        if e.response.status_code == 401:
            return "[API 401오류: Geocoding 서비스 신청 및 키 확인 요망]"
        return f"[API오류: {e.response.status_code}]"
    except Exception as e:
        return "[시스템오류]"

def extract_text_via_ocr(image_bytes):
    """수기 송장 사진 OCR 판독"""
    if not OCR_SECRET_KEY or "여기에" in OCR_SECRET_KEY:
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
        texts = [field['inferText'] for field in res_json['images'][0]['fields']]
        return " ".join(texts)
    except Exception as e:
        return f"[OCR 추출 실패: {e}]"

def parse_smart_order_line(line):
    """지능형 텍스트 분석기 (상품명 유무 및 기호 오류 완벽 방어)"""
    line = line.strip()
    if not line: return None
    
    phone_pattern = r'(01[016789][-.\s]?\d{3,4}[-.\s]?\d{4})'
    match = re.search(phone_pattern, line)
    
    if match:
        phone = match.group(1).strip()
        name = line[:match.start()].strip()
        
        # 전화번호 뒷부분(주소+상품명 후보) 추출 후 앞쪽에 잘못 붙은 특수기호 청소
        rest = line[match.end():].strip()
        rest = re.sub(r'^[/,-]\s*', '', rest) 
        
        # 상품명이 없을 수도 있다는 엣지 케이스 방어
        # 뒤에서부터 검색하여 마지막 슬래시(/)를 기준으로 주소와 상품명을 분리
        if '/' in rest:
            parts = rest.rsplit('/', 1)
            address = parts[0].strip()
            product = parts[1].strip()
        else:
            # 슬래시가 아예 없으면 전부 '주소'로 몰아넣어 주소 잘림 및 오배송 원천 차단
            address = rest
            product = ""
            
        return {"받는사람": name, "전화번호": phone, "주소": address, "상품명": product}
    
    # 전화번호가 없으면 엑셀 데이터 누락을 막기 위해 전체를 주소 칸에 임시 보관
    return {"받는사람": "[확인요망]", "전화번호": "", "주소": line, "상품명": ""}

# ==========================================
# 🖥️ 3. 웹사이트 UI 화면
# ==========================================
st.set_page_config(page_title="보람한돈 무인 주문소 V3.1", layout="wide")
st.title("🐷 보람한돈 100% 무인 주문 접수처 (AI 텍스트 방어 탑재)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📸 1. 수기 송장 사진 업로드")
    st.info("명절 특수! 글씨가 적힌 사진을 올리면 AI가 읽어냅니다.")
    uploaded_files = st.file_uploader("이미지 첨부", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

with col2:
    st.subheader("📝 2. 카톡/문자 내역 복붙")
    st.info("이름 010-1111-2222 주소 (상품명이 있다면 끝에 / 삼겹살 500g)")
    text_input = st.text_area("텍스트 입력:", height=200)

if st.button("🚀 데이터 통합 및 우편번호 변환 시작!", use_container_width=True):
    if not text_input.strip() and not uploaded_files:
        st.error("⚠️ 사진을 올리거나 주문 텍스트를 입력해 주세요!")
    else:
        with st.spinner("로봇이 데이터를 완벽하게 분석 중입니다..."):
            parsed_data = []
            
            if text_input.strip():
                for line in text_input.strip().split('\n'):
                    parsed = parse_smart_order_line(line)
                    if parsed: parsed_data.append(parsed)
            
            if uploaded_files:
                for img_file in uploaded_files:
                    image_bytes = img_file.read()
                    ocr_text = extract_text_via_ocr(image_bytes)
                    
                    if ocr_text and not ocr_text.startswith("[오류"):
                        parsed = parse_smart_order_line(ocr_text)
                        if parsed: parsed_data.append(parsed)
                    else:
                        st.error(f"사진 인식 오류: {ocr_text}")
            
            if not parsed_data:
                st.warning("분석할 수 있는 유효한 주문 데이터가 없습니다.")
                st.stop()
                
            df = pd.DataFrame(parsed_data)
            zipcodes = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total = len(df)
            for i, addr in enumerate(df['주소']):
                status_text.text(f"우편번호 찾는 중... ({i+1}/{total})")
                zipcodes.append(get_naver_zipcode(addr))
                time.sleep(0.1) 
                progress_bar.progress((i + 1) / total)
                
            df['우편번호'] = zipcodes
            
            cols = ['받는사람', '전화번호', '우편번호', '주소', '상품명']
            df = df[cols]
            
            st.success("🎉 변환 완료! 아래 표를 확인하세요.")
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
