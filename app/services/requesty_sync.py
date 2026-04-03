import logging
from decimal import Decimal
from sqlmodel import select
from app.models import AIModel, AIProvider
from app.services.requesty_ai_client import requesty_ai_client

logger = logging.getLogger(__name__)

class RequestySyncService:
    async def sync_models(self, session):
        try:
            logger.info("Starting RequestyAI model sync...")
            
            # Fetch remote models
            response = await requesty_ai_client.list_models()
            remote_models = response.get("data", [])
            
            created_count = 0
            updated_count = 0
            
            # Pre-fetch all providers for mapping
            providers_stmt = select(AIProvider)
            local_providers = {p.slug: p for p in session.exec(providers_stmt).all()}
            
            # Map of model name keywords to provider slugs for brand grouping
            # (Ensures 'vertex/claude' is grouped under 'Anthropic' in the UI)
            BRAND_MAPPING = {
                "claude": "anthropic",
                "gpt-": "openai",
                "chatgpt": "openai",
                "gemini": "google",
                "llama": "meta",
                "mistral": "mistral",
                "mixtral": "mistral",
                "deepseek": "deepseek",
                "qwen": "alibaba"
            }
            
            for m_data in remote_models:
                # m_data structure example: {"id": "openai/gpt-4o", "created": 123, "object": "model", "owned_by": "openai"}
                full_id = m_data.get("id", "")
                if "/" not in full_id:
                    continue
                
                # OPTIMIZATION: Filter out date-based/legacy model versions to save memory and DB space
                # We only want top-level aliases (e.g. "gpt-4o") not specific snapshots (e.g. "gpt-4o-2024-08-06")
                if any(year in full_id for year in ["2023-", "2024-", "2025-", "experimental"]):
                    continue
                
                raw_provider_slug, model_slug_part = full_id.split("/", 1)
                
                # Intelligent Provider Mapping: Group models by brand regardless of routing provider
                # e.g. bedrock/claude-3 -> provider: anthropic (but slug remains bedrock/claude-3)
                target_provider_slug = raw_provider_slug
                model_lower = full_id.lower()
                
                for keyword, brand_slug in BRAND_MAPPING.items():
                    if keyword in model_lower:
                        target_provider_slug = brand_slug
                        break
                
                # Try to find or create the BRAND provider
                if target_provider_slug not in local_providers:
                    # Create new provider if not exists
                    new_provider = AIProvider(
                        name=target_provider_slug.replace("-", " ").capitalize(),
                        slug=target_provider_slug,
                        is_active=True
                    )
                    session.add(new_provider)
                    session.commit()
                    session.refresh(new_provider)
                    local_providers[target_provider_slug] = new_provider
                    logger.info(f"Created new provider via sync: {target_provider_slug}")
                
                provider = local_providers[target_provider_slug]
                
                # Look for existing model by unique slug (the full ID remains the absolute router path)
                model_full_slug = full_id
                stmt = select(AIModel).where(AIModel.slug == model_full_slug)
                existing_model = session.exec(stmt).first()
                
                # Extract pricing and context info
                # Prices in Requesty are per token, we store per 1k tokens for UI consistency
                input_price = Decimal(str(m_data.get("input_price", 0))) * Decimal("1000")
                output_price = Decimal(str(m_data.get("output_price", 0))) * Decimal("1000")
                context_size = str(m_data.get("context_window", ""))
                description = m_data.get("description", "")
                
                # Intelligent Category Mapping
                category = "Text"
                if "embed" in model_lower:
                    category = "Embedding"
                elif "vision" in model_lower or "claude-3-opus" in model_lower or "claude-3-sonnet" in model_lower:
                    # Some multi-modal models might be vision-capable, but primary is usually text
                    pass
                
                if existing_model:
                    # Update fields
                    existing_model.name = model_slug_part.replace("-", " ").title()
                    existing_model.input_price = input_price
                    existing_model.output_price = output_price
                    # FORCE UPDATE provider_id if it differs (to fix existing mis-categorized models)
                    if existing_model.provider_id != provider.id:
                        existing_model.provider_id = provider.id
                        logger.info(f"Re-mapped model {model_full_slug} to provider {provider.name}")

                    if context_size and not existing_model.context_size:
                        existing_model.context_size = context_size
                    if description and not existing_model.description:
                        existing_model.description = description
                    
                    # Update category if it was default but we found a better match
                    if existing_model.category != category:
                        existing_model.category = category
                        logger.info(f"Updated category for {model_full_slug} to {category}")
                    updated_count += 1
                else:
                    # Create new model
                    new_model = AIModel(
                        name=model_slug_part.replace("-", " ").title(),
                        slug=model_full_slug,
                        provider_id=provider.id,
                        status="Approved",
                        availability="Global",
                        category=category,
                        input_price=input_price,
                        output_price=output_price,
                        context_size=context_size,
                        description=description
                    )
                    session.add(new_model)
                    created_count += 1
                    logger.info(f"Imported new model from Requesty: {model_full_slug}")
            
            session.commit()
            
            return {
                "status": "success",
                "created": created_count,
                "updated": updated_count,
                "total_fetched": len(remote_models)
            }
            
        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            return {"status": "error", "message": str(e)}

requesty_sync_service = RequestySyncService()
