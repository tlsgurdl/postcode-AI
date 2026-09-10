import streamlit as st
import pandas as pd
import requests
import time
import re
from io import BytesIO

# ==========================================
# ⚙️ 1. 보안 금고 연동 (API 키 노출 원천 차단)
# ==========================================
# Streamlit Secrets 금고에서 안전하게 키를 호출합니다.
try:
    KAKAO_REST_API_KEY = st.secrets["KAKAO_REST_API_KEY"]
except Exception:
    KAKAO_REST_API_KEY = "키_미설정"

# ==========================================
# 🧠 2. 100% 무인화 핵심 엔진 (소거법 AI 파서)
# ==========================================
def get_kakao_zipcode(address):
    if KAKAO_REST_API_KEY == "키_미설정":
        return "[오류: Streamlit Secrets 키 미등록]"
        
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
            return "[우편번호 누락]"
        return "[검색실패: 없는주소]"
    except Exception:
        return "[API오류]"

def parse_order_block(block_text):
    block_text = block_text.strip()
    if not block_text: return None
    
    phone_pattern = r'(01[016789][-.\s~_*]*\d{3,4}[-.\s~_*]*\d{4})'
    phone_match = re.search(phone_pattern, block_text)
    
    if not phone_match:
        return None
        
    raw_phone = phone_match.group(1)
    clean_phone = re.sub(r'[^0-9]', '', raw_phone)
    if len(clean_phone) == 11:
        phone = f"{clean_phone[:3]}-{clean_phone[3:7]}-{clean_phone[7:]}"
    elif len(clean_phone) == 10:
        phone = f"{clean_phone[:3]}-{clean_phone[3:6]}-{clean_phone[6:]}"
    else:
        phone = raw_phone
        
    text_without_phone = block_text.replace(raw_phone, ' ')
    
    product = ""
    text_without_product = text_without_phone
    if '/' in text_without_phone:
        parts = text_without_phone.rsplit('/', 1)
        text_without_product = parts[0]
        product = parts[1].strip()
        
    clean_text = re.sub(r'[-=+,#/\?:^$.@*\"※~&%ㆍ!』\\‘|\(\)\[\]\<\>`\'…》]', ' ', text_without_product)
    words = [w.strip() for w in clean_text.split() if w.strip()]
    
    name = "[이름확인요망]"
    address_words = []
    addr_keywords = ['서울', '경기', '인천', '강원', '충남', '충북', '경남', '경북', '전남', '전북', '제주', '부산', '대구', '대전', '광주', '울산', '세종', '아파트', '빌라', '오피스텔']
    
    for word in words:
        if re.search(r'\d', word) or any(k in word for k in addr_keywords) or len(word) > 4:
            address_words.append(word)
        elif name == "[이름확인요망]" and 2 <= len(word) <= 4:
            name = word
        else:
            address_words.append(word)
            
    address = " ".join(address_words)
    return {"받는사람": name, "전화번호": phone, "주소": address, "상품명": product}

def parse_multi_line_orders(full_text):
    if not full_text.strip(): return []
    
    phone_pattern = r'(01[016789][-.\s~_*]*\d{3,4}[-.\s~_*]*\d{4})'
    parts = re.split(phone_pattern, full_text)
    if len(parts) < 3: return []
    
    blocks = []
    current_block = parts[0]
    
    for i in range(1, len(parts), 2):
        phone = parts[i]
        text_after = parts[i+1] if i+1 < len(parts) else ""
        split_after = re.split(r'\n\s*\n', text_after, maxsplit=1)
        
        if len(split_after) > 1:
            current_block += " " + phone + " " + split_after[0]
            blocks.append(current_block)
            current_block = split_after[1]
        else:
            current_block += " " + phone + " " + split_after[0]
            
    if current_block.strip():
        blocks.append(current_block)
        
    parsed_data = []
    for block in blocks:
        parsed = parse_order_block(block)
        if parsed: parsed_data.append(parsed)
        
    return parsed_data

# ==========================================
# 🖥️ 3. 웹사이트 UI 화면
# ==========================================
st.set_page_config(page_title="보람한돈 무인 주문소 V6.4", layout="wide")
st.title("🐷 보람한돈 100% 무인 주문 접수처 (보안 금고 탑재)")

password = st.sidebar.text_input("🔒 접속 비밀번호", type="password")
if password != "9155":
    st.warning("사내 비밀번호를 입력해야 가동됩니다.")
    st.stop()
st.sidebar.success("✅ 사내 보안 인증 완료! (API 키 비노출 보호 중)")

st.subheader("📝 카톡/문자 내역 통째로 복사 & 붙여넣기")
st.info("줄바꿈이나 순서 상관없이 주문 내역을 그대로 붙여넣으세요.")
text_input = st.text_area("주문 내역 텍스트를 여기에 붙여넣으세요:", height=300)

if st.button("🚀 택배사 양식으로 자동 변환 시작!", use_container_width=True):
    if not text_input.strip():
        st.error("⚠️ 주문 텍스트를 먼저 입력해 주세요!")
    else:
        with st.spinner("로봇이 주소를 분석하고 택배사 양식을 조립 중입니다..."):
            parsed_data = parse_multi_line_orders(text_input)
            
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
            
            final_data = []
            for i, row in df.iterrows():
                final_data.append({
                    '받는사람': row['받는사람'],
                    '전화번호1': row['전화번호'],
                    '전화번호2': '',
                    '주소': row['주소'],
                    '우편번호': row['우편번호'],
                    '상품명1': row['상품명'],
                    '운임': '',
                    '운임구분': '',
                    '수량(A타입)': '',
                    '배송메시지': '',
                    '보내는사람(지정)': '㈜보람식품',
                    '전화번호1(지정)': '031-985-0031',
                    '주소(지정)': '경기도 김포시 장릉로 74(풍무동)'
                })
            
            final_df = pd.DataFrame(final_data)
            
            st.success("🎉 변환 완료! 아래 표를 확인하세요.")
            st.dataframe(final_df)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Sheet1')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📊 [CJ/롯데/로젠 등] 택배시스템 다이렉트 업로드용 파일 다운로드",
                data=processed_data,
                file_name="보람한돈_택배발송용_최종.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
