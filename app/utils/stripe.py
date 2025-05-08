import stripe
from typing import Dict, Any, Optional
import json
from fastapi import HTTPException, status
from decimal import Decimal

from app.config import settings

# Initialize Stripe with API key
stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_connect_account(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a Stripe Connect Express account for a freelancer
    
    Args:
        user_data: User data containing necessary information
        
    Returns:
        Dictionary with Stripe account details
    """
    try:
        # Create a Stripe Connect Express account
        account = stripe.Account.create(
            type="express",
            country=user_data.get("country", "FR"),
            email=user_data.get("email"),
            business_type="individual",
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_profile={
                "mcc": "7399",  # Business services
                "url": user_data.get("website", "https://bemynet.fr"),
            },
            metadata={
                "user_id": str(user_data.get("id")),
                "platform": "BeMyNet",
            }
        )
        
        # Generate account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{settings.FRONTEND_URL}/stripe/refresh",
            return_url=f"{settings.FRONTEND_URL}/stripe/complete",
            type="account_onboarding",
        )
        
        return {
            "stripe_account_id": account.id,
            "dashboard_url": f"https://dashboard.stripe.com/{'test/' if 'test' in settings.STRIPE_SECRET_KEY else ''}express/{account.id}",
            "onboarding_url": account_link.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating Stripe account: {str(e)}"
        )

def get_stripe_dashboard_link(account_id: str) -> str:
    """
    Generate a link to the Stripe Express dashboard for a user
    
    Args:
        account_id: Stripe account ID
        
    Returns:
        URL to access the Stripe dashboard
    """
    try:
        login_link = stripe.Account.create_login_link(account_id)
        return login_link.url
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating Stripe dashboard link: {str(e)}"
        )

def create_payment_intent(
    amount: Decimal, 
    freelance_stripe_account: str, 
    application_fee: Decimal,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create a Stripe payment intent with automatic transfers to freelancer
    
    Args:
        amount: Payment amount in euros
        freelance_stripe_account: Freelancer's Stripe account ID
        application_fee: Platform fee amount
        metadata: Additional data to store with the payment
        
    Returns:
        Dictionary with payment intent details
    """
    try:
        # Convert decimal to integer (cents for Stripe)
        amount_cents = int(amount * 100)
        fee_cents = int(application_fee * 100)
        
        # Create payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="eur",
            application_fee_amount=fee_cents,
            transfer_data={
                "destination": freelance_stripe_account,
            },
            metadata=metadata,
            automatic_payment_methods={"enabled": True}
        )
        
        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "amount": amount,
            "fee": application_fee
        }
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating payment: {str(e)}"
        )

def create_checkout_session(
    amount: Decimal,
    freelance_stripe_account: str,
    application_fee: Decimal,
    metadata: Dict[str, Any],
    success_url: str,
    cancel_url: str,
    product_name: str
) -> Dict[str, Any]:
    """
    Create a Stripe Checkout session for a product
    
    Args:
        amount: Payment amount in euros
        freelance_stripe_account: Freelancer's Stripe account ID
        application_fee: Platform fee amount
        metadata: Additional data to store with the payment
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect after canceled payment
        product_name: Name of the product being sold
        
    Returns:
        Dictionary with checkout session details
    """
    try:
        # Convert decimal to integer (cents for Stripe)
        amount_cents = int(amount * 100)
        fee_cents = int(application_fee * 100)
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": product_name,
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            payment_intent_data={
                "application_fee_amount": fee_cents,
                "transfer_data": {
                    "destination": freelance_stripe_account,
                },
                "metadata": metadata,
            },
            metadata=metadata,
        )
        
        return {
            "session_id": session.id,
            "checkout_url": session.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating checkout session: {str(e)}"
        )

def verify_stripe_webhook(signature: str, payload: bytes, secret: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify and construct Stripe webhook event
    
    Args:
        signature: Stripe signature from request header
        payload: Raw request payload
        secret: Webhook secret key (defaults to settings)
        
    Returns:
        Validated Stripe event
    """
    webhook_secret = secret or settings.STRIPE_WEBHOOK_SECRET
    
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret
        )
        return event
    except ValueError as e:
        # Invalid payload
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {str(e)}"
        )
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid signature: {str(e)}"
        )

def calculate_commission(amount: Decimal, discount: Decimal = Decimal('0.0')) -> Dict[str, Any]:
    """
    Calculate platform commission and freelancer net amount
    
    Args:
        amount: Gross payment amount
        discount: Discount amount applied to the payment
        
    Returns:
        Dictionary with commission breakdown
    """
    # Apply discount
    discounted_amount = amount - discount
    
    # Default platform fee: 10%
    platform_fee_rate = Decimal('0.10')
    platform_fee = discounted_amount * platform_fee_rate
    
    # Default net amount: 90%
    net_amount = discounted_amount - platform_fee
    
    return {
        "gross_amount": amount,
        "discount": discount,
        "discounted_amount": discounted_amount,
        "platform_fee": platform_fee,
        "platform_fee_rate": platform_fee_rate,
        "net_amount": net_amount
    }

def calculate_commissions_with_partners(
    amount: Decimal, 
    discount: Decimal = Decimal('0.0'),
    commercial_rate: Optional[Decimal] = None,
    partner_rate: Optional[Decimal] = None
) -> Dict[str, Any]:
    """
    Calculate commissions including commercial and partner rates
    
    Args:
        amount: Gross payment amount
        discount: Discount amount applied to the payment
        commercial_rate: Sales agent commission rate
        partner_rate: Partner commission rate
        
    Returns:
        Dictionary with detailed commission breakdown
    """
    # Apply discount
    discounted_amount = amount - discount
    
    # Default platform fee: 10%
    platform_fee_rate = Decimal('0.10')
    platform_fee = discounted_amount * platform_fee_rate
    
    # Commercial commission (if applicable)
    commercial_commission = Decimal('0.0')
    if commercial_rate:
        commercial_commission = discounted_amount * commercial_rate
    
    # Partner commission (if applicable)
    partner_commission = Decimal('0.0')
    if partner_rate:
        partner_commission = discounted_amount * partner_rate
    
    # Calculate net amount for freelancer
    total_fees = platform_fee + commercial_commission + partner_commission
    net_amount = discounted_amount - total_fees
    
    return {
        "gross_amount": amount,
        "discount": discount,
        "discounted_amount": discounted_amount,
        "platform_fee": platform_fee,
        "platform_fee_rate": platform_fee_rate,
        "commercial_commission": commercial_commission,
        "commercial_rate": commercial_rate or Decimal('0.0'),
        "partner_commission": partner_commission,
        "partner_rate": partner_rate or Decimal('0.0'),
        "total_fees": total_fees,
        "net_amount": net_amount
    }
