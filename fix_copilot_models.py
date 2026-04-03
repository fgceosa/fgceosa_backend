"""
Fix copilot models that are unsupported by Requesty router.
Run with: PYTHONPATH=. .venv/bin/python3 fix_copilot_models.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))

from sqlmodel import Session, text
from app.core.db import copilot_engine

# Models known to be unsupported/fictional on Requesty
UNSUPPORTED_MODELS = {
    "smart/task",
    "openai/gpt-5",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "openai/chatgpt-4o",  # might not be supported
}

# Safe fallback model
FALLBACK_MODEL = "openai/gpt-4o-mini"

# Normalize bare names to provider/model
MODEL_FIXES = {
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "gpt-4-turbo": "openai/gpt-4-turbo",
    "gpt-3.5-turbo": "openai/gpt-3.5-turbo",
    "claude-3-opus": "anthropic/claude-3-opus",
    "claude-3-5-sonnet": "anthropic/claude-3-5-sonnet",
    "claude-3-haiku": "anthropic/claude-3-haiku",
    "gemini-pro-1.5": "google/gemini-pro-1.5",
    "gemini-flash-1.5": "google/gemini-flash-1.5",
}

print(f"Connecting to Copilot DB...")

with Session(copilot_engine) as session:
    # SQLModel tables with schemas need the schema prefix in raw SQL
    try:
        result = session.exec(text("SELECT id, name, model FROM copilot.copilot ORDER BY created_at DESC"))
        rows = result.all()
    except Exception as e:
        print(f"❌ Error querying copilot.copilot: {e}")
        print("Trying public.copilot...")
        result = session.exec(text("SELECT id, name, model FROM copilot ORDER BY created_at DESC"))
        rows = result.all()
    
    print(f"\n📋 Found {len(rows)} copilots:\n")
    for row in rows:
        print(f"  [{row[0]}] {row[1]!r:40s} model={row[2]!r}")
    
    print("\n🔧 Applying fixes...")
    updated = 0
    
    for row in rows:
        cop_id, cop_name, cop_model = row
        new_model = None
        
        if cop_model in UNSUPPORTED_MODELS:
            new_model = FALLBACK_MODEL
            print(f"  ⚠ Replacing unsupported '{cop_model}' -> '{new_model}' for copilot '{cop_name}'")
        elif cop_model in MODEL_FIXES:
            new_model = MODEL_FIXES[cop_model]
            print(f"  🔄 Normalizing '{cop_model}' -> '{new_model}' for copilot '{cop_name}'")
        
        if new_model:
            # Use schema prefix for update as well
            try:
                session.exec(text("UPDATE copilot.copilot SET model = :model WHERE id = :id"), 
                             {"model": new_model, "id": str(cop_id)})
            except Exception:
                session.exec(text("UPDATE copilot SET model = :model WHERE id = :id"), 
                             {"model": new_model, "id": str(cop_id)})
            updated += 1
    
    session.commit()
    print(f"\n✅ Updated {updated} copilots.")
    
    # Show final state
    try:
        result2 = session.exec(text("SELECT name, model FROM copilot.copilot ORDER BY created_at DESC"))
    except Exception:
        result2 = session.exec(text("SELECT name, model FROM copilot ORDER BY created_at DESC"))
        
    print("\n📋 Final copilot models:")
    for row in result2.all():
        print(f"  {row[0]!r:40s} -> {row[1]!r}")
