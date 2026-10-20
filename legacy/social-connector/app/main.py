# Social Connector - Main FastAPI Application

from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
from typing import List, Optional
import logging

from app.config import get_settings
from app.db.session import init_db, get_db_session
from app.providers.registry import initialize_providers
from app.core.models import User, SocialConnection, Post, PostTarget, Media, JobEvent, PostStatus, ConnectionStatus
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict, Any
import secrets
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer(auto_error=False)


# Pydantic schemas
class ProviderInfo(BaseModel):
    id: str
    name: str
    capabilities: Dict[str, Any]


class ConnectResponse(BaseModel):
    authorization_url: str
    state: str
    code_challenge: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: str
    provider: str
    account_name: str
    external_account_id: str
    external_account_type: Optional[str]
    status: str
    created_at: datetime


class MediaItem(BaseModel):
    url: HttpUrl
    type: str  # image, video, document, audio
    mime: Optional[str] = None
    sha256: Optional[str] = None


class PostTargetConfig(BaseModel):
    provider: str
    account_id: str
    visibility: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class PostCreate(BaseModel):
    text: Optional[str] = None
    media: List[MediaItem] = []
    targets: List[dict] = []
    publish_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None


class PostResponse(BaseModel):
    id: str
    user_id: str
    text: Optional[str]
    media: List[dict]
    targets: List[dict]
    status: str
    publish_at: Optional[datetime]
    created_at: datetime
    idempotency_key: Optional[str]


class PostTargetResponse(BaseModel):
    id: str
    post_id: str
    connection_id: str
    provider: str
    external_post_id: Optional[str]
    external_url: Optional[str]
    status: str
    error_code: Optional[str]
    error_message: Optional[str]
    attempt_count: int
    next_retry_at: Optional[datetime]
    published_at: Optional[datetime]


class JobResponse(BaseModel):
    id: str
    post_id: str
    status: str
    targets: List[PostTargetResponse]
    created_at: datetime
    completed_at: Optional[datetime]


class AccountResponse(BaseModel):
    id: str
    provider: str
    account_name: str
    external_account_id: str
    external_account_type: Optional[str]
    capabilities: List[str]
    status: str


# Global state
_provider_registry = None
_scheduler = None


