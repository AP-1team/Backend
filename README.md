# Backend

FastAPI 기반 회원 인증 API입니다.

## 실행

```powershell
$env:JWT_SECRET_KEY = "여기에-충분히-길고-무작위인-비밀키"
uvicorn main:app --reload
```

`JWT_SECRET_KEY`를 지정하지 않으면 개발용 비밀키가 프로세스 시작 시 생성됩니다. 재시작 후에도 기존 토큰을 유지해야 하는 배포 환경에서는 반드시 고정된 비밀키를 환경 변수로 설정하세요.

## API

### 회원가입

`POST /signup`

```json
{
  "username": "my-id",
  "password": "password123",
  "phone": "010-1234-5678",
  "address": "서울시 ..."
}
```

아이디는 3~50자, 비밀번호는 8자 이상이며 bcrypt 제한에 따라 UTF-8 기준 72바이트 이하여야 합니다. 이미 사용 중인 아이디는 `409 Conflict`를 반환합니다.

### 로그인

`POST /login`

```json
{
  "username": "my-id",
  "password": "password123"
}
```

성공 시 30분 유효한 JWT를 반환합니다.

### 내 정보 조회

`GET /users/me`

로그인 응답의 `access_token`을 `Authorization: Bearer <token>` 헤더에 전달하면 아이디, 전화번호, 주소를 반환합니다.

기존 이메일/비밀번호 형식의 `users` 테이블이 있다면 시작 시 기존 비밀번호 해시를 보존하고, 기존 이메일을 아이디로 사용하도록 스키마를 마이그레이션합니다. 이 방식으로 옮긴 기존 계정의 전화번호와 주소는 비어 있으므로 사용자가 새로 입력해야 합니다.
