from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import SessionLocal, engine, ensure_schema, get_db

models.Base.metadata.create_all(bind=engine)
ensure_schema()
app = FastAPI(title="구매 뭉탱이 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def fail(code: str, message: str, http_status: int):
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


@app.exception_handler(HTTPException)
async def api_http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) and "code" in exc.detail else {
        "code": "HTTP_ERROR", "message": str(exc.detail)
    }
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": detail},
                        headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def api_validation_error(request: Request, exc: RequestValidationError):
    error = exc.errors()[0] if exc.errors() else {}
    return JSONResponse(status_code=400, content={"success": False, "error": {
        "code": "VALIDATION_ERROR", "message": error.get("msg", "요청 값이 올바르지 않습니다.")
    }})


def user_view(user: models.User, db: Session | None = None):
    bought_count = 0
    if db is not None:
        bought_count = db.query(models.Payment).filter_by(
            user_id=user.id, status="COMPLETED"
        ).count()
    return {
        "id": user.id, "username": user.username, "phone": user.phone, "address": user.address,
        "coinBalance": user.coin_balance, "boughtCount": bought_count,
    }


def count_participants(db: Session, group_id: int) -> int:
    return db.query(models.GroupParticipant).filter_by(group_id=group_id).count()


def group_status(group: models.Group, count: int) -> str:
    if count >= group.target_count:
        return "FULL"
    if group.deadline <= datetime.utcnow():
        return "CLOSED"
    return "RECRUITING"


def group_summary(db: Session, group: models.Group):
    return {
        "id": group.id, "title": group.title, "category": group.category, "price": group.price,
        "targetCount": group.target_count, "currentCount": count_participants(db, group.id),
        "quantity": group.quantity, "region": group.region, "imageUrl": group.image_url,
        "perPersonPrice": group.price // group.target_count,
        "perPersonQuantity": (
            group.quantity // group.target_count
            if group.quantity is not None and group.quantity % group.target_count == 0
            else None
        ),
        "createdAt": group.created_at.isoformat(),
        "status": group_status(group, count_participants(db, group.id)),
        "deadline": group.deadline.isoformat(),
    }


def require_group(db: Session, group_id: int):
    group = db.query(models.Group).filter_by(id=group_id).first()
    if not group:
        raise fail("GROUP_NOT_FOUND", "존재하지 않는 모집방입니다.", 404)
    return group


def require_participant(db: Session, group_id: int, user_id: int):
    participant = db.query(models.GroupParticipant).filter_by(
        group_id=group_id, user_id=user_id
    ).first()
    if not participant:
        raise fail("NOT_PARTICIPANT", "참여자만 이용할 수 있습니다.", 403)
    return participant


@app.post("/api/auth/signup", status_code=201)
def signup(request: schemas.SignUpRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter_by(username=request.username).first():
        raise fail("DUPLICATE_USERNAME", "이미 사용 중인 아이디입니다.", 409)
    user = models.User(username=request.username, password=auth.get_password_hash(request.password),
                       phone=request.phone, address=request.address, coin_balance=0)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise fail("DUPLICATE_USERNAME", "이미 사용 중인 아이디입니다.", 409)
    db.refresh(user)
    return {"success": True, "data": {"user": user_view(user, db)}}


@app.post("/api/auth/login")
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=request.username).first()
    if not user or not auth.verify_password(request.password, user.password):
        raise fail("INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.", 401)
    token = auth.create_token(db, user)
    db.commit()
    return {"success": True, "data": {
        "accessToken": token, "user": {"id": user.id, "username": user.username}
    }}


