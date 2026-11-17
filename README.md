# 구매 뭉탱이 Backend

FastAPI 기반 REST API와 모집방 채팅 WebSocket입니다. JSON을 사용하며 인증 요청은 `Authorization: Bearer {accessToken}` 헤더를 전달합니다.

## 실행

프로젝트 루트의 `.env`에 MySQL 연결 정보를 설정할 수 있습니다.

```env
DATABASE_URL=mysql+pymysql://root:1234@localhost:3306/fastapi_db
```

PowerShell에서 설치하고 실행합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

API 문서: <http://127.0.0.1:8000/docs>

로그인 토큰은 Python `secrets`로 생성되어 `tokens` 테이블에 7일간 저장됩니다. `.env`는 저장소에 커밋하지 마세요.

## 엔드포인트

모든 HTTP API 경로는 `/api`로 시작합니다.

| 기능 | Method | Path |
| --- | --- | --- |
| 회원가입 | POST | `/api/auth/signup` |
| 로그인 | POST | `/api/auth/login` |
| 로그아웃 | POST | `/api/auth/logout` |
| 내 정보 조회/수정 | GET/PATCH | `/api/users/me` |
| 구매 기록 | GET | `/api/users/me/purchases` |
| 모집방 생성/목록/검색/상세 | POST/GET | `/api/groups`, `/api/groups/search`, `/api/groups/{id}` |
| 모집방 수정/삭제 | PATCH/DELETE | `/api/groups/{id}` |
| 모집방 참여/취소 | POST/DELETE | `/api/groups/{id}/join`, `/api/groups/{id}/participants/me` |
| 코인 잔액/충전 | GET/POST | `/api/users/me/coins`, `/api/users/me/coins/charge` |
| 정산 조회/결제 | GET/POST | `/api/groups/{id}/coin-settlement`, `/api/groups/{id}/coin-settlement/pay` |
| 채팅 내역/메시지 전송 | GET/POST | `/api/groups/{id}/messages` |
| 실시간 채팅 | WebSocket | `/ws/groups/{id}?token={accessToken}` |

요청 및 응답 예시는 명세를 따릅니다. 입력 검증 오류는 `400`과 `VALIDATION_ERROR`, 존재하지 않는 모집방은 `404`와 `GROUP_NOT_FOUND`를 반환합니다. 모집방 목록은 `page`당 20개입니다.

## 구현 범위

- 결제 API는 결제 상태와 기록을 저장하는 데모 처리이며 실제 카드사/결제 서비스와 연동하지 않습니다.
- 카테고리는 별도 마스터 목록 없이 문자열로 저장합니다.
- 정산 금액은 모집방의 가격을 현재 참여 인원으로 나눈 금액으로 계산합니다.
- WebSocket은 연결 시 참여자와 access token을 확인합니다. 실시간 연결 주소에 토큰을 query parameter로 전달하므로 운영 환경에서는 반드시 HTTPS/WSS를 사용하세요.

DB 연결 설정은 `app/database.py`에서 관리합니다. 최초 실행 시 새 테이블은 자동 생성되며 기존 테이블의 스키마 변경을 자동 마이그레이션하지는 않습니다.
