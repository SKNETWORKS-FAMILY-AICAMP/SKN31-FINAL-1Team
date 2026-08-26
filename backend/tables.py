# backend/tables.py

import pandas as pd
import json

# JSON 파일 로드
with open('users_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Django dumpdata 특유의 'fields' 영역만 추출하여 데이터프레임 변환
fields_data = [item['fields'] for item in data]
df = pd.DataFrame(fields_data)

# 터미널에 표 형태로 출력
print(df)

# 필요 시 Excel 파일로 바로 내보내기
df.to_excel('all_data.xlsx', index=False)