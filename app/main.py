from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, auth
from app.database import engine, get_db

# 테이블 생성
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# 1-1. 회원가입
@app.post("/api/auth/signup", response_model=schemas.ApiResponse[schemas.SignUpData], status_code=status.HTTP_201_CREATED)
def signup(request: schemas.SignUpRequest, db: Session = Depends(get_db)):
    # 중복 아이디 체크
    existing_user = db.query(models.User).filter(models.User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 username입니다.")

    # 사용자 생성 및 저장
    hashed_pwd = auth.get_password_hash(request.password)
    user = models.User(
        username=request.username,
        password=hashed_pwd,
        phone=request.phone,
        address=request.address
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return schemas.ApiResponse(
        success=True,
        data=schemas.SignUpData(
            user=schemas.UserResponse.model_validate(user)
        )
    )

# 1-2. 로그인
@app.post("/api/auth/login", response_model=schemas.ApiResponse[schemas.LoginData], status_code=status.HTTP_200_OK)
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == request.username).first()
    if not user or not auth.verify_password(request.password, user.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    # 토큰 발급
    access_token = auth.create_access_token(data={"sub": user.username})
    refresh_token = auth.create_refresh_token(data={"sub": user.username})

    return schemas.ApiResponse(
        success=True,
        data=schemas.LoginData(
            accessToken=access_token,
            refreshToken=refresh_token,
            user=schemas.UserSimpleResponse.model_validate(user)
        )
    )

# 1-3. 로그아웃
@app.post("/api/auth/logout", response_model=schemas.ApiResponse[None], status_code=status.HTTP_200_OK)
def logout(
    auth_data: tuple = Depends(auth.get_current_user_and_token),
    db: Session = Depends(get_db)
):
    _, token = auth_data

    # 요청에 사용된 Access Token을 블랙리스트에 추가
    blacklisted_token = models.TokenBlacklist(token=token)
    db.add(blacklisted_token)
    db.commit()

    return schemas.ApiResponse(
        success=True,
        data=None
    )