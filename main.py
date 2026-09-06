import os
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import stripe

app = FastAPI()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "price_placeholder")

ADMIN_EMAIL = "Dwayne.mashburn@gmail.com"
ADMIN_PASSWORD = "Duanemashburn2!"

fake_users_db = {
    ADMIN_EMAIL: {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "is_admin": True,
        "is_subscribed": True
    }
}

class UserLogin(BaseModel):
    email: str
    password: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return """
    <html>
        <head><title>DayZ Bot Dashboard</title></head>
        <body style="font-family: Arial; background: #111; color: #fff; text-align: center; padding-top: 50px;">
            <h1>DayZ Server Management Bot</h1>
            <p>Explore features below. Active subscription required to interact.</p>
            <div style="opacity: 0.5; pointer-events: none; margin: 20px;">
                <button>Configure Server JSON</button>
                <button>Trigger Player Radar</button>
                <button>Manage Discord Webhooks</button>
            </div>
            <br>
            <a href="/login" style="color: #4f46e5; font-size: 18px;">Login to Account</a>
        </body>
    </html>
    """

@app.post("/api/login")
async def login(form_data: UserLogin):
    user = fake_users_db.get(form_data.email)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if user["email"] == ADMIN_EMAIL:
        return {"access_token": "admin_bypass_token", "token_type": "bearer", "redirect": "/admin/dashboard"}
    
    return {"access_token": "user_token", "token_type": "bearer", "redirect": "/dashboard"}

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(email: str = ADMIN_EMAIL):
    if email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Access Forbidden")
    
    try:
        subscriptions = stripe.Subscription.list(limit=10)
        sub_count = len(subscriptions.data)
    except Exception:
        sub_count = 0

    return f"""
    <html>
        <head><title>Owner Admin Dashboard</title></head>
        <body style="font-family: Arial; background: #0f172a; color: #f8fafc; padding: 40px;">
            <h1>Welcome Back, Dwayne</h1>
            <h2>Owner & Developer Control Panel</h2>
            <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin-top: 20px;">
                <h3>Live System Metrics</h3>
                <p>Active Subscribers: <b>{sub_count}</b></p>
                <p>Status: <span style="color: #22c55e;">Fully Operational (Bypass Active)</span></p>
            </div>
        </body>
    </html>
    """

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            subscription_data={'trial_period_days': 3},
            allow_promotion_codes=True,
            success_url=str(request.base_url) + 'dashboard?success=true',
            cancel_url=str(request.base_url) + '?canceled=true',
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/create-portal-session")
async def customer_portal(request: Request):
    try:
        data = await request.json()
        customer_id = data.get("customer_id")
        
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=str(request.base_url) + 'dashboard',
        )
        return {"url": portal_session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/webhook")
async def stripe_webhook(request: Request):
    event_data = await request.json()
    event_type = event_data.get("type")

    if event_type == "invoice.payment_failed":
        invoice = event_data["data"]["object"]
        subscription_id = invoice.get("subscription")
        
    elif event_type == "customer.subscription.deleted":
        subscription = event_data["data"]["object"]

    return {"status": "success"}
