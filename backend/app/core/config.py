from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    app_name: str = "AI Content Ops Backend"
    app_env: str = "dev"
    debug: bool = True
    database_url: str = "sqlite:///./backend.db"
    redis_url: str = "redis://localhost:6379/0"
    default_base_reward_points: int = 100

    # Threshold policy
    threshold_p0: float = 0.95
    threshold_p1: float = 0.90
    threshold_p2: float = 0.80

    # Distribution defaults
    youtube_publish_default_visibility: str = "unlisted"
    secondary_channel_name: str = "cms_webhook"
    hold_auto_create_gate1: bool = False

    # Celery queue names
    queue_ai_processing: str = "q.ai_processing"
    queue_review_p0: str = "q.review_p0"
    queue_review_p1: str = "q.review_p1"
    queue_review_p2: str = "q.review_p2"
    queue_review: str = "q.review"
    queue_hold: str = "q.hold"
    queue_report: str = "q.report"
    queue_reward: str = "q.reward"
    queue_distribution_youtube: str = "q.distribution_youtube"
    queue_distribution_secondary: str = "q.distribution_secondary"
    queue_distribution: str = "q.distribution"
    queue_dlq: str = "q.dlq"

    # YouTube OAuth / API
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None
    youtube_redirect_uri: str | None = None
    youtube_oauth_scope: str = "https://www.googleapis.com/auth/youtube.upload"
    youtube_token_url: str = "https://oauth2.googleapis.com/token"
    youtube_oauth_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    youtube_api_upload_url: str = "https://www.googleapis.com/upload/youtube/v3/videos"
    youtube_strict_mode: bool = False
    youtube_daily_quota_limit: int = 100
    youtube_status_poll_url: str = "https://www.googleapis.com/youtube/v3/videos"
    youtube_webhook_secret: str | None = None

    # Model gateway
    model_provider: str = "none"  # none | openai_compatible | ollama | gemini
    model_api_base: str | None = None
    model_api_key: str | None = None
    model_name_default: str = "gpt-4o-mini"
    model_name_impact: str = "gpt-4o-mini"
    model_name_moderation: str = "gpt-4o-mini"
    model_name_classification: str = "gpt-4o-mini"
    model_name_compliance: str = "gpt-4o-mini"
    model_name_content: str = "gpt-4o-mini"
    model_name_localization: str = "gpt-4o-mini"
    model_name_reporter: str = "gpt-4o-mini"
    model_timeout_seconds: float = 30.0
    model_temperature: float = 0.2
    impact_confidence_min: float = 0.60
    model_retry_max_attempts: int = 4
    model_retry_backoff_initial_seconds: float = 1.0
    model_retry_backoff_multiplier: float = 2.0
    model_retry_backoff_max_seconds: float = 20.0

    # TTS / Audio News config
    tts_model: str = "gemini-3.1-flash-tts-preview"
    tts_default_voice: str = "Kore"
    tts_default_locale: str = "en-IN"
    tts_script_gen_model: str = "gemini-2.5-flash"

    # Gemini-specific config (Google Generative Language API)
    google_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    google_genai_use_vertexai: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str | None = None

    # Token encryption (Fernet key, base64 url-safe)
    token_encryption_key: str | None = None

    # Secondary connector
    secondary_channel_webhook_url: str | None = None
    secondary_channel_api_key: str | None = None
    secondary_channel_timeout_seconds: float = 20.0
    secondary_channel_retry_max_attempts: int = 3
    secondary_channel_strict_mode: bool = False

    # Upload security
    upload_max_file_size_bytes: int = 524288000
    upload_allowed_mime_types: str = "video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
    malware_scan_url: str | None = None
    malware_scan_api_key: str | None = None
    malware_scan_timeout_seconds: float = 15.0

    # ------------------------------------------------------------------ #
    # Agentic RAG — Pattern Detection                                    #
    # ------------------------------------------------------------------ #
    pattern_database_url: str | None = None  # postgresql://user:pass@host:5433/news_patterns

    # Gemini embedding model
    gemini_embedding_model: str = "gemini-embedding-exp-03-07"
    pgvector_dimensions: int = 768

    # LLM models for RAG pipeline
    router_model: str = "gemini-2.0-flash"
    synthesiser_model: str = "gemini-2.5-flash"
    router_max_tokens: int = 512
    synthesiser_max_tokens: int = 600
    router_temperature: float = 0.1
    synthesiser_temperature: float = 0.2

    # Temporal decay
    temporal_decay_lambda: float = 0.05

    # Search defaults
    default_days_back: int = 90
    person_search_days_back: int = 180
    default_location_radius_meters: int = 500
    semantic_similarity_threshold: float = 0.72
    max_candidates_after_merge: int = 50
    top_k_to_synthesiser: int = 10

    # Thread assignment confidence thresholds
    thread_join_confidence_threshold: float = 0.80
    thread_link_confidence_threshold: float = 0.50

    # Scoring weights
    score_weight_semantic: float = 0.45
    score_weight_entity: float = 0.30
    score_weight_temporal: float = 0.15
    score_proximity_bonus: float = 0.10
    score_person_bonus: float = 0.10

    # ------------------------------------------------------------------ #
    # Auth / RBAC                                                        #
    # ------------------------------------------------------------------ #
    auth_jwt_secret: str = "change-me"
    auth_jwt_algorithm: str = "HS256"
    auth_access_token_exp_minutes: int = 120
    auth_default_admin_username: str = "admin"
    auth_default_admin_password: str = "admin123"
    auth_default_moderator_username: str = "moderator"
    auth_default_moderator_password: str = "moderator123"
    auth_default_uploader_username: str = "uploader"
    auth_default_uploader_password: str = "uploader123"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_credentials: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("upload_max_file_size_bytes")
    @classmethod
    def validate_upload_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("upload_max_file_size_bytes must be > 0")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