# Dependency functions
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Get current user ID from API key."""
    settings = get_settings()
    
    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")
    
    # Hash the provided API key
    api_key_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    
    # For development, also allow the raw key
    with get_db_session() as db:
        user = db.execute(
            select(User).where(
                (User.api_key_hash == api_key_hash) | (User.api_key_hash == credentials.credentials)
            )
        ).scalar_one_or_none()
        
        if not user:
            # For development, create a default user if API key matches
            if settings.api_key and credentials.credentials == settings.api_key:
                user = db.execute(select(User).where(User.id == "default")).scalar_one_or_none()
                if not user:
                    user = User(id="default", email="admin@local", api_key_hash=credentials.credentials)
                    db.add(user)
                    db.commit()
                    db.refresh(user)
            # Development mode: accept any key
            elif settings.app_env == "development":
                user = db.execute(select(User).where(User.id == "default")).scalar_one_or_none()
                if not user:
                    user = User(id="default", email="admin@local", api_key_hash=credentials.credentials)
                    db.add(user)
                    db.commit()
                    db.refresh(user)
            else:
                raise HTTPException(status_code=401, detail="Invalid API key")
        
        return user.id


def get_provider_registry():
    """Get the provider registry."""
    from app.providers.registry import get_available_providers
    # This is a singleton, initialize once
    pass


# Request/Response models
class ConnectRequest(BaseModel):
    provider: str
    redirect_uri: Optional[str] = None


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Social Connector...")
    init_db()
    
    # Initialize provider registry
    from app.providers.registry import initialize_providers
    from app.config import get_settings
    settings = get_settings()
    config = {
        "linkedin": {
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
            "redirect_uri": settings.linkedin_redirect_uri,
        }
    }
    initialize_providers(config)
    logger.info("Provider registry initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Social Connector...")


# Create FastAPI app
app = FastAPI(
    title="Social Media Auto-Publishing Connector",
    description="Unified API for publishing to social media platforms",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security scheme
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "social-connector"}


# Provider endpoints
@app.get("/v1/providers", response_model=List[dict])
async def list_providers():
    """List all available providers with capabilities."""
    from app.providers.registry import get_available_providers, initialize_providers
    from app.config import get_settings
    
    settings = get_settings()
    config = {
        "linkedin": {
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
            "redirect_uri": settings.linkedin_redirect_uri,
        }
    }
    registry = initialize_providers(config)
    
    from app.providers.registry import get_available_providers
    return get_available_providers(registry)


# OAuth endpoints
@app.post("/v1/connect/{provider}", response_model=ConnectResponse)
async def connect_provider(
    provider: str,
    redirect_uri: Optional[str] = None,
):
    """Start OAuth flow for a provider."""
    from app.providers.registry import initialize_providers
    from app.config import get_settings
    
    settings = get_settings()
    config = {
        "linkedin": {
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
            "redirect_uri": settings.linkedin_redirect_uri,
        }
    }
    registry = initialize_providers(config)
    
    provider_obj = registry.get(provider)
    if not provider_obj:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
    
    # Generate state and PKCE
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = secrets.token_urlsafe(32)  # Simplified
    
    # Store state in session (simplified - in production use Redis)
    # For now, we'll pass it through
    
    authorization_url = await provider_obj.get_authorization_url(
        state=state,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri or ""
    )
    
    return ConnectResponse(
        authorization_url=authorization_url,
        state=state,
        code_challenge=code_challenge
    )


@app.get("/v1/callback/{provider}")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    """OAuth callback handler."""
    from app.providers.registry import initialize_providers
    from app.config import get_settings
    from app.db.session import get_db_session
    from app.core.models import SocialConnection, User
    from sqlalchemy import select
    import json
    
    if error:
        return {"error": error, "description": error_description}
    
    settings = get_settings()
    config = {
        "linkedin": {
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
            "redirect_uri": settings.linkedin_redirect_uri,
        }
    }
    registry = initialize_providers(config)
    
    provider_obj = registry.get(provider)
    if not provider_obj:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
    
    # Exchange code for tokens
    token_data = await provider_obj.exchange_code(code, redirect_uri or "")
    
    # Get accounts to identify the account
    # For now, create a default user
    with get_db_session() as db:
        user = db.execute(select(User).where(User.id == "default")).scalar_one_or_none()
        if not user:
            user = User(id="default", email="admin@local")
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # Get accounts to find the connected account
        # This is simplified - in production, store state->user mapping
        accounts = await provider_obj.get_accounts(
            type('ConnectionData', (), {
                'provider': provider,
                'access_token': token_data.get('access_token'),
                'refresh_token': token_data.get('refresh_token'),
                'token_expires_at': None,
            })()
        )
        
        if accounts:
            account = accounts[0]
            # Encrypt tokens (simplified)
            from app.auth.crypto import encrypt_token
            connection = SocialConnection(
                id=secrets.token_urlsafe(16),
                user_id=user.id,
                provider=provider,
                external_account_id=account.external_id,
                external_account_type=account.type,
                account_name=account.name,
                access_token_encrypted=encrypt_token(token_data.get("access_token", "")),
                refresh_token_encrypted=encrypt_token(token_data.get("refresh_token", "")) if token_data.get("refresh_token") else None,
                token_expires_at=None,
                scopes_json=token_data.get("scope", "").split() if token_data.get("scope") else None,
                metadata_json={"capabilities": account.capabilities, "metadata": account.metadata},
                status="active"
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)
            
            return {"message": "Connected successfully", "connection_id": connection.id, "account": account.name}
    
    raise HTTPException(status_code=400, detail="Failed to connect")


# Account endpoints
@app.get("/v1/accounts", response_model=List[AccountResponse])
async def list_accounts(user_id: str = Depends(get_current_user_id)):
    """List all connected accounts for the user."""
    with get_db_session() as db:
        connections = db.execute(
            select(SocialConnection).where(SocialConnection.user_id == user_id)
        ).scalars().all()
        
        return [
            AccountResponse(
                id=c.id,
                provider=c.provider,
                account_name=c.account_name,
                external_account_id=c.external_account_id,
                external_account_type=c.external_account_type,
                capabilities=json.loads(c.scopes_json) if c.scopes_json else [],
                status=c.status.value
            )
            for c in connections
        ]


@app.delete("/v1/accounts/{connection_id}")
async def delete_account(
    connection_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Disconnect a social account."""
    with get_db_session() as db:
        connection = db.execute(
            select(SocialConnection).where(
                SocialConnection.id == connection_id,
                SocialConnection.user_id == user_id
            )
        ).scalar_one_or_none()
        
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        db.delete(connection)
        db.commit()
        return {"message": "Account disconnected"}


