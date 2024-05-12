# main.py
from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
import mysql.connector

#from fastapi.security import HTTPBasic, HTTPBasicCredentials #5/11新增（比對資料庫跟html帳號密碼）


app = FastAPI()

# 設置靜態文件目錄
app.mount("/static", StaticFiles(directory="static"), name="static")

#設置Jinja2 模板目錄
templates = Jinja2Templates(directory="templates")

#HTTPBasic 身份認證 (5/11 一定要用嗎？跟session擇一)
#security = HTTPBasic()

# 啟用 SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key="your_secret_key")

# 定義用戶狀態的鍵
USER_STATE_KEY = "SIGNED-IN"

# 驗證成功時設置用戶狀態為已登錄
def set_user_signed_in(request: Request):
    request.session[USER_STATE_KEY] = True # key: value

# 登出時設置用戶狀態為未登錄
def set_user_signed_out(request: Request):
    request.session.pop(USER_STATE_KEY, None) # 刪除 SIGNED-IN 的key

# 檢查用戶是否已登錄的依賴
def check_user_signed_in(request: Request):
    signed_in = request.session.get(USER_STATE_KEY, False)
    return signed_in

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "home_url": request.url_for('home')})

#中間層 
# endpoint: signup  5/11 
@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    #需要用 await （表示完成這一個動作，才能做後續的, form.get()內是"name")
    form = await request.form()
    # 先建立這個，後面判斷username有沒有重複
    signup_username = form.get("signup_username") 
    # 連接到 MySQL資料庫，username: wehelp (5/11 new) 
    with mysql.connector.connect(
        host="localhost",
        user="wehelp",
        password="wehelp",
        database="website"
    ) as conn:
         with conn.cursor() as cursor:
            # 檢查數據庫中是否已經存在相同的用戶名
            cursor.execute("SELECT * FROM `member` WHERE username = %s", (signup_username,))
            existing_user = cursor.fetchone()

            if existing_user:
                # 如果存在重複的用戶名，返回錯誤頁面，並顯示 "Repeated username"
                return templates.TemplateResponse("error.html", {"request": request,"message": "重複的使用者帳號"})
            else:
                # 如果不存在重複的用戶名，插入新用戶信息到數據庫中
                # 要傳給 jinja2模板用
                signup_name = form.get("signup_name")
                signup_password = form.get("signup_password")

                cursor.execute("INSERT INTO `member` (name, username, password) VALUES (%s, %s, %s)", (signup_name, signup_username, signup_password))
                conn.commit()

                # 重定向用戶到首頁
                return RedirectResponse(f"/?success=True&name={signup_name}", status_code=303)

@app.post("/signin") 
async def signin_post(request:Request,
                      #credentials: HTTPBasicCredentials = Depends(security), 
                      username: str = Form(None), 
                      password: str = Form(None)):
    # 從HTTPBasicCredentials 獲取username and password
    #username = credentials.username
    #password = credentials.password
    
    # 連線到 MySQL 資料庫
    with mysql.connector.connect(host="localhost", user="wehelp", password="wehelp", database="website") as conn:
        with conn.cursor() as cursor:
            try:
                # 使用 AND 來比對
                cursor.execute("SELECT username, password, name FROM `member` WHERE (username = %s AND password = %s)", (username, password))
                #cursor.execute("SELECT username, password, name FROM `member` WHERE (username, password) IN (%s, %s), (username, password))
                user = cursor.fetchone() # 獲取一行結果
                print("User from database:", user)  # 在這裡打印用戶信息

                if user: # 如果用戶存在
                    name = user[2]  # 獲取用戶名稱
                    # 登入成功，重定向到 /member 頁面，帶上用戶名作為查詢參數
                    set_user_signed_in(request) #本來的session
                    return RedirectResponse(url=f"/member?name={name}", status_code=303) 
                else:  # 如果用戶名或密碼不正確，重定向到錯誤頁面，並顯示消息
                    return RedirectResponse(url="/error?message=帳號、密碼輸入錯誤")
            except Exception as e:
                # 處理異常
                raise HTTPException(status_code=500)

    # 如果用戶名和密碼正確，重定向到成功頁面
    #set_user_signed_in(request) 本來的session
    #return RedirectResponse(url="/member", status_code=303)  # 303 將本來應該需要用post傳輸允許用get

#show不同訊息的錯誤頁面
@app.post("/error", response_class=HTMLResponse)
async def error(request: Request, message: str = ""):
    return templates.TemplateResponse("error.html", {"request": request, "message": message})

#success 登入頁面member
@app.get("/member", response_class=HTMLResponse, dependencies=[Depends(check_user_signed_in)])
async def member(request: Request, name: str = None): 
    #檢查是否已經登入
    signed_in = request.session.get(USER_STATE_KEY, False)
    if not signed_in:
        # 如果未登錄，重定向到首頁
        return RedirectResponse(url="/", status_code=303)
    
    # 建立與 MySQL 資料庫的連線
    with mysql.connector.connect(
        host="localhost",
        user="wehelp",
        password="wehelp",
        database="website"
    ) as conn:
        # 執行 SQL 查詢，使用 JOIN 操作獲取留言資料與作者名稱
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT message.content AS message, member.name AS name FROM message JOIN `member` ON message.member_id = member.id")

            # 檢索查詢結果
            messages = cursor.fetchall()

    # 返回會員頁面模板，傳遞留言資料
    return templates.TemplateResponse("member.html", {"request": request, "messages": messages, "name":name})

# 登出端點
@app.get("/signout")
async def signout(request: Request):
    # 登出，設置用戶狀態為未登錄
    set_user_signed_out(request)
    # 重定向到首頁
    return RedirectResponse(url="/", status_code=303)
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