@app.post("/api/auth/logout")
def logout(auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    _, token = auth_data
    db.query(models.Token).filter_by(token=token).delete()
    db.commit()
    return {"success": True, "data": None}


@app.get("/api/users/me")
def get_me(auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    return {"success": True, "data": {"user": user_view(auth_data[0], db)}}


@app.patch("/api/users/me")
def update_me(request: schemas.UserUpdateRequest, auth_data=Depends(auth.get_current_user_and_token),
              db: Session = Depends(get_db)):
    user, _ = auth_data
    changes = request.model_dump(exclude_unset=True)
    if "password" in changes:
        changes["password"] = auth.get_password_hash(changes["password"])
    if not changes:
        raise fail("VALIDATION_ERROR", "수정할 정보를 입력해 주세요.", 400)
    for key, value in changes.items():
        setattr(user, key, value)
    db.commit()
    return {"success": True, "data": {"user": user_view(user, db)}}


@app.post("/api/groups", status_code=201)
def create_group(request: schemas.GroupCreateRequest, auth_data=Depends(auth.get_current_user_and_token),
                 db: Session = Depends(get_db)):
    user, _ = auth_data
    group = models.Group(title=request.title.strip(), description=request.description,
                         category=request.category, price=request.price, target_count=request.targetCount,
                         quantity=request.quantity, region=request.region, image_url=request.image,
                         deadline=request.deadline, author_id=user.id)
    db.add(group)
    db.flush()
    db.add(models.GroupParticipant(group_id=group.id, user_id=user.id))
    db.commit()
    db.refresh(group)
    return {"success": True, "data": {"group": group_summary(db, group)}}


@app.get("/api/groups")
def list_groups(category: Optional[str] = None, keyword: Optional[str] = None,
                status_filter: Optional[str] = Query(None, alias="status"),
                page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    query = db.query(models.Group).order_by(models.Group.created_at.desc())
    if category:
        query = query.filter(models.Group.category == category)
    if keyword:
        query = query.filter(models.Group.title.contains(keyword))
    all_groups = query.all()
    summaries = [group_summary(db, group) for group in all_groups]
    if status_filter:
        summaries = [item for item in summaries if item["status"] == status_filter.upper()]
    page_size = 20
    total = len(summaries)
    return {"success": True, "data": {
        "groups": summaries[(page - 1) * page_size:page * page_size],
        "page": page, "totalPages": (total + page_size - 1) // page_size, "totalCount": total
    }}


@app.get("/api/groups/search")
def search_groups(keyword: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    groups = db.query(models.Group).filter(models.Group.title.contains(keyword)).all()
    return {"success": True, "data": {"groups": [group_summary(db, group) for group in groups]}}


@app.get("/api/groups/{group_id}")
def get_group(group_id: int, db: Session = Depends(get_db),
              current_user: models.User | None = Depends(auth.get_optional_user)):
    group = require_group(db, group_id)
    participants = db.query(models.GroupParticipant).filter_by(group_id=group_id).all()
    result = group_summary(db, group)
    result.update({
        "description": group.description,
        "author": {"id": group.author.id, "username": group.author.username},
        "participants": [{"id": item.user.id, "username": item.user.username} for item in participants],
        "isJoined": bool(current_user and any(item.user_id == current_user.id for item in participants)),
    })
    return {"success": True, "data": {"group": result}}


@app.patch("/api/groups/{group_id}")
def update_group(group_id: int, request: schemas.GroupUpdateRequest,
                 auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    group = require_group(db, group_id)
    if group.author_id != user.id:
        raise fail("NOT_GROUP_OWNER", "모집방 작성자만 수정할 수 있습니다.", 403)
    for key, value in request.model_dump(exclude_unset=True, by_alias=True).items():
        setattr(group, {"targetCount": "target_count"}.get(key, key), value)
    db.commit()
    return {"success": True, "data": {"group": group_summary(db, group)}}


@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, auth_data=Depends(auth.get_current_user_and_token),
                 db: Session = Depends(get_db)):
    user, _ = auth_data
    group = require_group(db, group_id)
    if group.author_id != user.id:
        raise fail("NOT_GROUP_OWNER", "모집방 작성자만 삭제할 수 있습니다.", 403)
    db.delete(group)
    db.commit()
    return {"success": True, "data": None}


@app.post("/api/groups/{group_id}/join", status_code=201)
def join_group(group_id: int, auth_data=Depends(auth.get_current_user_and_token),
               db: Session = Depends(get_db)):
    user, _ = auth_data
    group = require_group(db, group_id)
    count = count_participants(db, group_id)
    if count >= group.target_count:
        raise fail("GROUP_FULL", "모집 인원이 이미 마감되었습니다.", 409)
    if group.deadline <= datetime.utcnow():
        raise fail("DEADLINE_PASSED", "모집 기간이 끝난 모집방입니다.", 400)
    if db.query(models.GroupParticipant).filter_by(group_id=group_id, user_id=user.id).first():
        raise fail("ALREADY_JOINED", "이미 참여한 모집방입니다.", 409)
    db.add(models.GroupParticipant(group_id=group_id, user_id=user.id))
    db.commit()
    return {"success": True, "data": {"groupId": group_id, "userId": user.id, "currentCount": count + 1}}


@app.post("/api/groups/{group_id}/leave")
@app.delete("/api/groups/{group_id}/participants/me")
def leave_group(group_id: int, auth_data=Depends(auth.get_current_user_and_token),
                db: Session = Depends(get_db)):
    user, _ = auth_data
    require_group(db, group_id)
    participant = db.query(models.GroupParticipant).filter_by(group_id=group_id, user_id=user.id).first()
    if not participant:
        raise fail("NOT_PARTICIPANT", "참여하지 않은 모집방입니다.", 409)
    if participant.group.author_id == user.id:
        raise fail("GROUP_OWNER_CANNOT_LEAVE", "작성자는 모집방을 나가려면 삭제해야 합니다.", 409)
    db.delete(participant)
    db.commit()
    return {"success": True, "data": {"groupId": group_id}}


@app.get("/api/users/me/groups")
def my_groups(group_type: str = Query("joined", alias="type"),
              auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    query = db.query(models.Group)
    if group_type == "created":
        query = query.filter_by(author_id=user.id)
    else:
        query = query.join(models.GroupParticipant).filter(models.GroupParticipant.user_id == user.id)
    return {"success": True, "data": {"groups": [group_summary(db, group) for group in query.all()]}}


@app.get("/api/groups/{group_id}/messages")
def message_history(group_id: int, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                    auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    require_group(db, group_id)
    require_participant(db, group_id, user.id)
    query = db.query(models.Message).filter_by(group_id=group_id).order_by(models.Message.created_at.asc())
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return {"success": True, "data": {
        "messages": [{"id": row.id, "userId": row.user_id, "username": row.user.username,
                      "content": row.content, "createdAt": row.created_at.isoformat()} for row in rows],
        "page": page, "totalPages": (total + size - 1) // size
    }}


ws_clients: dict[int, list[WebSocket]] = {}


async def broadcast(group_id: int, payload: dict):
    for socket in list(ws_clients.get(group_id, [])):
        try:
            await socket.send_json(payload)
        except Exception:
            if socket in ws_clients.get(group_id, []):
                ws_clients[group_id].remove(socket)


@app.post("/api/groups/{group_id}/messages", status_code=201)
async def send_message(group_id: int, request: schemas.MessageCreateRequest,
                       auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    require_group(db, group_id)
    require_participant(db, group_id, user.id)
    content = request.content.strip()
    if not content:
        raise fail("VALIDATION_ERROR", "메시지 내용은 비어 있을 수 없습니다.", 400)
    message = models.Message(group_id=group_id, user_id=user.id, content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    payload = {"type": "MESSAGE", "id": message.id, "userId": user.id, "username": user.username,
               "content": content, "createdAt": message.created_at.isoformat()}
    await broadcast(group_id, payload)
    return {"success": True, "data": {key: value for key, value in payload.items() if key != "type"}}


def ensure_deadline_notifications(db: Session, user_id: int):
    now = datetime.utcnow()
    memberships = db.query(models.GroupParticipant).filter_by(user_id=user_id).all()
    for membership in memberships:
        group = membership.group
        if now < group.deadline <= now + timedelta(hours=24):
            exists = db.query(models.Notification).filter_by(
                user_id=user_id, group_id=group.id, type="DEADLINE_IMMINENT"
            ).first()
            if not exists:
                db.add(models.Notification(
                    user_id=user_id, group_id=group.id, type="DEADLINE_IMMINENT",
                    message="모집 마감까지 24시간 남았습니다."
                ))
    db.commit()


@app.get("/api/users/me/purchases")
def purchase_history(auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    rows = db.query(models.Payment).filter_by(user_id=user.id, status="COMPLETED").order_by(
        models.Payment.paid_at.desc()).all()
    return {"success": True, "data": {"purchases": [
        {"groupId": row.group_id, "title": row.group.title, "amount": row.amount,
         "purchasedAt": row.paid_at.isoformat()} for row in rows
    ]}}


@app.get("/api/users/me/notifications")
def notifications(auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    ensure_deadline_notifications(db, user.id)
    rows = db.query(models.Notification).filter_by(user_id=user.id).order_by(
        models.Notification.created_at.desc()).all()
    unread_count = sum(not row.is_read for row in rows)
    return {"success": True, "data": {"notifications": [
        {"id": row.id, "groupId": row.group_id, "title": row.group.title, "type": row.type,
         "message": row.message, "deadline": row.group.deadline.isoformat(),
         "createdAt": row.created_at.isoformat(), "isRead": row.is_read,
         "imageUrl": row.group.image_url} for row in rows
    ], "unreadCount": unread_count}}


@app.post("/api/users/me/notifications/read")
def read_notifications(auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    db.query(models.Notification).filter_by(user_id=user.id).update({"is_read": True})
    db.commit()
    return {"success": True, "data": None}


@app.get("/api/users/me/coins")
def get_coins(auth_data=Depends(auth.get_current_user_and_token)):
    user, _ = auth_data
    return {"success": True, "data": {"balance": user.coin_balance}}


@app.post("/api/users/me/coins/charge")
def charge_coins(request: schemas.CoinChargeRequest,
                 auth_data=Depends(auth.get_current_user_and_token), db: Session = Depends(get_db)):
    user, _ = auth_data
    user.coin_balance += request.amount
    charged_at = datetime.utcnow()
    db.commit()
    return {"success": True, "data": {
        "chargedAmount": request.amount, "balance": user.coin_balance,
        "coinBalance": user.coin_balance,
        "chargedAt": charged_at.isoformat()
    }}


def settlement_data(group: models.Group, participants, payments):
    count = len(participants)
    coin = group.price // count if count else 0
    paid = {payment.user_id for payment in payments}
    return {
        "groupId": group.id, "totalCoin": group.price, "participantCount": count,
        "coinPerPerson": coin,
        "details": [{"userId": item.user.id, "username": item.user.username, "coin": coin,
                     "paid": item.user_id in paid} for item in participants]
    }


@app.get("/api/groups/{group_id}/coin-settlement")
@app.get("/api/groups/{group_id}/settlement")
def get_settlement(group_id: int, auth_data=Depends(auth.get_current_user_and_token),
                   db: Session = Depends(get_db)):
    group = require_group(db, group_id)
    participants = db.query(models.GroupParticipant).filter_by(group_id=group_id).all()
    payments = db.query(models.Payment).filter_by(group_id=group_id, status="COMPLETED").all()
    return {"success": True, "data": settlement_data(group, participants, payments)}


@app.post("/api/groups/{group_id}/coin-settlement/pay")
@app.post("/api/groups/{group_id}/purchase")
@app.post("/api/groups/{group_id}/settlement/pay")
def pay_settlement(group_id: int, auth_data=Depends(auth.get_current_user_and_token),
                   db: Session = Depends(get_db)):
    user, _ = auth_data
    group = require_group(db, group_id)
    require_participant(db, group_id, user.id)
    participants = db.query(models.GroupParticipant).filter_by(group_id=group_id).all()
    if len(participants) < group.target_count:
        raise fail("GROUP_NOT_COMPLETED", "모집이 완료된 모집방에서만 결제할 수 있습니다.", 400)
    if db.query(models.Payment).filter_by(group_id=group_id, user_id=user.id, status="COMPLETED").first():
        raise fail("ALREADY_PAID", "이미 결제를 완료했습니다.", 409)
    amount = group.price // len(participants)
    if user.coin_balance < amount:
        raise fail("INSUFFICIENT_COIN", "코인 잔액이 부족합니다.", 409)
    user.coin_balance -= amount
    group.author.coin_balance += amount
    payment = models.Payment(group_id=group_id, user_id=user.id, amount=amount, payment_method="COIN")
    db.add(payment)
    db.commit()
    return {"success": True, "data": {
        "groupId": group_id, "userId": user.id, "paidCoin": amount,
        "balance": user.coin_balance, "coinBalance": user.coin_balance,
        "paidAt": payment.paid_at.isoformat()
    }}


@app.post("/api/groups/{group_id}/payment-request")
def request_payment(group_id: int, auth_data=Depends(auth.get_current_user_and_token),
                    db: Session = Depends(get_db)):
    user, _ = auth_data
    group = require_group(db, group_id)
    require_participant(db, group_id, user.id)
    if group.author_id != user.id:
        notification = models.Notification(
            user_id=group.author_id, group_id=group.id, type="PAYMENT_REQUEST",
            message=f"{user.username}님이 결제를 요청했습니다."
        )
        db.add(notification)
        db.commit()
    return {"success": True, "data": None}


@app.websocket("/ws/groups/{group_id}")
async def group_socket(websocket: WebSocket, group_id: int, token: str = Query("")):
    db = SessionLocal()
    try:
        token_row = db.query(models.Token).filter_by(token=token).first()
        group = db.query(models.Group).filter_by(id=group_id).first()
        user = token_row.user if token_row and token_row.expires_at > datetime.utcnow() else None
        member = user and db.query(models.GroupParticipant).filter_by(
            group_id=group_id, user_id=user.id).first()
        if not user or not group or not member:
            await websocket.close(code=4401)
            return
        user_id, username = user.id, user.username
    finally:
        db.close()
    await websocket.accept()
    ws_clients.setdefault(group_id, []).append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            content = str(data.get("content", "")).strip()
            if not content:
                await websocket.send_json({"success": False, "error": {
                    "code": "VALIDATION_ERROR", "message": "메시지 내용은 비어 있을 수 없습니다."
                }})
                continue
            db = SessionLocal()
            try:
                message = models.Message(group_id=group_id, user_id=user_id, content=content)
                db.add(message)
                db.commit()
                db.refresh(message)
                payload = {"type": "MESSAGE", "id": message.id, "userId": user_id, "username": username,
                           "content": content, "createdAt": message.created_at.isoformat()}
            finally:
                db.close()
            await broadcast(group_id, payload)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in ws_clients.get(group_id, []):
            ws_clients[group_id].remove(websocket)
