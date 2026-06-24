"""
Supabase Auth integration for Kuryos FastAPI backend.

Responsabilidades:
  - Verificar JWTs emitidos pelo Supabase Auth (HS256, sem chamada HTTP)
  - Gerenciar usuários via Supabase Admin API (criar, convidar, atualizar metadata)
  - Converter claims do Supabase para o formato de usuário Kuryos

Variáveis de ambiente necessárias:
  SUPABASE_URL         — https://<project>.supabase.co
  SUPABASE_SERVICE_KEY — service_role key (bypassa RLS, uso somente no backend)
  SUPABASE_JWT_SECRET  — Settings → API → JWT Settings → JWT Secret
"""
import os
import logging
from typing import Optional
from jose import jwt as jose_jwt, JWTError
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ─── Lazy-init: o client é criado uma vez na startup ─────────────────────────

_supabase_admin: Optional[Client] = None
_jwt_secret: Optional[str] = None


def init_supabase_auth():
    global _supabase_admin, _jwt_secret
    url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    _jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")

    if not url or not service_key:
        logger.warning("SUPABASE_URL ou SUPABASE_SERVICE_KEY ausentes — Supabase Auth desativado")
        return False
    if not _jwt_secret:
        logger.warning("SUPABASE_JWT_SECRET ausente — verificação local de JWT desativada")

    _supabase_admin = create_client(url, service_key)
    logger.info("Supabase Auth admin client inicializado")
    return True


def is_supabase_available() -> bool:
    return _supabase_admin is not None


# ─── Verificação de JWT ───────────────────────────────────────────────────────

def verify_supabase_jwt(token: str) -> Optional[dict]:
    """
    Verifica um JWT emitido pelo Supabase Auth localmente (sem HTTP).
    Retorna as claims do payload ou None se inválido.
    """
    if not _jwt_secret:
        return None
    try:
        payload = jose_jwt.decode(
            token,
            _jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except JWTError:
        return None


def supabase_claims_to_kuryos_user(claims: dict) -> Optional[dict]:
    """
    Converte as claims do JWT Supabase para o dict de usuário Kuryos.

    Estrutura esperada no app_metadata:
      { "tenant_id": "...", "user_role": "admin", "name": "...", "kuryos_id": "..." }
    """
    app_meta = claims.get("app_metadata") or {}
    user_meta = claims.get("user_metadata") or {}

    tenant_id = app_meta.get("tenant_id") or user_meta.get("tenant_id")
    role = app_meta.get("user_role") or user_meta.get("user_role") or "vendedor"
    name = app_meta.get("name") or user_meta.get("name") or claims.get("email", "")
    kuryos_id = app_meta.get("kuryos_id") or claims.get("sub")

    if not tenant_id:
        return None

    return {
        "id": kuryos_id,
        "supabase_id": claims.get("sub"),
        "email": claims.get("email", ""),
        "name": name,
        "role": role,
        "tenant_id": tenant_id,
        "auth_provider": "supabase",
    }


def is_supabase_token(token: str) -> bool:
    """
    Heurística rápida: JWTs Supabase têm 'aud: authenticated'.
    Evita tentar decodificar com o segredo errado.
    """
    try:
        # Decode sem verificar assinatura — só para checar o claim
        unverified = jose_jwt.get_unverified_claims(token)
        return unverified.get("aud") == "authenticated"
    except Exception:
        return False


# ─── Gerenciamento de usuários via Admin API ──────────────────────────────────

def _build_app_metadata(tenant_id: str, role: str, name: str, kuryos_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "user_role": role,     # "role" é reservado pelo Supabase — usamos "user_role"
        "name": name,
        "kuryos_id": kuryos_id,
    }


def create_supabase_user(
    email: str,
    password: str,
    tenant_id: str,
    role: str,
    name: str,
    kuryos_id: str,
) -> Optional[dict]:
    """
    Cria um usuário no Supabase Auth com metadata customizado.
    Retorna o dict do usuário criado ou None em caso de erro.
    """
    if not _supabase_admin:
        return None
    try:
        metadata = _build_app_metadata(tenant_id, role, name, kuryos_id)
        response = _supabase_admin.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": metadata,
            "user_metadata": {"name": name},
        })
        return response.user.__dict__ if response.user else None
    except Exception as e:
        logger.error(f"Erro ao criar usuário no Supabase: {e}")
        return None


def invite_supabase_user(
    email: str,
    tenant_id: str,
    role: str,
    name: str,
    kuryos_id: str,
) -> Optional[dict]:
    """
    Convida um usuário por email via Supabase Auth (magic link de redefinição de senha).
    Retorna o dict do usuário criado ou None.
    """
    if not _supabase_admin:
        return None
    try:
        import secrets
        temp_password = secrets.token_urlsafe(16)
        metadata = _build_app_metadata(tenant_id, role, name, kuryos_id)
        response = _supabase_admin.auth.admin.create_user({
            "email": email,
            "password": temp_password,
            "email_confirm": False,   # Supabase enviará email de confirmação
            "app_metadata": metadata,
            "user_metadata": {"name": name},
        })
        return response.user.__dict__ if response.user else None
    except Exception as e:
        logger.error(f"Erro ao convidar usuário no Supabase: {e}")
        return None


def update_supabase_user_metadata(supabase_id: str, updates: dict) -> bool:
    """
    Atualiza o app_metadata de um usuário (ex: mudança de role).
    """
    if not _supabase_admin:
        return False
    try:
        _supabase_admin.auth.admin.update_user_by_id(supabase_id, {"app_metadata": updates})
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar metadata no Supabase: {e}")
        return False


def delete_supabase_user(supabase_id: str) -> bool:
    if not _supabase_admin:
        return False
    try:
        _supabase_admin.auth.admin.delete_user(supabase_id)
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar usuário no Supabase: {e}")
        return False


def sign_in_with_password(email: str, password: str) -> Optional[dict]:
    """
    Autentica um usuário via Supabase Auth (email + senha).
    Retorna session dict com access_token, refresh_token, etc.
    """
    if not _supabase_admin:
        return None
    try:
        response = _supabase_admin.auth.sign_in_with_password({"email": email, "password": password})
        if response.session:
            return {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "expires_in": response.session.expires_in,
                "user": response.user.__dict__ if response.user else None,
            }
        return None
    except Exception as e:
        logger.debug(f"Supabase sign_in falhou para {email}: {e}")
        return None


def get_supabase_user_by_email(email: str) -> Optional[dict]:
    """Busca um usuário no Supabase pelo email via Admin API."""
    if not _supabase_admin:
        return None
    try:
        response = _supabase_admin.auth.admin.list_users()
        users = response if isinstance(response, list) else []
        for u in users:
            if hasattr(u, "email") and u.email == email:
                return u.__dict__
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar usuário no Supabase: {e}")
        return None
