from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Header
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import stripe
import json
from decimal import Decimal

from app.database import get_db
from app.models.users import User
from app.models.sales import Vente
from app.models.clients import Client
from app.models.products import Produit
from app.schemas.sales import VenteCreate
from app.dependencies import get_current_user, get_current_active_user, check_admin_role
from app.utils.stripe import (
    create_stripe_connect_account, get_stripe_dashboard_link,
    create_payment_intent, create_checkout_session,
    verify_stripe_webhook, calculate_commissions_with_partners
)
from app.config import settings

router = APIRouter()

# Initialize Stripe with API key
stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post("/onboard", response_model=Dict[str, str])
async def create_stripe_onboarding(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create Stripe Connect Express account and onboarding link
    """
    try:
        # Check if user already has a Stripe account
        if current_user.stripe_account_id:
            # If they have an account but not onboarded, create a new onboarding link
            account_link = stripe.AccountLink.create(
                account=current_user.stripe_account_id,
                refresh_url=f"{settings.FRONTEND_URL}/stripe/refresh",
                return_url=f"{settings.FRONTEND_URL}/stripe/complete",
                type="account_onboarding",
            )
            return {"onboarding_url": account_link.url}
        
        # Create a new Stripe Connect account
        stripe_account = create_stripe_connect_account({
            "id": current_user.id,
            "email": current_user.email,
            "country": current_user.country or "FR",
            "website": current_user.website
        })
        
        # Update user with Stripe account info
        current_user.stripe_account_id = stripe_account["stripe_account_id"]
        current_user.stripe_dashboard_url = stripe_account["dashboard_url"]
        db.commit()
        
        return {"onboarding_url": stripe_account["onboarding_url"]}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating Stripe account: {str(e)}"
        )

@router.get("/dashboard", response_model=Dict[str, str])
async def get_stripe_dashboard_url(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get Stripe dashboard link for current user
    """
    if not current_user.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User doesn't have a Stripe account yet"
        )
    
    dashboard_url = get_stripe_dashboard_link(current_user.stripe_account_id)
    return {"dashboard_url": dashboard_url}

@router.get("/account-status", response_model=Dict[str, Any])
async def check_stripe_account_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Check current user's Stripe account status
    """
    if not current_user.stripe_account_id:
        return {
            "has_account": False,
            "details_submitted": False,
            "charges_enabled": False,
            "payouts_enabled": False
        }
    
    try:
        account = stripe.Account.retrieve(current_user.stripe_account_id)
        
        # Update user's payout_enabled status
        current_user.payout_enabled = account.payouts_enabled
        db.commit()
        
        return {
            "has_account": True,
            "details_submitted": account.details_submitted,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "requirements": account.requirements
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error checking Stripe account: {str(e)}"
        )

@router.post("/payment-intent", response_model=Dict[str, Any])
async def create_stripe_payment_intent(
    data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Payment Intent for a sale
    """
    # Validate required fields
    required_fields = ["amount", "freelance_id", "product_id", "client_id"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required field: {field}"
            )
    
    # Get freelancer
    freelancer = db.query(User).filter(User.id == data["freelance_id"]).first()
    if not freelancer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Freelancer not found"
        )
    
    # Check if freelancer has Stripe account
    if not freelancer.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Freelancer doesn't have a Stripe account"
        )
    
    # Get product
    product = db.query(Produit).filter(Produit.id == data["product_id"]).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Get client
    client = db.query(Client).filter(Client.id == data["client_id"]).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Calculate commissions
    commercial_id = data.get("commercial_id")
    partenaire_id = data.get("partenaire_id")
    
    # Get commission rates
    commercial_rate = None
    partner_rate = None
    
    if commercial_id:
        commercial = db.query(Commercial).filter(Commercial.id == commercial_id).first()
        if commercial:
            commercial_rate = commercial.pourcentage / 100
    
    if partenaire_id:
        partenaire = db.query(Partenaire).filter(Partenaire.id == partenaire_id).first()
        if partenaire:
            partner_rate = partenaire.pourcentage / 100
    
    # Calculate commissions
    amount = Decimal(str(data["amount"]))
    discount = Decimal(str(data.get("discount", 0)))
    
    commission_data = calculate_commissions_with_partners(
        amount=amount,
        discount=discount,
        commercial_rate=commercial_rate,
        partner_rate=partner_rate
    )
    
    # Create metadata for the payment
    metadata = {
        "freelance_id": str(freelancer.id),
        "product_id": str(product.id),
        "client_id": str(client.id),
        "platform": "BeMyNet"
    }
    
    if commercial_id:
        metadata["commercial_id"] = str(commercial_id)
    
    if partenaire_id:
        metadata["partenaire_id"] = str(partenaire_id)
    
    # Create payment intent
    payment_intent = create_payment_intent(
        amount=amount,
        freelance_stripe_account=freelancer.stripe_account_id,
        application_fee=commission_data["platform_fee"] + commission_data["commercial_commission"] + commission_data["partner_commission"],
        metadata=metadata
    )
    
    return payment_intent

