from typing import Any
from fastapi import APIRouter
from sqlmodel import select
from app.api.deps import SessionDep
from app.models import (
    HelpCategory, HelpArticle, HelpFAQ, 
    HelpCenterResponse
)

router = APIRouter()

DEFAULT_HELP_CENTER = {
    "categories": [
        {
            "title": "Getting Started",
            "description": "Learn the essentials and set up your account.",
            "icon": "Zap",
            "color": "text-amber-500",
            "bgColor": "bg-amber-50 dark:bg-amber-900/20",
            "order": 1,
            "articles": ["Quick start guide", "Platform navigation", "Account setup"]
        },
        {
            "title": "Team & Users",
            "description": "Manage your members, roles, and permissions.",
            "icon": "Users",
            "color": "text-blue-500",
            "bgColor": "bg-blue-50 dark:bg-blue-900/20",
            "order": 2,
            "articles": ["Understanding roles", "Permissions matrix", "Team collaboration basics"]
        },
        {
            "title": "Payments",
            "description": "Top up credits and manage your billing.",
            "icon": "Shield",
            "color": "text-emerald-500",
            "bgColor": "bg-emerald-50 dark:bg-emerald-900/20",
            "order": 3,
            "articles": ["Managing credits", "Top up workflows", "Internal transfers"]
        },
        {
            "title": "Settings",
            "description": "Configure your workspace and security.",
            "icon": "Settings",
            "color": "text-purple-500",
            "bgColor": "bg-purple-50 dark:bg-purple-900/20",
            "order": 4,
            "articles": ["Connecting external apps", "Security protocols", "API key management"]
        }
    ],
    "faqs": [
        {
            "question": "How do I add credits?",
            "answer": "Go to the 'Payments' section, click Top Up, and follow the simple checkout process.",
            "order": 1
        },
        {
            "question": "Where are my API keys?",
            "answer": "You can find your keys in the 'Settings' section under API Management.",
            "order": 2
        },
        {
            "question": "Can I transfer credits?",
            "answer": "Yes, use the 'Internal Transfer' feature within the Payments dashboard.",
            "order": 3
        }
    ]
}

@router.get("", response_model=HelpCenterResponse, response_model_by_alias=True)
def get_help_center(session: SessionDep) -> Any:
    """
    Get all help center content.
    Initializes with defaults if empty.
    """
    categories = session.exec(select(HelpCategory).order_by(HelpCategory.order)).all()
    faqs = session.exec(select(HelpFAQ).order_by(HelpFAQ.order)).all()

    if not categories:
        # Initialize
        for cat_data in DEFAULT_HELP_CENTER["categories"]:
            articles = cat_data.pop("articles")
            category = HelpCategory(**cat_data)
            session.add(category)
            session.commit()
            session.refresh(category)
            
            for idx, art_title in enumerate(articles):
                article = HelpArticle(
                    title=art_title, 
                    category_id=category.id,
                    order=idx + 1
                )
                session.add(article)
        
        for faq_data in DEFAULT_HELP_CENTER["faqs"]:
            faq = HelpFAQ(**faq_data)
            session.add(faq)
            
        session.commit()
        # Refresh lists
        categories = session.exec(select(HelpCategory).order_by(HelpCategory.order)).all()
        faqs = session.exec(select(HelpFAQ).order_by(HelpFAQ.order)).all()

    return {
        "categories": categories,
        "faqs": faqs
    }
