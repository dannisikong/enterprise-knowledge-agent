from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str
    token: str
    expires_at: str