# Post endpoints
@app.post("/v1/posts", response_model=PostResponse)
async def create_post(
    post: PostCreate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id)
):
    """Create a new post job."""
    import json
    from app.core.models import Post, PostTarget, SocialConnection
    from sqlalchemy import select
    
    with get_db_session() as db:
        # Check idempotency
        if post.idempotency_key:
            existing = db.execute(
                select(Post).where(
                    Post.user_id == user_id,
                    Post.idempotency_key == post.idempotency_key
                )
            ).scalar_one_or_none()
            if existing:
                return PostResponse(
                    id=existing.id,
                    user_id=existing.user_id,
                    text=existing.text,
                    media=json.loads(existing.media_json) if existing.media_json else [],
                    targets=[],  # Simplified
                    status=existing.status.value,
                    publish_at=existing.publish_at,
                    created_at=existing.created_at,
                    idempotency_key=existing.idempotency_key
                )
        
        # Create post
        new_post = Post(
            id=secrets.token_urlsafe(16),
            user_id=user_id,
            text=post.text,
            media_json=json.dumps([m.dict() for m in post.media]) if post.media else None,
            publish_at=post.publish_at,
            idempotency_key=post.idempotency_key or secrets.token_urlsafe(16),
            status=PostStatus.QUEUED if not post.publish_at or post.publish_at <= datetime.now(timezone.utc) else PostStatus.CREATED,
        )
        db.add(new_post)
        
        # Create targets
        for target in post.targets:
            connection = db.execute(
                select(SocialConnection).where(
                    SocialConnection.id == target.get("account_id"),
                    SocialConnection.user_id == user_id
                )
            ).scalar_one_or_none()
            
            if connection:
                target_obj = PostTarget(
                    id=secrets.token_urlsafe(16),
                    post_id=new_post.id,
                    connection_id=connection.id,
                    provider=target.get("provider"),
                    status=PostStatus.QUEUED,
                )
                db.add(target_obj)
        
        db.commit()
        db.refresh(new_post)
        
        # Schedule background processing
        if new_post.status == PostStatus.QUEUED:
            background_tasks.add_task(process_post_job, new_post.id)
        
        return PostResponse(
            id=new_post.id,
            user_id=new_post.user_id,
            text=new_post.text,
            media=json.loads(new_post.media_json) if new_post.media_json else [],
            targets=[{"provider": t.provider, "account_id": t.connection_id} for t in new_post.targets],
            status=new_post.status.value,
            publish_at=new_post.publish_at,
            created_at=new_post.created_at,
            idempotency_key=new_post.idempotency_key
        )


@app.get("/v1/posts", response_model=List[PostResponse])
async def list_posts(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id)
):
    """List posts for the user."""
    from app.core.models import Post
    from sqlalchemy import select, desc
    
    with get_db_session() as db:
        query = select(Post).where(Post.user_id == user_id).order_by(desc(Post.created_at))
        
        if status:
            query = query.where(Post.status == PostStatus(status))
        
        query = query.limit(limit).offset(offset)
        posts = db.execute(query).scalars().all()
        
        import json
        return [
            PostResponse(
                id=p.id,
                user_id=p.user_id,
                text=p.text,
                media=json.loads(p.media_json) if p.media_json else [],
                targets=[],  # Simplified
                status=p.status.value,
                publish_at=p.publish_at,
                created_at=p.created_at,
                idempotency_key=p.idempotency_key
            )
            for p in posts
        ]


@app.get("/v1/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db_session)
):
    """Get a specific post with its targets."""
    from app.core.models import Post, PostTarget
    from sqlalchemy import select
    import json
    
    post = db.execute(
        select(Post).where(Post.id == post_id, Post.user_id == user.id)
    ).scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    targets = db.execute(
        select(PostTarget).where(PostTarget.post_id == post_id)
    ).scalars().all()
    
    import json
    return PostResponse(
        id=post.id,
        user_id=post.user_id,
        text=post.text,
        media=json.loads(post.media_json) if post.media_json else [],
        targets=[
            {
                "provider": t.provider,
                "account_id": t.connection_id,
                "status": t.status.value,
                "external_post_id": t.external_post_id,
                "external_url": t.external_url,
                "error_code": t.error_code,
                "error_message": t.error_message
            }
            for t in targets
        ],
        status=post.status.value,
        publish_at=post.publish_at,
        created_at=post.created_at,
        idempotency_key=post.idempotency_key
    )


@app.post("/v1/posts/{post_id}/cancel")
async def cancel_post(
    post_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db_session)
):
    """Cancel a queued post."""
    from app.core.models import Post, PostTarget, PostStatus
    from sqlalchemy import select
    
    post = db.execute(
        select(Post).where(Post.id == post_id, Post.user_id == user.id)
    ).scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.status in (PostStatus.PUBLISHED, PostStatus.FAILED, PostStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Cannot cancel post in {post.status.value} status")
    
    post.status = PostStatus.CANCELLED
    
    # Cancel all targets
    targets = db.execute(select(PostTarget).where(PostTarget.post_id == post_id)).scalars().all()
    for target in targets:
        if target.status in (PostStatus.QUEUED, PostStatus.VALIDATING, PostStatus.UPLOADING, PostStatus.PROCESSING):
            target.status = PostStatus.CANCELLED
    
    db.commit()
    return {"message": "Post cancelled"}


# Job endpoints
@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db_session)
):
    """Get job status."""
    from app.core.models import Post, PostTarget, JobEvent
    from sqlalchemy import select
    
    post = db.execute(
        select(Post).where(Post.id == job_id, Post.user_id == user.id)
    ).scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Job not found")
    
    targets = db.execute(
        select(PostTarget).where(PostTarget.post_id == job_id)
    ).scalars().all()
    
    return JobResponse(
        id=post.id,
        post_id=post.id,
        status=post.status.value,
        targets=[
            PostTargetResponse(
                id=t.id,
                post_id=t.post_id,
                connection_id=t.connection_id,
                provider=t.provider,
                external_post_id=t.external_post_id,
                external_url=t.external_url,
                status=t.status.value,
                error_code=t.error_code,
                error_message=t.error_message,
                attempt_count=t.attempt_count,
                next_retry_at=t.next_retry_at,
                published_at=t.published_at
            )
            for t in targets
        ],
        created_at=post.created_at,
        completed_at=post.published_at if post.status == PostStatus.PUBLISHED else None
    )


