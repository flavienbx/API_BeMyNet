import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, users, clients, products, sales, invoices, stripe, reviews
from app.config import settings

app = FastAPI(
    title="BeMyNet API",
    description="API for BeMyNet freelance platform",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the exact domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(clients.router, prefix="/clients", tags=["Clients"])
app.include_router(products.router, prefix="/produits", tags=["Products"])
app.include_router(sales.router, prefix="/ventes", tags=["Sales"])
app.include_router(invoices.router, prefix="/devis", tags=["Quotes and Invoices"])
app.include_router(stripe.router, prefix="/stripe", tags=["Stripe Integration"])
app.include_router(reviews.router, prefix="/avis", tags=["Reviews"])


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Welcome to BeMyNet API",
        "version": "1.0.0",
        "documentation": "/docs"
    }


if __name__ == "__main__":
    uvicorn.run(
        "fastapi_app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )