from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from panel.auth import COOKIE_NAME, MAX_AGE, create_session_token, verify_credentials
from panel.deps import templates

router = APIRouter()


@router.get("/panel/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/panel/login")
async def login_submit(request: Request, login: str = Form(...), password: str = Form(...)):
    if not verify_credentials(login, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
    response = RedirectResponse("/panel/dashboard", status_code=302)
    response.set_cookie(COOKIE_NAME, create_session_token(), max_age=MAX_AGE, httponly=True)
    return response


@router.get("/panel/logout")
async def logout():
    response = RedirectResponse("/panel/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