# Background task for processing posts
async def process_post_job(post_id: str):
    """Background task to process a post through all its targets."""
    from app.db.session import get_db_session
    from app.core.models import Post, PostTarget, PostStatus
    from app.providers.registry import initialize_providers
    from app.config import get_settings
    import json
    
    settings = get_settings()
    config = {
        "linkedin": {
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
            "redirect_uri": settings.linkedin_redirect_uri,
        }
    }
    registry = initialize_providers(config)
    
    with get_db_session() as db:
        post = db.execute(select(Post).where(Post.id == post_id)).scalar_one_or_none()
        if not post:
            return
        
        post.status = PostStatus.VALIDATING
        db.commit()
        
        targets = db.execute(
            select(PostTarget).where(PostTarget.post_id == post_id)
        ).scalars().all()
        
        for target in targets:
            connection = db.execute(
                select(SocialConnection).where(SocialConnection.id == target.connection_id)
            ).scalar_one_or_none()
            
            if not connection:
                target.status = PostStatus.FAILED
                target.error_code = "CONNECTION_NOT_FOUND"
                target.error_message = "Connection not found"
                db.commit()
                continue
            
            target.status = PostStatus.VALIDATING
            db.commit()
            
            provider = registry.get(target.provider)
            if not provider:
                target.status = PostStatus.FAILED
                target.error_code = "PROVIDER_NOT_FOUND"
                target.error_message = f"Provider {target.provider} not available"
                db.commit()
                continue
            
            # Build universal post
            from app.providers.base import UniversalPost, MediaItem, MediaType, PostTargetConfig
            import json
            
            media = []
            if post.media_json:
                for m in json.loads(post.media_json):
                    media.append(MediaItem(
                        url=m["url"],
                        type=MediaType(m["type"]),
                        mime=m.get("mime"),
                        sha256=m.get("sha256")
                    ))
            
            universal_post = UniversalPost(
                text=post.text,
                media=media,
                targets=[PostTargetConfig(provider=target.provider, account_id=target.connection_id)],
                idempotency_key=post.idempotency_key,
                publish_at=post.publish_at.isoformat() if post.publish_at else None
            )
            
            # Create connection data
            from app.providers.base import ConnectionData
            from app.auth.crypto import decrypt_token
            
            connection_data = ConnectionData(
                provider=connection.provider,
                external_account_id=connection.external_account_id,
                external_account_type=connection.external_account_type,
                account_name=connection.account_name,
                access_token=decrypt_token(connection.access_token_encrypted),
                refresh_token=decrypt_token(connection.refresh_token_encrypted) if connection.refresh_token_encrypted else None,
                token_expires_at=connection.token_expires_at.isoformat() if connection.token_expires_at else None,
                scopes=connection.scopes_json,
                metadata=connection.metadata_json
            )
            
            # Validate
            target.status = PostStatus.VALIDATING
            db.commit()
            
            validation = await provider.validate_post(connection_data, universal_post)
            if not validation.valid:
                target.status = PostStatus.FAILED
                target.error_code = "VALIDATION_FAILED"
                target.error_message = "; ".join(validation.errors)
                db.commit()
                continue
            
            # Upload media and publish
            target.status = PostStatus.UPLOADING
            db.commit()
            
            # TODO: Upload media to provider if needed
            
            # Publish
            target.status = PostStatus.PROCESSING
            db.commit()
            
            result = await provider.publish(connection_data, universal_post)
            
            if result.success:
                target.status = PostStatus.PUBLISHED
                target.external_post_id = result.external_post_id
                target.external_url = result.external_url
                target.published_at = datetime.now(timezone.utc)
            else:
                target.status = PostStatus.FAILED
                target.error_code = result.error_code or "PUBLISH_FAILED"
                target.error_message = result.error_message or "Unknown error"
                target.raw_response_json = result.raw_response
            
            db.commit()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)