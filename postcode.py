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
# [우편번호] 카카오 REST API 키
KAKAO_REST_API_KEY = "6e8d0ef74f5ae0a2f74769058235b074"

# [사진판독] 네이버 CLOVA OCR 키
OCR_SECRET_KEY = "cnltdEtBb1d5aWFubEhhV0pHc3VqSGJWRVhwU0JKTGk="
OCR_INVOKE_URL = "https://mnq7p7qzj1.apigw.ntruss.com/custom/v1/57843/fd754354ae24c0225b0f571c6ea4457f452f953a0150b27a80f69a3e98d13a77/general"

# ==========================================
# 🧠 2. 100% 무인화 핵심 엔진
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

def extract_text_via_ocr(image_bytes):
    """(업그레이드) Y좌표 기반 줄바꿈 자동 복원 엔진 탑재"""
    if not OCR_SECRET_KEY or "여기에" in OCR_SECRET_KEY:
        return "[오류: OCR API 키 세팅 안됨]"
        
    headers = {"X-OCR-SECRET": OCR_SECRET_KEY, "Content-Type": "application/json"}
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    payload = {
        "version": "V2", "requestId": str(uuid.uuid4()), "timestamp": int(round(time.time() * 1000)),
        "images": [{"format": "jpg", "name": "handwritten_invoice", "data": image_b64}]
    }
    
    try:
        response = requests.post(OCR_INVOKE_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        res_json = response.json()
        fields = res_json['images'][0]['fields']
        
        if not fields: return ""

        # 1. 글자 박스들의 평균 높이를 계산하여 동적 오차 범위 설정
        total_height = sum([abs(f['boundingPoly']['vertices'][2]['y'] - f['boundingPoly']['vertices'][0]['y']) for f in fields])
        avg_height = total_height / len(fields)
        y_threshold = avg_height * 0.5  # 높이의 50% 이내면 '같은 줄'로 인식
        
        # 2. Y좌표(높낮이) 기준으로 글자들 그룹화 묶기
        lines_dict = {}
        for field in fields:
            text = field['inferText']
            v = field['boundingPoly']['vertices']
            y_center = sum([pt.get('y', 0) for pt in v]) / 4
            x_center = sum([pt.get('x', 0) for pt in v]) / 4
            
            placed = False
            for line_y in lines_dict.keys():
                if abs(line_y - y_center) < y_threshold:
                    lines_dict[line_y].append((x_center, text))
                    placed = True
                    break
            if not placed:
                lines_dict[y_center] = [(x_center, text)]
                
        # 3. Y좌표 오름차순(위에서 아래), X좌표 오름차순(왼쪽에서 오른쪽) 정렬 후 텍스트 복원
        sorted_y = sorted(lines_dict.keys())
        ocr_lines = []
        for y in sorted_y:
            sorted_line = sorted(lines_dict[y], key=lambda item: item[0])
            line_text = " ".join([item[1] for item in sorted_line])
            ocr_lines.append(line_text)
            
        return "\n".join(ocr_lines) # 한 줄씩 이쁘게 떨어지게 반환
    except Exception as e:
        return f"[OCR 추출 실패: {e}]"

def parse_smart_order_line(line):
    """지능형 텍스트 분석기 (순번 제거 및 띄어쓰기 오류 교정)"""
    line = line.strip()
    if not line: return None
    
    # 전화번호 패턴 (010- 4303-9782 같이 띄어쓰기가 엉망이어도 잡아냄)
    phone_pattern = r'(01[016789][-.\s]*\d{3,4}[-.\s]*\d{4})'
    match = re.search(phone_pattern, line)
    
    if match:
        raw_phone = match.group(1)
        phone = re.sub(r'\s+', '', raw_phone) # 전화번호 안의 공백 싹 제거
        
        name_part = line[:match.start()].strip()
        name = re.sub(r'^\d+[\s.]*', '', name_part) # 이름 앞의 순번(1, 2, 3...) 깔끔하게 제거
        
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
# 🖥️ 3. 웹사이트 UI 화면
# ==========================================
st.set_page_config(page_title="보람한돈 무인 주문소 V4.1", layout="wide")
st.title("🐷 보람한돈 100% 무인 주문 접수처 (공간지각 OCR 탑재)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📸 1. 수기 송장 사진 업로드")
    st.info("명절 특수! 표나 리스트 형태의 사진을 올리면 AI가 줄바꿈을 복원해 읽어냅니다.")
    uploaded_files = st.file_uploader("이미지 첨부", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

with col2:
    st.subheader("📝 2. 카톡/문자 내역 복붙")
    st.info("이름 010-1111-2222 주소 (상품명이 있다면 끝에 / 삼겹살 500g)")
    text_input = st.text_area("텍스트 입력:", height=200)

if st.button("🚀 데이터 통합 및 우편번호 변환 시작!", use_container_width=True):
    if not text_input.strip() and not uploaded_files:
        st.error("⚠️ 사진을 올리거나 주문 텍스트를 입력해 주세요!")
    else:
        with st.spinner("로봇이 사진의 표 구조를 분석하여 주소를 찾는 중입니다..."):
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
                        # 줄바꿈 복원된 텍스트를 한 줄씩 쪼개서 분석기에 넣음
                        for ocr_line in ocr_text.split('\n'):
                            parsed = parse_smart_order_line(ocr_line)
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
                # 주소가 너무 짧거나 빈칸이면 검색 스킵
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
            
            st.success("🎉 완벽하게 줄이 맞춰진 변환이 완료되었습니다! 엑셀로 다운로드하세요.")
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