@router.post("/checkout-session", response_model=Dict[str, Any])
async def create_stripe_checkout(
    data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Checkout Session for a product
    """
    # Validate required fields
    required_fields = ["amount", "freelance_id", "product_id", "client_id", "success_url", "cancel_url"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required field: {field}"
            )
    
    # Get freelancer
    freelancer = db.query(User).filter(User.id == data["freelance_id"]).first()
    if not freelancer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Freelancer not found"
        )
    
    # Check if freelancer has Stripe account
    if not freelancer.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Freelancer doesn't have a Stripe account"
        )
    
    # Get product
    product = db.query(Produit).filter(Produit.id == data["product_id"]).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Get client
    client = db.query(Client).filter(Client.id == data["client_id"]).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Calculate commissions
    commercial_id = data.get("commercial_id")
    partenaire_id = data.get("partenaire_id")
    
    # Get commission rates
    commercial_rate = None
    partner_rate = None
    
    if commercial_id:
        commercial = db.query(Commercial).filter(Commercial.id == commercial_id).first()
        if commercial:
            commercial_rate = commercial.pourcentage / 100
    
    if partenaire_id:
        partenaire = db.query(Partenaire).filter(Partenaire.id == partenaire_id).first()
        if partenaire:
            partner_rate = partenaire.pourcentage / 100
    
    # Calculate commissions
    amount = Decimal(str(data["amount"]))
    discount = Decimal(str(data.get("discount", 0)))
    
    commission_data = calculate_commissions_with_partners(
        amount=amount,
        discount=discount,
        commercial_rate=commercial_rate,
        partner_rate=partner_rate
    )
    
    # Create metadata for the payment
    metadata = {
        "freelance_id": str(freelancer.id),
        "product_id": str(product.id),
        "client_id": str(client.id),
        "platform": "BeMyNet"
    }
    
    if commercial_id:
        metadata["commercial_id"] = str(commercial_id)
    
    if partenaire_id:
        metadata["partenaire_id"] = str(partenaire_id)
    
    # Create checkout session
    checkout_session = create_checkout_session(
        amount=amount,
        freelance_stripe_account=freelancer.stripe_account_id,
        application_fee=commission_data["platform_fee"] + commission_data["commercial_commission"] + commission_data["partner_commission"],
        metadata=metadata,
        success_url=data["success_url"],
        cancel_url=data["cancel_url"],
        product_name=product.nom
    )
    
    return checkout_session

@router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db)
):
    """
    Handle Stripe webhook events
    """
    # Read request body
    payload = await request.body()
    
    try:
        # Verify webhook signature
        event = verify_stripe_webhook(
            signature=stripe_signature,
            payload=payload
        )
        
        # Handle different event types
        if event["type"] == "payment_intent.succeeded":
            await handle_payment_success(event["data"]["object"], db)
        
        elif event["type"] == "account.updated":
            await handle_account_updated(event["data"]["object"], db)
        
        # Add more event handlers as needed
        
        return {"status": "success"}
    
    except Exception as e:
        # Log the error but return 200 to acknowledge receipt
        print(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

async def handle_payment_success(payment_intent, db: Session):
    """
    Handle successful payment webhook
    """
    # Extract metadata
    metadata = payment_intent.get("metadata", {})
    
    # If no metadata, this might not be our payment
    if not metadata:
        return
    
    # Extract necessary IDs
    freelance_id = int(metadata.get("freelance_id", 0))
    product_id = int(metadata.get("product_id", 0))
    client_id = int(metadata.get("client_id", 0))
    commercial_id = int(metadata.get("commercial_id", 0)) if "commercial_id" in metadata else None
    partenaire_id = int(metadata.get("partenaire_id", 0)) if "partenaire_id" in metadata else None
    
    # Check if this payment has already been processed
    existing_sale = db.query(Vente).filter(
        Vente.stripe_payment_id == payment_intent["id"]
    ).first()
    
    if existing_sale:
        # Update status if needed
        if existing_sale.statut_paiement != "payé":
            existing_sale.statut_paiement = "payé"
            db.commit()
        return
    
    # Get the amount in correct format
    amount = Decimal(payment_intent["amount"]) / 100  # Convert cents to dollars/euros
    
    # Calculate application fee
    application_fee = Decimal(payment_intent.get("application_fee_amount", 0)) / 100
    
    # Create a new sale
    sale_data = VenteCreate(
        user_id=freelance_id,
        client_id=client_id,
        produit_id=product_id,
        montant=amount,
        commercial_id=commercial_id,
        partenaire_id=partenaire_id,
        description=f"Payment for product ID: {product_id}",
        source="stripe"
    )
    
    # Get freelancer
    freelancer = db.query(User).filter(User.id == freelance_id).first()
    
    # Get commercial commission rate if applicable
    commercial_rate = None
    if commercial_id:
        commercial = db.query(Commercial).filter(Commercial.id == commercial_id).first()
        if commercial:
            commercial_rate = commercial.pourcentage / 100 if commercial.pourcentage else None
    
    # Get partner commission rate if applicable
    partner_rate = None
    if partenaire_id:
        partner = db.query(Partenaire).filter(Partenaire.id == partenaire_id).first()
        if partner:
            partner_rate = partner.pourcentage / 100 if partner.pourcentage else None
    
    # Calculate commissions
    commission_data = calculate_commissions_with_partners(
        amount=amount,
        commercial_rate=commercial_rate,
        partner_rate=partner_rate
    )
    
    # Create new sale with calculated commissions
    new_sale = Vente(
        user_id=freelance_id,
        client_id=client_id,
        produit_id=product_id,
        montant=amount,
        description=f"Payment for product ID: {product_id}",
        date=datetime.utcnow(),
        source="stripe",
        commission_plateforme=commission_data['platform_fee'],
        commission_commerciale=commission_data['commercial_commission'],
        commission_partenaire=commission_data['partner_commission'],
        montant_net_freelance=commission_data['net_amount'],
        commercial_id=commercial_id,
        partenaire_id=partenaire_id,
        stripe_payment_id=payment_intent["id"],
        statut_paiement="payé"
    )
    
    db.add(new_sale)
    
    # Update client lifetime value
    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        client.lifetime_value = (client.lifetime_value or Decimal('0.0')) + amount
        client.last_purchase_date = datetime.utcnow()
    
    # Update freelancer revenue
    if freelancer:
        freelancer.total_revenue = (freelancer.total_revenue or Decimal('0.0')) + commission_data['net_amount']
    
    db.commit()
    
    # Create affiliations if needed
    if commercial_id:
        affiliation = Affiliation(
            source_type="commercial",
            source_id=commercial_id,
            vente_id=new_sale.id,
            commission=commission_data['commercial_commission']
        )
        db.add(affiliation)
    
    if partenaire_id:
        affiliation = Affiliation(
            source_type="partenaire",
            source_id=partenaire_id,
            vente_id=new_sale.id,
            commission=commission_data['partner_commission']
        )
        db.add(affiliation)
    
    db.commit()

async def handle_account_updated(account, db: Session):
    """
    Handle Stripe Connect account updates
    """
    # Find user with this account
    user = db.query(User).filter(User.stripe_account_id == account["id"]).first()
    
    if not user:
        return
    
    # Update user's payout status
    user.payout_enabled = account.get("payouts_enabled", False)
    
    # Update KYC status if available
    if "requirements" in account:
        if account["requirements"]["currently_due"]:
            user.kyc_status = "pending"
        elif account["requirements"]["disabled_reason"]:
            user.kyc_status = "rejected"
        else:
            user.kyc_status = "verified"
    
    db.commit()

@router.get("/refresh-account", response_model=Dict[str, Any])
async def refresh_stripe_account(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Manually refresh Stripe account status
    """
    if not current_user.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User doesn't have a Stripe account"
        )
    
    try:
        account = stripe.Account.retrieve(current_user.stripe_account_id)
        
        # Update user's payout status
        current_user.payout_enabled = account.payouts_enabled
        
        # Update KYC status if available
        if "requirements" in account:
            if account["requirements"].get("currently_due"):
                current_user.kyc_status = "pending"
            elif account["requirements"].get("disabled_reason"):
                current_user.kyc_status = "rejected"
            else:
                current_user.kyc_status = "verified"
        
        db.commit()
        
        return {
            "has_account": True,
            "details_submitted": account.details_submitted,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "requirements": account.requirements
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error refreshing Stripe account: {str(e)}"
        )
